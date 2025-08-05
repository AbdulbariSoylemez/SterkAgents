import os
import logging
from typing import List, Dict, Any
from pydantic import BaseModel, Field

# Import ChromaDB and LangChain libraries
import chromadb
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores.chroma import Chroma
from dotenv import load_dotenv

# Load environment variables (e.g., GOOGLE_API_KEY from .env file)
load_dotenv()

# Logger configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Pydantic Models (API Request and Response Structures) ---

class ChunkMetadata(BaseModel):
    """Metadata model for a chunk."""
    video_id: str
    video_title: str
    timestamp_link: str | None = None

class ChunkModel(BaseModel):
    """Model defining the data structure of a single chunk."""
    chunk_index: int
    text: str
    start_ms: int
    end_ms: int
    metadata: ChunkMetadata

class CreateCollectionRequest(BaseModel):
    """Request body model for the /create_collection endpoint."""
    collection_name: str = Field(..., description="The name of the ChromaDB collection to be created. Usually the slugified video title.")
    chunks: List[ChunkModel]
    base_persist_directory: str = Field("./rag_collections", description="The main directory where collections will be saved.")

# --- Vector Database Management Class ---

class RAGVectorStoreManager:
    """
    Class that takes text chunks and creates a persistent vector store in ChromaDB.
    """
    def __init__(self, persist_directory: str):
        """
        Args:
            persist_directory (str): The full path where the ChromaDB collection will be saved to disk.
        """
        if not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("GOOGLE_API_KEY environment variable not found. Please check your .env file.")
        
        self.persist_directory = persist_directory
        
        logger.info("Initializing Google Generative AI embedding model...")
        self.embedding_function = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        logger.info("Embedding model initialized successfully.")
        
        # Configure the Chroma client for persistent storage
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        logger.info(f"ChromaDB client configured for path '{self.persist_directory}'.")

    def create_and_persist_store(self, chunks: List[Dict[str, Any]]):
        """
        Creates the vector store using the given list of chunks and saves it to disk.
        
        Args:
            chunks (List[Dict[str, Any]]): A list of dictionaries, each containing text and metadata.
        """
        if not chunks:
            logger.warning("No chunks found to add to the vector store. Skipping operation.")
            return

        logger.info(f"Creating vector store for '{self.persist_directory}'. Number of chunks to add: {len(chunks)}")

        # Separate texts and metadatas for LangChain's Chroma.from_texts method
        texts = [chunk['text'] for chunk in chunks]
        metadatas = [
            {
                "video_id": chunk['metadata']['video_id'],
                "video_title": chunk['metadata']['video_title'],
                "timestamp_link": chunk['metadata']['timestamp_link'],
                "start_ms": chunk['start_ms'],
                "end_ms": chunk['end_ms'],
                "chunk_index": chunk['chunk_index']
            }
            for chunk in chunks
        ]

        # Create the vector store and save it to the specified path
        # This process creates the embeddings and writes both the embeddings and metadatas to ChromaDB.
        vector_store = Chroma.from_texts(
            texts=texts,
            embedding=self.embedding_function,
            metadatas=metadatas,
            persist_directory=self.persist_directory
        )
        
        logger.info(f"Vector store successfully created and saved to '{self.persist_directory}'.")