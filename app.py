from flask import Flask, request, jsonify
from openai_integration.openai_utils import get_openai_response, get_openai_embedding
import json
import logging
import os
import hashlib
import redis  # ✅ Valkey uses Redis API
import re
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv
from pinecone import Pinecone
from datetime import datetime, timezone
from textblob import TextBlob  # ✅ For spell-checking & sentiment analysis
import nltk
from nltk.corpus import wordnet
from flask import Flask
from flask_cors import CORS

# ✅ Load environment variables
load_dotenv()

# ✅ Initialize Flask app
app = Flask(__name__)
CORS(app, resources={r"/query": {"origins": "http://localhost:5174"}})

# ✅ Configure Rate Limiter using Valkey (Redis API)
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="redis://localhost:6379",
    default_limits=["10 per minute"]
)

# ✅ Initialize Valkey (Using Redis API)
valkey_client = redis.Redis(host="localhost", port=6379, db=0)
CACHE_TTL = 3600  # Cache responses for 1 hour

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
    log_dir = "/home/jeff/devops/aiml1/chatbot-api/logs"
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return os.path.join(log_dir, f"chatbot_logs_{today}.json")

# ✅ Function to write logs to a JSON file (Daily Rotation)
def log_to_json(user_query, response, sentiment, status="success"):
    log_entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "query": user_query,
        "response": response,
        "sentiment": sentiment,
        "status": status
    }

    log_file = get_log_filename()
    
    try:
        with open(log_file, "a", encoding="utf-8") as file:
            json.dump(log_entry, file, ensure_ascii=False)
            file.write("\n")
        print("✅ Logged query to JSON file.")
    except Exception as e:
        print(f"❌ Failed to write to chatbot JSON log: {e}")

# ✅ Function to analyze sentiment
def analyze_sentiment(user_query):
    """Analyze sentiment of the query."""
    blob = TextBlob(user_query)
    return blob.sentiment.polarity  # Returns sentiment score between -1 (negative) to +1 (positive)

# ✅ Function to correct spelling
def correct_spelling(user_query):
    """Correct spelling mistakes in user query using TextBlob."""
    blob = TextBlob(user_query)
    corrected_query = str(blob.correct())  # Auto-corrects misspelled words
    return corrected_query

# ✅ Function to sanitize user input
def sanitize_input(user_query):
    user_query = user_query.strip()
    user_query = re.sub(r"[^a-zA-Z0-9,.'?\"\s]", "", user_query)  # Allow valid quotes
    user_query = user_query.replace('"', '\\"')  # Escape quotes to prevent JSON errors
    
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
    query_hash = generate_query_hash(user_query)
    valkey_client.setex(f"query:{query_hash}", CACHE_TTL, json.dumps(response, ensure_ascii=False))

# ✅ Function to retrieve responses from Valkey (Cache)
def cache_get_response(user_query):
    query_hash = generate_query_hash(user_query)
    cached_data = valkey_client.get(f"query:{query_hash}")
    return json.loads(cached_data.decode("utf-8")) if cached_data else None

# ✅ Function to store queries in Pinecone
def store_query_in_pinecone(user_query, response):
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

        # ✅ Preserve original query to avoid unnecessary alterations
        original_query = user_query

        # ✅ Spell-check & correct query
        corrected_query = correct_spelling(user_query)
        if corrected_query.lower() != user_query.lower():
            print(f"📝 Spell-corrected Query: {corrected_query}")
            user_query = corrected_query

        # ✅ Analyze sentiment
        sentiment = analyze_sentiment(user_query)
        print(f"📊 Sentiment Score: {sentiment}")

        # ✅ Sanitize input
        user_query = sanitize_input(user_query)
        if user_query is None:
            return jsonify({"error": "Invalid query detected"}), 400

        print(f"📝 Final Query Sent to OpenAI: {user_query}")

        # ✅ Step 1: Check Cache First
        cached_response = cache_get_response(user_query)
        if cached_response:
            return jsonify({"response": cached_response})

        # ✅ Step 2: Check Pinecone for Stored Response
        stored_response = retrieve_from_pinecone(user_query)
        if stored_response:
            cache_set_response(user_query, stored_response)
            return jsonify({"response": stored_response})

        # ✅ Step 3: Query OpenAI for New Response
        # Improve accuracy for factual/geographic queries
        geo_keywords = ["where is", "elevation of", "location of", "map of", "distance to"]
        if any(keyword in user_query.lower() for keyword in geo_keywords):
            print("🌍 Detected a geographical query, enforcing accuracy.")
            user_query = f"Provide the exact geographical information for: {original_query}. Use reliable sources."

        openai_instruction = (
            "You are a highly accurate chatbot. Respond with correct and factual information. "
            "Strictly follow the query's wording. Do not alter names or interpret differently. "
            "If unsure, respond with 'I do not have the exact data.' rather than guessing. "
        )

        response = get_openai_response(openai_instruction + user_query)

        # ✅ Validate response before caching
        unlikely_responses = ["Camp Provide", "I do not know", "I'm not sure"]
        if any(term in response for term in unlikely_responses):
            print(f"⚠️ OpenAI returned an unlikely response: {response}. Re-querying with refined input...")
            response = get_openai_response(openai_instruction + f"Provide factual location-based information for: {original_query}")

        # ✅ Store in Pinecone & Cache
        store_query_in_pinecone(user_query, response)
        cache_set_response(user_query, response)

        return jsonify({"response": response})

    except Exception as e:
        return jsonify({"error": f"Unexpected error: {e}"}), 500



if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
