# I want AIden to be able to work with information from various sources
import os
from langchain.document_loaders import TextLoader
from langchain.document_loaders.csv_loader import CSVLoader
from langchain.document_loaders import PyPDFLoader

directory="./data/raw"

def load_txt_files(directory):
    documents = []
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            file_path = os.path.join(directory, filename)
            loader = TextLoader(file_path)
            documents.extend(loader.load())
    return documents

def load_csv_files(directory):
    documents = []
    for filename in os.listdir(directory):
        if filename.endswith(".csv"):
            file_path = os.path.join(directory, filename)
            loader = CSVLoader(file_path)
            documents.extend(loader.load())
    return documents

def load_pdf_files(directory):
    documents = []
    for filename in os.listdir(directory):
        if filename.endswith(".pdf"):
            file_path = os.path.join(directory, filename)
            loader = PyPDFLoader(file_path)
            pages = loader.load_and_split()
            documents.extend(pages)
    return documents
