import os
from dotenv import load_dotenv

def load_secrets():
    try:
        # Load environment variables from .env file
        load_dotenv()

        # Access environment variables
        api_key = os.getenv("OPENAI_API_KEY")

        if api_key is None:
            raise ValueError("OPENAI_API_KEY not found in environment variables. Ensure it's set in your .env file.")

        print("Boot: Secrets loaded.")
        return True

    except Exception as e:
        print(f"Boot Error: {str(e)}")
        return False