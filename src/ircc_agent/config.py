"""Configuration management for IRCC Agent."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Configuration
    llm_provider: Literal["google", "openai", "anthropic"] = Field(
        default="google",
        description="LLM provider to use",
    )
    google_api_key: str = Field(
        default="",
        description="Google AI API key for Gemini",
    )
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key",
    )
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key",
    )

    # Model settings
    openai_model_name: str = Field(
        default="gpt-5.1",
        description="OpenAI model name to use",
    )
    model_name: str = Field(
        default="gemini-1.5-flash",
        description="Model name to use",
    )
    temperature: float = Field(
        default=0.1,
        description="LLM temperature (lower = more deterministic)",
    )

    # Embedding settings
    embedding_model: str = Field(
        default="models/embedding-001",
        description="Embedding model for vector store",
    )

    # RAG Configuration
    chunk_size: int = Field(
        default=1000,
        description="Size of text chunks for RAG",
    )
    chunk_overlap: int = Field(
        default=200,
        description="Overlap between chunks",
    )
    retrieval_k: int = Field(
        default=5,
        description="Number of documents to retrieve",
    )

    # Paths
    chroma_persist_dir: Path = Field(
        default=Path(".chroma"),
        description="Directory for ChromaDB persistence",
    )
    forms_dir: Path = Field(
        default=Path("forms"),
        description="Directory containing IRCC forms",
    )
    output_dir: Path = Field(
        default=Path("output"),
        description="Directory for filled PDFs",
    )


# Global settings instance
settings = Settings()
