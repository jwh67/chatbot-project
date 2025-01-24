from flask import Flask, request, jsonify
from database.db import create_connection
from openai_integration.openai_utils import get_openai_response
import json

app = Flask(__name__)
conn = create_connection()

# Load predefined intents
with open("intents/responses.json") as f:
    intents = json.load(f)

@app.route('/query', methods=['POST'])
def handle_query():
    data = request.json
    user_query = data.get("query")
    if not user_query:
        return jsonify({"error": "Query is required"}), 400

    cursor = conn.cursor(dictionary=True)
    
    # Step 1: Check MySQL for a cached response
    cursor.execute("SELECT response FROM user_queries WHERE query=%s LIMIT 1", (user_query,))
    result = cursor.fetchone()

    if result:
        # Return cached response
        response = result["response"]
    else:
        # Step 2: Check predefined intents
        response = intents.get(user_query.lower())
        
        if not response:
            # Step 3: Call OpenAI as a fallback
            response = get_openai_response(user_query)
        
        # Log the new query and response in MySQL
        cursor.execute(
            "INSERT INTO user_queries (query, response, intent) VALUES (%s, %s, %s)",
            (user_query, response, None)
        )
        conn.commit()

    return jsonify({"response": response})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
