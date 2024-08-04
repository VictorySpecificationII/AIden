# AIden

AIden is a versatile co-pilot. Inspiration is from a long time ago, in the pre-GPT era.

### Models Used

 - Mistral 7B: The Mistral LLM is a versatile language model, excelling at tasks like reasoning, comprehension, tackling STEM problems, and even coding.
 - Llama-2 7B is produced by Meta AI to specifically target the art of conversation.

## Setup
0. Install:
    ```bash
    sudo apt-get install build-essential python3.10-dev portaudio19-dev
    ```

1. Clone the repository:
    ```bash
    git clone https://github.com/VictorySpecificationII/AIden.git
    cd AIden
    ```

2. Create a virtual environment and activate it:
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3. Install the dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

Run the main script:
```bash
python src/copilot.py
```
Interact with the API at:
```
localhost:8000/docs
```

API documentation at:
```
localhost:8000/redoc
```

In order to run the testing suite, navigate to the root of the project and run:
```bash
pytest
```

# Sources

 - https://nanonets.com/blog/langchain/