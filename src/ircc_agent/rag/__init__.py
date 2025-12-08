"""RAG (Retrieval-Augmented Generation) module for document processing."""

from ircc_agent.rag.loader import DocumentLoader, load_documents_from_directory
from ircc_agent.rag.store import VectorStore

__all__ = ["DocumentLoader", "VectorStore", "load_documents_from_directory"]
