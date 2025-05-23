from flask import Flask, request, jsonify
from openai_integration.openai_utils import get_openai_response, get_openai_embedding
import json
import html
import logging
import os
import random 
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
from flask_cors import CORS
import difflib # ✅ For fuzzy matching

# ✅ Prevent "unused" warning from Pylance
_ = get_openai_embedding

# ✅ Load environment variables
load_dotenv()

# ✅ Load intents and responses at app start
with open("data/intents.json", "r", encoding="utf-8") as f:
    intent_data = json.load(f)
    intents = intent_data.get("intents", [])

with open("data/responses.json", "r", encoding="utf-8") as f:
    responses = json.load(f)

# ✅ Download necessary NLTK data
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')
nltk.download('wordnet')

# ✅ Initialize Flask app
app = Flask(__name__)
CORS(app, resources={r"/query": {"origins": "*"}})

# ✅ Configure Rate Limiter using Valkey (Redis API)
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="redis://localhost:6379",
    default_limits=["10 per minute"]
)

# ✅ Initialize Valkey
valkey_client = redis.Redis(host="localhost", port=6379, db=0)
CACHE_TTL = 3600  # 1 hour

# ✅ Initialize Pinecone
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX", "chatbot-embeddings")
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(name=PINECONE_INDEX_NAME)

if PINECONE_INDEX_NAME not in pc.list_indexes().names():
    print(f"ℹ️ Creating Pinecone index: {PINECONE_INDEX_NAME} ...")
    pc.create_index(name=PINECONE_INDEX_NAME, dimension=3072, metric="cosine")
else:
    print(f"✅ Pinecone index '{PINECONE_INDEX_NAME}' already exists.")

# ✅ Logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

def get_log_filename():
    log_dir = "/home/jeff/devops/aiml1/chatbot-api/logs"
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return os.path.join(log_dir, f"chatbot_logs_{today}.json")

def log_to_json(user_query, response, source, status="success"):
    log_entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "query": user_query,
        "response": response,
        "source": source,
        "status": status
    }

    try:
        with open(get_log_filename(), "a", encoding="utf-8") as file:
            json.dump(log_entry, file, ensure_ascii=False)
            file.write("\n")
        print("✅ Logged query to JSON file.")
    except Exception as e:
        print(f"❌ Failed to write to chatbot JSON log: {e}")

def analyze_sentiment(user_query):
    blob = TextBlob(user_query)
    return blob.sentiment.polarity  # Between -1 and +1

def correct_spelling(user_query):
    blob = TextBlob(user_query)
    return str(blob.correct())  # Suggested correction (not used for query)

def get_synonyms(word):
    synonyms = set()
    for syn in wordnet.synsets(word):
        for lemma in syn.lemmas():
            synonyms.add(lemma.name())
    return list(synonyms)

def sanitize_input(user_query):
    if not isinstance(user_query, str):
        return None
    user_query = user_query.strip()
    user_query = html.escape(user_query)
    user_query = re.sub(r"[^a-zA-Z0-9,.'?\"\s]", "", user_query)
    user_query = re.sub(r"(--|;|'|\"|DROP|ALTER|INSERT|DELETE|UPDATE|SELECT|UNION)", "", user_query, flags=re.IGNORECASE)
    return user_query

def generate_query_hash(user_query):
    return hashlib.md5(user_query.encode()).hexdigest()

def cache_set_response(user_query, response):
    query_hash = generate_query_hash(user_query)
    valkey_client.setex(f"query:{query_hash}", CACHE_TTL, json.dumps(response, ensure_ascii=False))

def cache_get_response(user_query):
    query_hash = generate_query_hash(user_query)
    cached_data = valkey_client.get(f"query:{query_hash}")
    return json.loads(cached_data.decode("utf-8")) if cached_data else None

def store_query_in_pinecone(user_query, response):
    embedding = get_openai_embedding(user_query)
    if not embedding:
        return
    query_hash = generate_query_hash(user_query)
    index.upsert(vectors=[{
        "id": query_hash,
        "values": embedding,
        "metadata": {"query": user_query, "response": response}
    }])

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

