# AIden

AIden is a versatile co-pilot. Inspiration is from a long time ago, in the pre-GPT era.

## Features

- Retrieval-augmented generation using LlamaIndex and LangChain.
- Interacts with external APIs (e.g., weather API)
- Customized to understand personal preferences and information
- Multimodal:
    - Access to camera for vision capabilities
    - Access to microphone for hearing capabilities
    - Access to sensors for sensory input
- Portable, can run on the edge
- Offline capabilities (text/voice only)

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

4. Set up your API keys and environment variables. Create a copy of the `env` file in the root directory, name it `.env` and add your keys:
    ```env
    WEATHER_API_KEY=your_api_key_here
    ```

## Usage

Run the main script:
```bash
python src/copilot.py
```

In order to run the testing suite, navigate to the root of the project and run:
```bash
pytest
```
# Sources

 - https://nanonets.com/blog/langchain/
 - https://github.com/KoljaB/RealtimeSTT for the real time speech transcription module