from flask import Flask, request, jsonify, Response
from database.db import create_connection
from openai_integration.openai_utils import get_openai_response, get_openai_embedding
import json
import logging
import os
import hashlib
import redis  # ✅ Valkey uses Redis API
import re
import mysql.connector
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from pinecone import Pinecone
from datetime import datetime

# ✅ Load environment variables
load_dotenv()

# ✅ Initialize Flask app
app = Flask(__name__)

# ✅ Configure Rate Limiter using Valkey (Redis API)
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="redis://localhost:6379",  # ✅ Use Valkey for rate limit tracking
    default_limits=["10 per minute"]
)

# ✅ Initialize Valkey (Using Redis API)
valkey_client = redis.Redis(host="localhost", port=6379, db=0)
CACHE_TTL = 3600  # Cache responses for 1 hour

# ✅ MySQL Database Configuration
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# ✅ Initialize MySQL Connection
try:
    db_conn = create_connection()
    logging.info("✅ Connected to MySQL database successfully.")
except Exception as e:
    logging.error(f"❌ Failed to connect to MySQL: {e}")
    db_conn = None

# ✅ Initialize Pinecone
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX", "chatbot-embeddings")

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(name=PINECONE_INDEX_NAME)

# ✅ Ensure Pinecone Index Exists
if PINECONE_INDEX_NAME not in pc.list_indexes().names():
    print(f"ℹ️ Creating Pinecone index: {PINECONE_INDEX_NAME} ...")
    pc.create_index(name=PINECONE_INDEX_NAME, dimension=3072, metric="cosine")
else:
    print(f"✅ Pinecone index '{PINECONE_INDEX_NAME}' already exists.")

# ✅ Configure Logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# ✅ Function to get a daily log filename
def get_log_filename():
    """Generates a daily rotating log filename."""
    log_dir = "/home/jeff/devops/aiml1/chatbot-api/logs"
    os.makedirs(log_dir, exist_ok=True)  # ✅ Ensure logs directory exists

    today = datetime.utcnow().strftime("%Y-%m-%d")  # Daily logs
    return os.path.join(log_dir, f"chatbot_logs_{today}.json")

# ✅ Function to write logs to a JSON file (Daily Rotation)
def log_to_json(user_query, response, status="success"):
    """Logs chatbot interactions to a daily rotating JSON log file."""
    log_entry = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "query": user_query,
        "response": response,
        "status": status
    }

    log_file = get_log_filename()
    
    try:
        with open(log_file, "a", encoding="utf-8") as file:
            json.dump(log_entry, file, ensure_ascii=False)
            file.write("\n")  # ✅ New line to separate JSON entries
        print("✅ Logged query to JSON file.")
    except Exception as e:
        print(f"❌ Failed to write to chatbot JSON log: {e}")

# ✅ Function to sanitize user input (prevent hacks & bad input)
def sanitize_input(user_query):
    """Sanitizes user input to prevent SQL injection, XSS, and illegal queries."""
    user_query = user_query.strip()
    
    # ✅ Prevent SQL injection
    user_query = re.sub(r"(--|;|'|\"|DROP|ALTER|INSERT|DELETE|UPDATE|SELECT|UNION)", "", user_query, flags=re.IGNORECASE)

    # ✅ Block illegal queries
    blocked_keywords = ["hack", "exploit", "malware", "illegal", "bypass security"]
    for keyword in blocked_keywords:
        if keyword in user_query.lower():
            return None  # 🚫 Block the request

    return user_query

# ✅ Function to generate a unique hash for queries
def generate_query_hash(user_query):
    return hashlib.md5(user_query.encode()).hexdigest()

# ✅ Function to store responses in Valkey (Cache)
def cache_set_response(user_query, response):
    """Store response in Valkey cache with a unique key."""
    query_hash = generate_query_hash(user_query)
    valkey_client.setex(f"query:{query_hash}", CACHE_TTL, json.dumps(response, ensure_ascii=False))

# ✅ Function to retrieve responses from Valkey (Cache)
def cache_get_response(user_query):
    """Retrieve cached response from Valkey using unique key."""
    query_hash = generate_query_hash(user_query)
    cached_data = valkey_client.get(f"query:{query_hash}")
    return json.loads(cached_data.decode("utf-8")) if cached_data else None

# ✅ Function to store queries in Pinecone
def store_query_in_pinecone(user_query, response):
    """Store each query-response pair uniquely in Pinecone."""
    embedding = get_openai_embedding(user_query)
    if not embedding:
        return
    
    query_hash = generate_query_hash(user_query)

    index.upsert(vectors=[
        {
            "id": query_hash,  
            "values": embedding,
            "metadata": {"query": user_query, "response": response}
        }
    ])

# ✅ Function to retrieve queries from Pinecone
def retrieve_from_pinecone(user_query):
    """Retrieve the closest stored query response from Pinecone."""
    embedding = get_openai_embedding(user_query)
    if not embedding:
        return None

    results = index.query(vector=embedding, top_k=3, include_metadata=True)

    if results and results.get("matches"):
        for match in results["matches"]:
            stored_query = match["metadata"].get("query", "")
            if stored_query.lower() == user_query.lower():
                return match["metadata"].get("response", None)

    return None

# ✅ API Route to Handle Queries
@app.route('/query', methods=['POST'])
@limiter.limit("10 per minute")
def handle_query():
    try:
        data = request.json
        user_query = data.get("query")

        if not user_query:
            return jsonify({"error": "Query is required"}), 400

        # ✅ Sanitize input
        user_query = sanitize_input(user_query)
        if user_query is None:
            return jsonify({"error": "Invalid query detected"}), 400

        print(f"📝 New Query Received: {user_query}")

        # ✅ Step 1: Check Cache First
        cached_response = cache_get_response(user_query)
        if cached_response:
            log_to_json(user_query, cached_response, status="cached")
            return jsonify({"response": cached_response})

        # ✅ Step 2: Check Pinecone for Stored Response
        stored_response = retrieve_from_pinecone(user_query)
        if stored_response:
            cache_set_response(user_query, stored_response)  
            log_to_json(user_query, stored_response, status="pinecone")
            return jsonify({"response": stored_response})
        
        # ✅ Step 3: Query OpenAI for New Response
        response = get_openai_response(user_query)
        if not response:
            return jsonify({"error": "Failed to fetch response from OpenAI"}), 500

        store_query_in_pinecone(user_query, response)
        cache_set_response(user_query, response)
        log_to_json(user_query, response)

        return jsonify({"response": response})

    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
