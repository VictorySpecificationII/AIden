# I want AIden to be able to work with information from various sources
import os
from langchain.document_loaders import TextLoader

directory="./data/raw"

def load_txt_files(directory):
    documents = []
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            file_path = os.path.join(directory, filename)
            loader = TextLoader(file_path)
            documents.extend(loader.load())
    return documents