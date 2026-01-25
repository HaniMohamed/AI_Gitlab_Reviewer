"""
RAG (Retrieval-Augmented Generation) system for code review.
Handles document loading, vectorization, and retrieval of project guidelines.
"""
import os
import json
from pathlib import Path
from typing import List, Optional
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from config import OLLAMA_BASE_URL

# Default vector store path
VECTOR_STORE_PATH = "./vector_store"
REPO_METADATA_FILE = os.path.join(VECTOR_STORE_PATH, "repo_metadata.json")

def get_embeddings():
    """Get Ollama embeddings instance."""
    return OllamaEmbeddings(base_url=OLLAMA_BASE_URL, model="nomic-embed-text")

def load_documents(data_folder: str) -> List:
    """
    Load documents from a folder.
    Supports: .txt, .md, .pdf files.
    
    Args:
        data_folder: Path to folder containing documents
        
    Returns:
        List of loaded documents
    """
    if not os.path.exists(data_folder):
        raise ValueError(f"Data folder does not exist: {data_folder}")
    
    documents = []
    data_path = Path(data_folder)
    
    # Load text files (including markdown)
    text_files = list(data_path.rglob("*.txt")) + list(data_path.rglob("*.md"))
    for file_path in text_files:
        try:
            loader = TextLoader(str(file_path), encoding="utf-8")
            docs = loader.load()
            documents.extend(docs)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    # Load PDF files
    pdf_files = list(data_path.rglob("*.pdf"))
    for file_path in pdf_files:
        try:
            loader = PyPDFLoader(str(file_path))
            docs = loader.load()
            documents.extend(docs)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    if not documents:
        raise ValueError(f"No documents found in {data_folder}")
    
    return documents

def split_documents(documents: List, chunk_size: int = 1000, chunk_overlap: int = 200) -> List:
    """
    Split documents into chunks for vectorization.
    
    Args:
        documents: List of documents to split
        chunk_size: Size of each chunk
        chunk_overlap: Overlap between chunks
        
    Returns:
        List of document chunks
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    return text_splitter.split_documents(documents)

def create_vector_store(data_folder: str, repo_name: str, vector_store_path: str = VECTOR_STORE_PATH) -> str:
    """
    Create vector store from documents in data folder.
    
    Args:
        data_folder: Path to folder containing documents
        repo_name: Repository name (path_with_namespace) to associate with this vector store
        vector_store_path: Path where vector store will be saved
        
    Returns:
        Success message
    """
    # Load documents
    print(f"Loading documents from {data_folder}...")
    documents = load_documents(data_folder)
    print(f"Loaded {len(documents)} documents")
    
    # Split documents
    print("Splitting documents into chunks...")
    chunks = split_documents(documents)
    print(f"Created {len(chunks)} chunks")
    
    # Create embeddings and vector store
    print("Creating vector store...")
    embeddings = get_embeddings()
    
    # Remove existing vector store if it exists
    if os.path.exists(vector_store_path):
        import shutil
        shutil.rmtree(vector_store_path)
    
    # Create directory if it doesn't exist
    os.makedirs(vector_store_path, exist_ok=True)
    
    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=vector_store_path
    )
    
    # Store repository metadata
    metadata = {
        "repo_name": repo_name,
        "created_at": str(Path().cwd())  # Store creation context
    }
    metadata_file = os.path.join(vector_store_path, "repo_metadata.json")
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Vector store created at {vector_store_path} for repository: {repo_name}")
    return f"✅ Successfully created vector store with {len(chunks)} chunks from {len(documents)} documents for repository: {repo_name}"

def load_vector_store(vector_store_path: str = VECTOR_STORE_PATH) -> Optional[Chroma]:
    """
    Load existing vector store.
    
    Args:
        vector_store_path: Path to vector store
        
    Returns:
        Chroma vector store instance or None if not found
    """
    if not os.path.exists(vector_store_path):
        return None
    
    try:
        embeddings = get_embeddings()
        vector_store = Chroma(
            persist_directory=vector_store_path,
            embedding_function=embeddings
        )
        return vector_store
    except Exception as e:
        print(f"Error loading vector store: {e}")
        return None

def retrieve_relevant_context(query: str, vector_store: Chroma, k: int = 3) -> str:
    """
    Retrieve relevant context from vector store based on query.
    
    Args:
        query: Search query
        vector_store: Chroma vector store instance
        k: Number of documents to retrieve
        
    Returns:
        Combined context string
    """
    if vector_store is None:
        return ""
    
    try:
        docs = vector_store.similarity_search(query, k=k)
        context = "\n\n".join([doc.page_content for doc in docs])
        return context
    except Exception as e:
        print(f"Error retrieving context: {e}")
        return ""

def is_vector_store_available(vector_store_path: str = VECTOR_STORE_PATH) -> bool:
    """
    Check if vector store exists and is available.
    
    Args:
        vector_store_path: Path to vector store
        
    Returns:
        True if vector store is available
    """
    return os.path.exists(vector_store_path) and os.path.isdir(vector_store_path)

def get_stored_repo_name(vector_store_path: str = VECTOR_STORE_PATH) -> Optional[str]:
    """
    Get the repository name stored in the vector store metadata.
    
    Args:
        vector_store_path: Path to vector store
        
    Returns:
        Repository name (path_with_namespace) or None if not found
    """
    metadata_file = os.path.join(vector_store_path, "repo_metadata.json")
    if not os.path.exists(metadata_file):
        return None
    
    try:
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
            return metadata.get("repo_name")
    except Exception as e:
        print(f"Error reading repository metadata: {e}")
        return None

def is_repo_match(current_repo_name: str, vector_store_path: str = VECTOR_STORE_PATH) -> bool:
    """
    Check if the current repository matches the stored repository in vector store.
    
    Args:
        current_repo_name: Current repository name (path_with_namespace)
        vector_store_path: Path to vector store
        
    Returns:
        True if repository matches, False otherwise
    """
    if not is_vector_store_available(vector_store_path):
        return False
    
    stored_repo = get_stored_repo_name(vector_store_path)
    if stored_repo is None:
        return False
    
    return stored_repo == current_repo_name
