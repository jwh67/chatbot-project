import os
import json
import logging
import logging.handlers
import re
import mysql.connector
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from cachetools import TTLCache
from openai_integration.openai_utils import get_openai_response, get_openai_embedding
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
from weaviate.classes.config import Configure, Property, DataType

# Load environment variables
load_dotenv()

# Flask app initialization
app = Flask(__name__)

# Database configuration from .env
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

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

# Load API keys from the database
VALID_API_KEYS = load_api_keys_from_db()

# Initialize Weaviate client (v4)
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
connection_params = ConnectionParams.from_url(WEAVIATE_URL, grpc_port=50051)
client = WeaviateClient(connection_params=connection_params)

# Ensure Weaviate connection is active
try:
    client.connect()
    print("✅ Weaviate client connected successfully.")
except Exception as e:
    print(f"❌ Error connecting to Weaviate: {e}")
    exit(1)

# Define collection name
collection_name = "ChatbotEmbeddings"

# Ensure collection exists
if not client.collections.exists(collection_name):
    print(f"ℹ️ Creating collection: {collection_name} in Weaviate...")
    client.collections.create(
        name=collection_name,
        vectorizer_config=Configure.Vectorizer.text2vec_openai(),  # Corrected vectorizer config
        properties=[
            Property(name="query", data_type=DataType.TEXT),
            Property(name="response", data_type=DataType.TEXT),
        ]
    )
else:
    print(f"✅ Weaviate collection '{collection_name}' already exists.")

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

    # Step 2: Generate embedding for Weaviate query
    embedding = get_openai_embedding(user_query)
    if embedding is None:
        return jsonify({"error": "Failed to generate embedding"}), 500

    # Step 3: Query Weaviate using near_vector
    try:
        result = client.collections.get(collection_name).query.near_vector(
            near_vector=embedding,
            limit=1,
            return_properties=["query", "response"]
        )
        
        # ✅ **Fix: Access properties properly**
        if result.objects:
            response = result.objects[0].properties["response"]  # ✅ **Correct way to access properties**
        else:
            response = None
    except Exception as e:
        print(f"❌ Error querying Weaviate: {e}")
        response = None

    # Step 4: If no result found, fetch from OpenAI and store in Weaviate
    if not response:
        response = get_openai_response(user_query)

        try:
            client.collections.get(collection_name).data.insert(
                properties={"query": user_query, "response": response},
                vector=embedding
            )
        except Exception as e:
            print(f"❌ Error inserting into Weaviate: {e}")

    # Cache the new response
    cache_set_response(user_query, response)

    log_request(user_query, response)
    return jsonify({"response": response})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
