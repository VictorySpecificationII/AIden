# Function to generate an answer from the LLM in question
generate_response() {
  local model="$1"
  local prompt="$2"
  local stream="$3"
  local url="http://localhost:11434/api/generate"
  
  curl -X POST "$url" -d "{
    \"model\": \"$model\", 
    \"prompt\": \"$prompt\", 
    \"stream\": $stream
  }"
}

# Main interactive loop
echo "Welcome to the interactive CLI chat. Type 'exit' or 'quit' to leave."

while true; do
    # Prompt the user for input
    read -p "You: " user_input

    # Check if the user wants to exit
    if [[ "$user_input" == "exit" || "$user_input" == "quit" ]]; then
        echo "Exiting chat. Goodbye!"
        break
    fi

    # Query the Ollama container and get the response
    echo "Querying the Ollama container..."
    generate_response "smollm:135m" "$user_input" false   # true for streaming, false to disable

    # Display the response from Ollama
    echo "Ollama: $response"
done

