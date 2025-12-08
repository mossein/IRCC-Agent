"""Text chunking utilities for RAG pipeline."""

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from ircc_agent.config import settings


def create_text_splitter(
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> RecursiveCharacterTextSplitter:
    """Create a text splitter with configured settings.

    Args:
        chunk_size: Override default chunk size.
        chunk_overlap: Override default chunk overlap.

    Returns:
        Configured text splitter.
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or settings.chunk_size,
        chunk_overlap=chunk_overlap or settings.chunk_overlap,
        length_function=len,
        is_separator_regex=False,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def chunk_documents(
    documents: list[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Document]:
    """Split documents into smaller chunks for embedding.

    Args:
        documents: List of documents to chunk.
        chunk_size: Optional override for chunk size.
        chunk_overlap: Optional override for chunk overlap.

    Returns:
        List of chunked documents.
    """
    splitter = create_text_splitter(chunk_size, chunk_overlap)
    chunks = splitter.split_documents(documents)
    return chunks
