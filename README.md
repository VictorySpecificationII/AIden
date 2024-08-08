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

Launch a terminal, copy the docker command in the monitoring/README.md file and execute it. 
```
IMPORTANT: The app won't run without it.
```

Run the main script, in another terminal:
```bash
python src/aiden.py
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
In order to run the linter, pylint, run it from the main project directory otherwise some odd recomendations might come up

```bash
pylint src/NAME_OF_FILE_TO_LINT
```

The pylint file, should you wish to modify it is in the project root, named .pylintrc

# Todo

Some of the things that I want to do, not an exhaustive list.

- [x] Instrument LLM API's
- [x] Write better exception handling
- [x] Encapsulate LLM library in class, call functions in libraries via dependency injection in API's for better segmentation
- [ ] Modify LLM API to allow downloading, inventory and loading of any model as opposed to current implementation
- [ ] Build a frontend (voice and text)
- [ ] Incorporate chat history
- [ ] Build LLM agents

# Sources

 - https://nanonets.com/blog/langchain/