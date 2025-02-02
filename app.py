import os
import json
import logging
import logging.handlers
import re
import mysql.connector
import nltk
import redis
from pinecone import Pinecone, ServerlessSpec
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cachetools import TTLCache
from dotenv import load_dotenv
from openai_integration.openai_utils import get_openai_response, get_openai_embedding

# Ensure NLTK is properly installed
nltk.data.path.append("/home/jeff/nltk_data")

# Load environment variables
load_dotenv()

# Flask app initialization
app = Flask(__name__)

# Rate limiting with Redis
redis_client = redis.Redis(host="localhost", port=6379, db=0)
limiter = Limiter(get_remote_address, app=app, storage_uri="redis://localhost:6379")

# Database configuration
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Pinecone configuration
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX")

# Initialize Pinecone
pc = Pinecone(api_key=PINECONE_API_KEY)

# Define Pinecone Index Name
PINECONE_INDEX = os.getenv("PINECONE_INDEX", "chatbot-index")  # Set default index name

# Check if index exists, otherwise create it
if PINECONE_INDEX not in pc.list_indexes().names():
    print(f"ℹ️ Creating Pinecone index: {PINECONE_INDEX} ...")
    pc.create_index(
        name=PINECONE_INDEX,
        dimension=1536,  # OpenAI embedding size
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-west-2")  # Modify if needed
    )
else:
    print(f"✅ Pinecone index '{PINECONE_INDEX}' already exists.")

# Connect to the existing index
index = pc.Index(PINECONE_INDEX)

# Initialize MySQL connection
def load_api_keys_from_db():
    """Load API keys from the MySQL database."""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT key_value FROM api_keys")
        keys = {row[0] for row in cursor.fetchall()}
        conn.close()
        return keys
    except Exception as e:
        print(f"Error loading API keys: {e}")
        return set()

# Load API keys
VALID_API_KEYS = load_api_keys_from_db()

# Configure logging
log_file = "chatbot_logs.json"
logger = logging.getLogger("ChatbotLogger")
logger.setLevel(logging.INFO)
file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)
formatter = logging.Formatter('{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Configure cache (max size: 1000 entries, TTL: 3600 seconds)
response_cache = TTLCache(maxsize=1000, ttl=3600)

def log_request(query, response, status="success"):
    """Log user queries and responses."""
    log_entry = json.dumps({
        "query": query,
        "response": response,
        "status": status,
    })
    logger.info(log_entry)

def sanitize_and_validate_input(user_query):
    """Sanitize and validate user query to ensure it is safe and appropriate."""
    user_query = user_query.strip()

    if not user_query or len(user_query) < 3:
        return False, "Query must be at least 3 characters long."

    blocked_terms = ["illegal", "hack", "exploit", "bypass", "violate"]
    if any(term in user_query.lower() for term in blocked_terms):
        return False, "Query contains prohibited content."

    user_query = re.sub(r'[^\w\s]', '', user_query)
    return True, user_query

def cache_get_response(key):
    """Retrieve cached response if available."""
    return response_cache.get(key)

def cache_set_response(key, value):
    """Set a response in the cache."""
    response_cache[key] = value

def authenticate_request():
    """Check for a valid API key in the request headers."""
    api_key = request.headers.get("X-API-Key")
    return api_key in VALID_API_KEYS

@app.route('/query', methods=['POST'])
@limiter.limit("10 per minute")
def handle_query():
    # Authenticate the request
    if not authenticate_request():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    user_query = data.get("query")

    # Validate and sanitize user query
    is_valid, sanitized_query = sanitize_and_validate_input(user_query)
    if not is_valid:
        log_request(user_query, sanitized_query, status="failure")
        return jsonify({"error": sanitized_query}), 400

    user_query = sanitized_query  # Use sanitized input moving forward

    # Step 1: Check cache
    cached_response = cache_get_response(user_query)
    if cached_response:
        log_request(user_query, cached_response, status="cached")
        return jsonify({"response": cached_response})

    # Step 2: Generate embedding for Pinecone query
    embedding = get_openai_embedding(user_query)
    if embedding is None:
        return jsonify({"error": "Failed to generate embedding"}), 500

    # Step 3: Query Pinecone using the embedding
    try:
        pinecone_results = index.query(vector=embedding, top_k=1, include_metadata=True)

        if pinecone_results and pinecone_results["matches"]:
            response = pinecone_results["matches"][0]["metadata"]["response"]
        else:
            response = None
    except Exception as e:
        print(f"❌ Error querying Pinecone: {e}")
        response = None

    # Step 4: If no result found, fetch from OpenAI and store in Pinecone
    if not response:
        response = get_openai_response(user_query)

        try:
            index.upsert(vectors=[{
                "id": user_query,  # Ensure ID uniqueness
                "values": embedding,
                "metadata": {"query": user_query, "response": response}
            }])
        except Exception as e:
            print(f"❌ Error inserting into Pinecone: {e}")

    # Cache the new response
    cache_set_response(user_query, response)

    log_request(user_query, response)
    return jsonify({"response": response})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
