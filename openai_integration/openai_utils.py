import openai

# Set your OpenAI API key
openai.api_key = "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"

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
