from flask import Flask, request, jsonify
from database.db import create_connection
from openai_integration.openai_utils import get_openai_response, get_openai_embedding
from chromadb.config import Settings
import chromadb
import json
import re

# Initialize Flask app
app = Flask(__name__)
conn = create_connection()

# Initialize Chroma client
chroma_client = chromadb.Client()
collection = chroma_client.get_or_create_collection(name="chatbot_embeddings")

# Load predefined intents
with open("intents/responses.json") as f:
    intents = json.load(f)

def sanitize_and_validate_input(user_query):
    """
    Sanitize and validate the user query to ensure it is safe and appropriate.
    """
    # Remove leading/trailing whitespaces
    user_query = user_query.strip()

    # Reject empty or very short queries
    if not user_query or len(user_query) < 3:
        return False, "Query must be at least 3 characters long."

    # Prevent illegal or inappropriate queries using a predefined list of blocked terms
    blocked_terms = ["illegal", "hack", "exploit", "bypass", "violate"]
    if any(term in user_query.lower() for term in blocked_terms):
        return False, "Query contains prohibited content."

    # Additional sanitization (e.g., removing special characters)
    user_query = re.sub(r'[^\w\s]', '', user_query)

    # Return sanitized input and success flag
    return True, user_query

def validate_embedding_dimension(embedding, expected_dim=1536):
    """
    Validate the dimension of the embedding to match the expected dimensionality.
    """
    if len(embedding) != expected_dim:
        raise ValueError(f"Invalid embedding dimension: {len(embedding)}. Expected {expected_dim}.")

@app.route('/query', methods=['POST'])
def handle_query():
    data = request.json
    user_query = data.get("query")

    # Validate and sanitize user query
    is_valid, sanitized_query = sanitize_and_validate_input(user_query)
    if not is_valid:
        return jsonify({"error": sanitized_query}), 400

    user_query = sanitized_query  # Use sanitized input moving forward
    cursor = conn.cursor(dictionary=True)

    # Step 1: Check MySQL for a cached response
    cursor.execute("SELECT response FROM user_queries WHERE query=%s LIMIT 1", (user_query,))
    result = cursor.fetchone()

    if result:
        response = result["response"]
    else:
        # Step 2: Check predefined intents
        response = intents.get(user_query.lower())

        if not response:
            # Step 3: Check Chroma for a cached embedding
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

            if not response:
                # Step 4: Call OpenAI for a new response and embedding
                try:
                    response = get_openai_response(user_query)
                    embedding = get_openai_embedding(user_query)

                    # Prevent adding embeddings with incorrect dimensions
                    if len(embedding) != 1536:  # Replace 1536 with the expected dimension
                        raise ValueError(f"Invalid embedding dimension: {len(embedding)}. Expected 1536.")

                    # Log the embedding dimension for debugging
                    print(f"Generated embedding dimension: {len(embedding)}")

                    # Validate embedding dimension
                    validate_embedding_dimension(embedding)

                    # Store the new embedding and response in Chroma
                    collection.add(
                        ids=[user_query],
                        documents=[user_query],
                        embeddings=[embedding],
                        metadatas=[{"response": response}],
                    )

                    # Log the embedding creation in MySQL
                    cursor.execute(
                        "INSERT INTO embedding_logs (query_text, response) VALUES (%s, %s)",
                        (user_query, response),
                    )
                except ValueError as ve:
                    print(f"Validation Error: {ve}")
                    return jsonify({"error": str(ve)}), 400
                except Exception as e:
                    print(f"Error fetching response or embedding from OpenAI: {e}")
                    return jsonify({"error": "Failed to process the query."}), 500

        # Log the new query and response in MySQL
        cursor.execute(
            "INSERT INTO user_queries (query, response, intent) VALUES (%s, %s, %s)",
            (user_query, response, None),
        )
        conn.commit()

    return jsonify({"response": response})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
