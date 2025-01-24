import openai
import os

# Set your OpenAI API key from an environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

def get_openai_response(query):
    try:
        # Optimize token usage
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=f"Respond briefly to: {query}",
            max_tokens=100,  # Limit response length
            temperature=0.7  # Control creativity
        )
        return response.choices[0].text.strip()
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return "I'm sorry, I encountered an error processing your query."
