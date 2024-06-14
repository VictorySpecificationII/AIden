#AIden

AIden is a versatile co-pilot.

## Features

- Retrieval-augmented generation using LlamaIndex and a language model
- Interacts with external APIs (e.g., weather API)
- Customized to understand personal preferences and information

## Setup

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

4. Set up your API keys and environment variables. Create a `.env` file in the root directory and add your keys:
    ```env
    WEATHER_API_KEY=your_api_key_here
    ```

## Usage

Run the main script:
```bash
python src/copilot.py
```
