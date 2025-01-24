from openai import OpenAI
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Create an OpenAI client instance
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_openai_response(query):
    try:
        # Correct usage with the OpenAI client
        response = client.chat.completions.create(
            model="gpt-4",  # Replace with "gpt-4" if available in your plan
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": query},
            ],
            max_tokens=150,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()

    # Handle specific OpenAI errors
    except client.error.AuthenticationError as e:
        print(f"Authentication error: {e}")
        return "Authentication error: Please check your API key."
    except client.error.RateLimitError as e:
        print(f"Rate limit error: {e}")
        return "Rate limit error: You've exceeded your usage limit."
    except client.error.OpenAIError as e:
        print(f"OpenAI API error: {e}")
        return f"OpenAI API error: {e}"
    except Exception as e:
        # Handle any unexpected errors
        print(f"Unexpected error: {e}")
        return f"Unexpected error: {e}"



