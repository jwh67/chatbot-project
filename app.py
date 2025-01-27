from flask import Flask, request, jsonify
from database.db import create_connection
from openai_integration.openai_utils import get_openai_response, get_openai_embedding
from chromadb.config import Settings
import chromadb
import json
import logging
import logging.handlers
import re
from cachetools import TTLCache
from dotenv import load_dotenv
import os
import mysql.connector

# Load environment variables
load_dotenv()

# Flask app initialization
app = Flask(__name__)

# Database configuration from .env
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Connect to the database
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

# Load API keys from the database
VALID_API_KEYS = load_api_keys_from_db()

# Initialize Chroma client
chroma_client = chromadb.Client()
collection = chroma_client.get_or_create_collection(name="chatbot_embeddings")

# Load predefined intents
with open("intents/responses.json") as f:
    intents = json.load(f)

# Configure logging
log_file = "chatbot_logs.json"
logger = logging.getLogger("ChatbotLogger")
logger.setLevel(logging.INFO)
file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)  # 5 MB files
formatter = logging.Formatter('{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Configure cache (max size: 1000 entries, TTL: 3600 seconds)
response_cache = TTLCache(maxsize=1000, ttl=3600)

def log_request(query, response, status="success"):
    """Log the user query and response in JSON format."""
    log_entry = json.dumps({
        "query": query,
        "response": response,
        "status": status,
    })
    logger.info(log_entry)

def sanitize_and_validate_input(user_query):
    """Sanitize and validate the user query to ensure it is safe and appropriate."""
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
    if api_key not in VALID_API_KEYS:
        return False
    return True

@app.route('/query', methods=['POST'])
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

    # Step 2: Check Chroma
    try:
        chroma_results = collection.query(query_texts=[user_query], n_results=1)
        if chroma_results and chroma_results["metadatas"]:
            metadata = chroma_results["metadatas"][0]
            response = metadata.get("response") if metadata else None
        else:
            response = None
    except Exception as e:
        print(f"Error querying ChromaDB: {e}")
        response = None

    # Step 3: Call OpenAI if no cached response
    if not response:
        try:
            response = get_openai_response(user_query)
            embedding = get_openai_embedding(user_query)

            if embedding is None:
                raise ValueError("Failed to generate embedding for the query.")

            # Store embedding in Chroma
            collection.add(
                ids=[user_query],
                documents=[user_query],
                embeddings=[embedding],
                metadatas=[{"response": response}],
            )
        except Exception as e:
            print(f"Error fetching response or embedding from OpenAI: {e}")
            log_request(user_query, "Failed to process query", status="error")
            return jsonify({"error": "Failed to process the query."}), 500

    # Cache the new response
    cache_set_response(user_query, response)

    log_request(user_query, response)
    return jsonify({"response": response})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
