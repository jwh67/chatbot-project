from flask import Flask, request, jsonify
from database.db import create_connection
from openai_integration.openai_utils import get_openai_response
import json
import logging

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Initialize database connection
try:
    conn = create_connection()
    logging.info("Connected to MySQL database successfully.")
except Exception as e:
    logging.error(f"Failed to connect to MySQL: {e}")
    conn = None

# Load predefined intents
try:
    with open("intents/responses.json") as f:
        intents = json.load(f)
    logging.info("Loaded intents from intents/responses.json.")
except FileNotFoundError:
    logging.error("Intents file not found. Ensure intents/responses.json exists.")
    intents = {}

@app.route('/query', methods=['POST'])
def handle_query():
    try:
        # Parse user query
        data = request.json
        user_query = data.get("query")
        if not user_query:
            logging.warning("Empty query received.")
            return jsonify({"error": "Query is required"}), 400
        logging.info(f"Received user query: {user_query}")

        # Step 1: Check MySQL for a cached response
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT response FROM user_queries WHERE query=%s LIMIT 1", (user_query,))
        result = cursor.fetchone()

        if result:
            response = result["response"]
            logging.info(f"Found cached response: {response}")
        else:
            # Step 2: Check predefined intents
            response = intents.get(user_query.lower())
            if response:
                logging.info(f"Matched predefined intent response: {response}")
            else:
                # Step 3: Call OpenAI as a fallback
                logging.info("No match in database or intents. Using OpenAI API.")
                response = get_openai_response(user_query)

            # Log the new query and response in MySQL
            cursor.execute(
                "INSERT INTO user_queries (query, response, intent) VALUES (%s, %s, %s)",
                (user_query, response, None)
            )
            conn.commit()
            logging.info("Logged new query and response in MySQL.")

        return jsonify({"response": response})

    except Exception as e:
        logging.error(f"Unexpected error in /query: {e}")
        return jsonify({"response": f"Unexpected error: {e}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
