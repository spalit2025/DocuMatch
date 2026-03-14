"""
Configuration management for DocuMatch Architect.
Uses pydantic-settings for environment variable loading.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Ollama Configuration
    ollama_host: str = "http://localhost:11434"
    default_model: str = "phi3.5"
    fallback_model: str = "llama3.2"

    # ChromaDB Configuration
    chroma_persist_dir: str = "./data/chroma_db"

    # Parser Configuration
    parser_fallback_enabled: bool = True
    max_file_size_mb: int = 50

    # Chunking Configuration
    chunk_size: int = 512
    chunk_overlap: int = 50

    # Embedding Model
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Logging
    log_level: str = "INFO"
    log_file: str = "./logs/documatch.log"

    # Data Directories
    contracts_dir: str = "./data/contracts"
    invoices_dir: str = "./data/invoices"
    purchase_orders_dir: str = "./data/purchase_orders"

    # SQLite Database
    db_path: str = "./data/documatch.db"

    # Three-Way Matching Configuration
    match_tolerance: float = 0.01  # 1% tolerance for amount comparisons

    @property
    def chroma_path(self) -> Path:
        """Get ChromaDB persistence path as Path object."""
        return Path(self.chroma_persist_dir)

    @property
    def contracts_path(self) -> Path:
        """Get contracts directory as Path object."""
        return Path(self.contracts_dir)

    @property
    def invoices_path(self) -> Path:
        """Get invoices directory as Path object."""
        return Path(self.invoices_dir)

    @property
    def purchase_orders_path(self) -> Path:
        """Get purchase orders directory as Path object."""
        return Path(self.purchase_orders_dir)

    @property
    def max_file_size_bytes(self) -> int:
        """Get max file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024


# Global settings instance
settings = Settings()
