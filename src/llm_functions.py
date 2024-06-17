def queryLLM(llm, query):

    def get_response_chunks(query):
        response_chunks = []
        for chunk in llm.stream(query):
            response_chunks.append(chunk)
        return response_chunks

    def print_response_chunks(chunks):
        for chunk in chunks:
            print(chunk, end="", flush=True)
        print("\n")
    
    chunks = get_response_chunks(query)
    print_response_chunks(chunks)