@app.route('/query', methods=['POST'])
@limiter.limit("10 per minute")
def handle_query():
    try:
        data = request.get_json(force=True)
        user_query = data.get("query")

        if not user_query:
            return jsonify({"error": "Query is required"}), 400

        user_query = sanitize_input(user_query)
        if user_query is None:
            return jsonify({"error": "Invalid or blocked query."}), 400

        sentiment = analyze_sentiment(user_query)
        suggested_query = correct_spelling(user_query)
        synonyms = get_synonyms(user_query)
        user_query_lower = user_query.lower()

        # ✅ intent_keywords required for scoring & fallback
        intent_keywords = {
            "greeting": ["hi", "hello", "hey", "greetings"],
            "goodbye": ["bye", "goodbye", "see you", "later"],
            "hours": ["open", "close", "hours", "when are you", "time"],
            "services": ["services", "support", "chat", "call center", "help desk"],
            "languages": ["languages", "speak", "Spanish", "French", "Filipino"],
            "location": ["location", "office", "where", "address"],
            "pricing": ["pricing", "cost", "charge", "rate", "how much"],
            "support": ["assist", "help", "issue"],
            "agent": ["human", "agent", "representative", "live person"]
        }

        # ✅ Step 1: Check Cache
        cached_response = cache_get_response(user_query)
        if cached_response:
            log_to_json(user_query, cached_response, "cache", "success")
            return jsonify({
                "response": cached_response,
                "sentiment": sentiment,
                "suggested_query": suggested_query,
                "synonyms": synonyms
            })

        # ✅ Step 2a: Intent Matching (fuzzy + keywords)
        print(f"\n🧪 Incoming query: {user_query_lower}")
        best_score = 0.0
        matched_tag = None

        for intent in intents:
            tag = intent.get("tag")
            print(f"📂 Checking intent: {tag}")
            for pattern in intent.get("patterns", []):
                print(f"   🔸 Pattern: {pattern}")
                pattern_lower = pattern.lower()
                score = difflib.SequenceMatcher(None, user_query_lower, pattern_lower).ratio()

                if any(word in user_query_lower for word in intent_keywords.get(tag, [])):
                    score += 0.15

                if score > best_score:
                    best_score = score
                    matched_tag = tag

                if pattern_lower in user_query_lower or user_query_lower in pattern_lower:
                    best_score = 1.0
                    matched_tag = tag
                    break

        print(f"🔍 Best fuzzy match score: {best_score}, matched tag: {matched_tag}")

        if matched_tag and best_score >= 0.5:
            matched_response = responses.get(matched_tag)
            if isinstance(matched_response, list):
                matched_response = random.choice(matched_response)
            elif not matched_response:
                matched_response = "I'm not sure how to respond to that."

            print(f"DEBUG: ✅ Intent matched - tag='{matched_tag}' with score={round(best_score, 2)}")
            log_to_json(user_query, matched_response, "intent", f"matched@{round(best_score, 2)}")
            return jsonify({
                "response": matched_response,
                "sentiment": sentiment,
                "suggested_query": suggested_query,
                "synonyms": synonyms
            })

        # ✅ Step 2b: Keyword fallback
        for tag, keywords in intent_keywords.items():
            for word in keywords:
                if word.lower() in user_query_lower:
                    matched_response = responses.get(tag, "I'm not sure how to respond to that.")
                    if isinstance(matched_response, list):
                        matched_response = random.choice(matched_response)

                    print(f"DEBUG: ⚠️ Keyword-only fallback matched tag='{tag}' via word='{word}'")
                    log_to_json(user_query, matched_response, "intent", "keyword fallback")
                    return jsonify({
                        "response": matched_response,
                        "sentiment": sentiment,
                        "suggested_query": suggested_query,
                        "synonyms": synonyms
                    })

        # ✅ Step 3: Pinecone check
        stored_response = retrieve_from_pinecone(user_query)
        if stored_response:
            cache_set_response(user_query, stored_response)
            log_to_json(user_query, stored_response, "pinecone", "success")
            return jsonify({
                "response": stored_response,
                "sentiment": sentiment,
                "suggested_query": suggested_query,
                "synonyms": synonyms
            })

        # ✅ Step 4: Query OpenAI
        response = get_openai_response(user_query)
        response = response if isinstance(response, str) else "⚠️ Unexpected response format."

        # ✅ Store and Log
        store_query_in_pinecone(user_query, response)
        cache_set_response(user_query, response)
        log_to_json(user_query, response, "openai", "success")

        return jsonify({
            "response": response,
            "sentiment": sentiment,
            "suggested_query": suggested_query,
            "synonyms": synonyms
        })

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON format: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
