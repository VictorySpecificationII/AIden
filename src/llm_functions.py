from langchain_openai import OpenAI

def queryLLM_openAI(query):

    llm = OpenAI()

    def get_response_chunks(query):
        response_chunks = []
        for chunk in llm.stream(query):
            response_chunks.append(chunk)
        return response_chunks

    def concatenate_response_chunks(chunks):
        response_string = "".join(chunks)
        return response_string
    
    chunks = get_response_chunks(query)
    response_string = concatenate_response_chunks(chunks)
    
    return response_string