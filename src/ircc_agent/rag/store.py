"""Vector store for document embeddings and retrieval."""

import logging
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from ircc_agent.config import settings
from ircc_agent.rag.chunker import chunk_documents

logger = logging.getLogger(__name__)


def get_embeddings() -> Embeddings:
    """Get embeddings model based on configuration.
    
    Supports: google, openai, huggingface (free).
    """
    provider = settings.llm_provider
    
    # Try OpenAI first if key is available (more reliable)
    if settings.openai_api_key:
        try:
            from langchain_openai import OpenAIEmbeddings
            logger.info("Using OpenAI embeddings")
            return OpenAIEmbeddings(
                openai_api_key=settings.openai_api_key,
                model="text-embedding-3-small",
            )
        except Exception as e:
            logger.warning(f"OpenAI embeddings failed: {e}")
    
    # Try Google
    if settings.google_api_key:
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            logger.info("Using Google embeddings")
            return GoogleGenerativeAIEmbeddings(
                model=settings.embedding_model,
                google_api_key=settings.google_api_key,
            )
        except Exception as e:
            logger.warning(f"Google embeddings failed: {e}")
    
    # Fallback to free HuggingFace embeddings (local, no API needed)
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        logger.info("Using free HuggingFace embeddings (local)")
        return HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
    except Exception as e:
        logger.error(f"HuggingFace embeddings failed: {e}")
        raise RuntimeError("No embedding provider available. Set OPENAI_API_KEY or GOOGLE_API_KEY.")


class VectorStore:
    """ChromaDB-based vector store for document retrieval."""

    def __init__(
        self,
        persist_directory: Path | str | None = None,
        collection_name: str = "ircc_documents",
    ):
        """Initialize vector store.

        Args:
            persist_directory: Directory for ChromaDB persistence.
            collection_name: Name of the collection.
        """
        self.persist_directory = Path(persist_directory or settings.chroma_persist_dir)
        self.collection_name = collection_name
        self._embeddings: Embeddings | None = None
        self._vectorstore: Chroma | None = None

    @property
    def embeddings(self) -> Embeddings:
        """Get or create embeddings model."""
        if self._embeddings is None:
            self._embeddings = get_embeddings()
        return self._embeddings

    @property
    def vectorstore(self) -> Chroma:
        """Get or create vector store."""
        if self._vectorstore is None:
            self._vectorstore = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embeddings,
                persist_directory=str(self.persist_directory),
            )
        return self._vectorstore

    def add_documents(
        self,
        documents: list[Document],
        chunk: bool = True,
    ) -> list[str]:
        """Add documents to the vector store.

        Args:
            documents: Documents to add.
            chunk: Whether to chunk documents before adding.

        Returns:
            List of document IDs.
        """
        if chunk:
            documents = chunk_documents(documents)

        ids = self.vectorstore.add_documents(documents)
        logger.info(f"Added {len(ids)} document chunks to vector store")
        return ids

    def similarity_search(
        self,
        query: str,
        k: int | None = None,
    ) -> list[Document]:
        """Search for similar documents.

        Args:
            query: Search query.
            k: Number of results to return.

        Returns:
            List of matching documents.
        """
        k = k or settings.retrieval_k
        results = self.vectorstore.similarity_search(query, k=k)
        return results

    def similarity_search_with_score(
        self,
        query: str,
        k: int | None = None,
    ) -> list[tuple[Document, float]]:
        """Search for similar documents with relevance scores.

        Args:
            query: Search query.
            k: Number of results to return.

        Returns:
            List of (document, score) tuples.
        """
        k = k or settings.retrieval_k
        results = self.vectorstore.similarity_search_with_score(query, k=k)
        return results

    def get_retriever(self, k: int | None = None) -> Any:
        """Get a retriever for use with LangChain chains.

        Args:
            k: Number of documents to retrieve.

        Returns:
            LangChain retriever.
        """
        k = k or settings.retrieval_k
        return self.vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k},
        )

    def clear(self) -> None:
        """Clear all documents from the vector store."""
        # Delete the collection and recreate it
        self.vectorstore.delete_collection()
        self._vectorstore = None
        logger.info("Cleared vector store")

    @property
    def count(self) -> int:
        """Get the number of documents in the store."""
        return self.vectorstore._collection.count()
