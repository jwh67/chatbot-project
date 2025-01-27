from openai import OpenAI
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI()
client.api_key = os.getenv("OPENAI_API_KEY")  # Ensure the API key is loaded correctly

def get_openai_response(query):
    """
    Get a response from OpenAI's ChatCompletion API using the updated library structure.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": query},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error fetching ChatCompletion: {e}")
        return None

def get_openai_embedding(text):
    """
    Get an embedding for a given text using OpenAI's Embedding API.
    """
    try:
        embedding_response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text,
        )
        return embedding_response.data[0].embedding
    except Exception as e:
        print(f"Error fetching embedding: {e}")
        return None

