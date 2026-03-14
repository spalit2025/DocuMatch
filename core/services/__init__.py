"""
Service Layer for DocuMatch Architect.

Provides orchestration services that coordinate core modules.
Both Streamlit UI and FastAPI endpoints consume this layer.

Architecture:
    ┌──────────────┐   ┌──────────────┐
    │ Streamlit UI  │   │  FastAPI      │
    └──────┬───────┘   └──────┬───────┘
           │                   │
           └───────┬───────────┘
                   ▼
           ┌──────────────────┐
           │ Service Layer     │
           │  DocumentService  │
           │  MatchService     │
           └───────┬──────────┘
                   ▼
           ┌──────────────────┐
           │ Core Modules      │
           │  Parser, Extract, │
           │  VectorStore, etc │
           └──────────────────┘
"""

from .batch_service import BatchFile, BatchService, BatchStatus
from .document_service import DocumentService, DocumentProcessingError
from .match_service import MatchService

__all__ = [
    "BatchFile",
    "BatchService",
    "BatchStatus",
    "DocumentService",
    "DocumentProcessingError",
    "MatchService",
]
