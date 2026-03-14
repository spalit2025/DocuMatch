"""
FastAPI dependency injection for DocuMatch Architect.

Creates and caches service instances shared across requests.
Uses functools.lru_cache for singleton behavior.
"""

from functools import lru_cache

from config import settings
from core.extraction import ExtractionEngine
from core.matcher import Matcher
from core.parser_engine import ParserEngine
from core.po_store import POStore
from core.services import DocumentService, MatchService
from core.vector_store import VectorStore


@lru_cache
def get_parser() -> ParserEngine:
    return ParserEngine(fallback_enabled=settings.parser_fallback_enabled)


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore(
        persist_directory=str(settings.chroma_path),
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )


@lru_cache
def get_po_store() -> POStore:
    return POStore(persist_directory=str(settings.chroma_path))


@lru_cache
def get_extraction_engine() -> ExtractionEngine:
    return ExtractionEngine(
        model=settings.default_model,
        ollama_host=settings.ollama_host,
    )


@lru_cache
def get_matcher() -> Matcher:
    return Matcher(
        vector_store=get_vector_store(),
        po_store=get_po_store(),
        ollama_host=settings.ollama_host,
        model=settings.default_model,
    )


@lru_cache
def get_document_service() -> DocumentService:
    return DocumentService(
        parser=get_parser(),
        vector_store=get_vector_store(),
        po_store=get_po_store(),
        extraction_engine=get_extraction_engine(),
    )


@lru_cache
def get_match_service() -> MatchService:
    return MatchService(matcher=get_matcher())
