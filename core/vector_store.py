"""
Vector Store for DocuMatch Architect.

Manages contract clause storage and retrieval using ChromaDB
with local embeddings via FastEmbed.
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import List, Optional
from datetime import datetime

import chromadb
from chromadb.config import Settings as ChromaSettings

from .exceptions import StoreError
from .models import RetrievedClause


def normalize_vendor_name(name: str) -> str:
    """
    Normalize vendor name for consistent matching.

    Handles common variations:
    - Trailing punctuation (Inc. vs Inc)
    - Extra whitespace
    - Case differences
    """
    if not name:
        return ""
    # Strip whitespace and trailing punctuation
    normalized = name.strip().rstrip('.,;:')
    # Normalize internal whitespace
    normalized = ' '.join(normalized.split())
    return normalized

# Configure logging
logger = logging.getLogger(__name__)


class VectorStore:
    """
    ChromaDB-based vector store for contract clauses.

    Stores contract text chunks with embeddings for semantic search,
    organized by vendor name for efficient retrieval.

    Usage:
        store = VectorStore(persist_directory="./data/chroma_db")
        store.index_contract(markdown_text, "VendorA")
        clauses = store.retrieve_clauses("VendorA", "payment terms")
    """

    COLLECTION_NAME = "contracts"

    def __init__(
        self,
        persist_directory: str = "./data/chroma_db",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ):
        """
        Initialize the vector store.

        Args:
            persist_directory: Path for ChromaDB persistence
            embedding_model: Model name for FastEmbed
            chunk_size: Target size for text chunks (characters)
            chunk_overlap: Overlap between chunks (characters)
        """
        self.persist_directory = Path(persist_directory)
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Ensure directory exists
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client with persistence
        self._client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Get or create collection with embedding function
        self._collection = self._get_or_create_collection()

        logger.info(f"VectorStore initialized at {self.persist_directory}")

    def _get_or_create_collection(self):
        """Get or create the contracts collection."""
        try:
            collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            return collection
        except (ConnectionError, OSError) as e:
            raise StoreError(f"ChromaDB infrastructure error: {e}") from e
        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise StoreError(f"Failed to initialize vector store collection: {e}") from e

    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks.

        Uses sentence boundaries when possible for better semantic coherence.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []

        # Clean the text
        text = text.strip()

        # Split by paragraphs first (double newlines)
        paragraphs = re.split(r'\n\s*\n', text)

        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If paragraph fits in remaining chunk space, add it
            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                # Save current chunk if it has content
                if current_chunk:
                    chunks.append(current_chunk)

                # If paragraph is larger than chunk size, split it
                if len(para) > self.chunk_size:
                    # Split by sentences
                    sentences = re.split(r'(?<=[.!?])\s+', para)
                    current_chunk = ""

                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) + 1 <= self.chunk_size:
                            if current_chunk:
                                current_chunk += " " + sentence
                            else:
                                current_chunk = sentence
                        else:
                            if current_chunk:
                                chunks.append(current_chunk)
                            # If single sentence is too long, force split
                            if len(sentence) > self.chunk_size:
                                for i in range(0, len(sentence), self.chunk_size - self.chunk_overlap):
                                    chunks.append(sentence[i:i + self.chunk_size])
                                current_chunk = ""
                            else:
                                current_chunk = sentence
                else:
                    current_chunk = para

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk)

        # Add overlap between chunks (for context continuity)
        if self.chunk_overlap > 0 and len(chunks) > 1:
            overlapped_chunks = []
            for i, chunk in enumerate(chunks):
                if i > 0:
                    # Get overlap from previous chunk
                    prev_overlap = chunks[i - 1][-self.chunk_overlap:]
                    chunk = prev_overlap + " " + chunk
                overlapped_chunks.append(chunk)
            chunks = overlapped_chunks

        return chunks

    def index_contract(
        self,
        text: str,
        vendor_name: str,
        contract_type: str = "general",
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Index a contract's text into the vector store.

        Args:
            text: The full contract text (markdown)
            vendor_name: Name of the vendor (for filtering)
            contract_type: Type of contract (MSA, SOW, etc.)
            metadata: Additional metadata to store

        Returns:
            contract_id: Unique identifier for this contract
        """
        if not text or not text.strip():
            raise ValueError("Cannot index empty text")

        if not vendor_name or not vendor_name.strip():
            raise ValueError("Vendor name is required")

        # Generate contract ID
        contract_id = self._generate_contract_id(vendor_name, text)

        # Check if already indexed
        existing = self._collection.get(
            where={"contract_id": contract_id}
        )
        if existing and existing["ids"]:
            logger.info(f"Contract {contract_id} already indexed, updating...")
            # Delete existing chunks for this contract
            self._collection.delete(
                where={"contract_id": contract_id}
            )

        # Chunk the text
        chunks = self.chunk_text(text)

        if not chunks:
            raise ValueError("No chunks generated from text")

        # Prepare data for insertion
        ids = []
        documents = []
        metadatas = []

        base_metadata = {
            "vendor_name": normalize_vendor_name(vendor_name),
            "contract_id": contract_id,
            "contract_type": contract_type,
            "indexed_at": datetime.now().isoformat(),
            "total_chunks": len(chunks),
        }

        if metadata:
            base_metadata.update(metadata)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{contract_id}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk)

            chunk_metadata = base_metadata.copy()
            chunk_metadata["chunk_index"] = i
            metadatas.append(chunk_metadata)

        # Add to collection
        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(f"Indexed {len(chunks)} chunks for vendor '{vendor_name}' (contract_id: {contract_id})")
        return contract_id

    def retrieve_clauses(
        self,
        vendor_name: str,
        query: str,
        top_k: int = 3,
    ) -> List[RetrievedClause]:
        """
        Retrieve relevant contract clauses for a vendor.

        Args:
            vendor_name: Vendor to search within
            query: Semantic search query
            top_k: Number of results to return

        Returns:
            List of RetrievedClause objects
        """
        if not query or not query.strip():
            return []

        # Build filter for vendor (normalize for consistent matching)
        where_filter = {"vendor_name": normalize_vendor_name(vendor_name)} if vendor_name else None

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter,
            )
        except (ConnectionError, OSError) as e:
            raise StoreError(f"ChromaDB infrastructure error during query: {e}") from e
        except Exception as e:
            logger.error(f"Query failed: {e}")
            return []

        # Convert results to RetrievedClause objects
        clauses = []

        if results and results["ids"] and results["ids"][0]:
            ids = results["ids"][0]
            documents = results["documents"][0] if results["documents"] else []
            metadatas = results["metadatas"][0] if results["metadatas"] else []
            distances = results["distances"][0] if results["distances"] else []

            for i, chunk_id in enumerate(ids):
                # Convert distance to similarity score (cosine distance to similarity)
                distance = distances[i] if i < len(distances) else 0
                similarity = 1 - distance  # For cosine distance

                clause = RetrievedClause(
                    text=documents[i] if i < len(documents) else "",
                    vendor_name=metadatas[i].get("vendor_name", vendor_name) if i < len(metadatas) else vendor_name,
                    similarity_score=max(0, min(1, similarity)),  # Clamp to [0, 1]
                    chunk_id=chunk_id,
                    metadata=metadatas[i] if i < len(metadatas) else {},
                )
                clauses.append(clause)

        return clauses

    def search_all_vendors(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[RetrievedClause]:
        """
        Search across all vendors.

        Args:
            query: Semantic search query
            top_k: Number of results to return

        Returns:
            List of RetrievedClause objects
        """
        return self.retrieve_clauses(vendor_name="", query=query, top_k=top_k)

    def delete_contract(self, vendor_name: str, contract_id: Optional[str] = None) -> int:
        """
        Delete contract chunks from the store.

        Args:
            vendor_name: Vendor name to delete
            contract_id: Specific contract ID (if None, deletes all for vendor)

        Returns:
            Number of chunks deleted
        """
        if contract_id:
            where_filter = {"contract_id": contract_id}
        else:
            where_filter = {"vendor_name": normalize_vendor_name(vendor_name)}

        # Get count before deletion
        existing = self._collection.get(where=where_filter)
        count = len(existing["ids"]) if existing and existing["ids"] else 0

        if count > 0:
            self._collection.delete(where=where_filter)
            logger.info(f"Deleted {count} chunks for vendor '{vendor_name}'")

        return count

    def list_vendors(self) -> List[dict]:
        """
        List all indexed vendors with their chunk counts.

        Returns:
            List of dicts with vendor info
        """
        # Get all documents metadata
        all_data = self._collection.get()

        if not all_data or not all_data["metadatas"]:
            return []

        # Aggregate by vendor
        vendor_info = {}
        for meta in all_data["metadatas"]:
            vendor = meta.get("vendor_name", "Unknown")
            contract_id = meta.get("contract_id", "")
            contract_type = meta.get("contract_type", "general")

            if vendor not in vendor_info:
                vendor_info[vendor] = {
                    "vendor_name": vendor,
                    "chunk_count": 0,
                    "contract_ids": set(),
                    "contract_types": set(),
                }

            vendor_info[vendor]["chunk_count"] += 1
            if contract_id:
                vendor_info[vendor]["contract_ids"].add(contract_id)
            if contract_type:
                vendor_info[vendor]["contract_types"].add(contract_type)

        # Convert sets to lists for JSON serialization
        result = []
        for vendor, info in vendor_info.items():
            result.append({
                "vendor_name": info["vendor_name"],
                "chunk_count": info["chunk_count"],
                "contract_count": len(info["contract_ids"]),
                "contract_types": list(info["contract_types"]),
            })

        return sorted(result, key=lambda x: x["vendor_name"])

    def get_stats(self) -> dict:
        """
        Get statistics about the vector store.

        Returns:
            Dict with stats
        """
        all_data = self._collection.get()
        total_chunks = len(all_data["ids"]) if all_data and all_data["ids"] else 0

        vendors = self.list_vendors()

        return {
            "total_chunks": total_chunks,
            "total_vendors": len(vendors),
            "vendors": vendors,
            "persist_directory": str(self.persist_directory),
        }

    def _generate_contract_id(self, vendor_name: str, text: str) -> str:
        """Generate a unique contract ID based on vendor and content hash."""
        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        safe_vendor = re.sub(r'[^a-zA-Z0-9]', '_', vendor_name.strip().lower())
        return f"{safe_vendor}_{content_hash}"


# Convenience function
def create_vector_store(
    persist_directory: str = "./data/chroma_db",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> VectorStore:
    """
    Create a VectorStore instance with default settings.

    Args:
        persist_directory: Path for persistence
        chunk_size: Chunk size in characters
        chunk_overlap: Overlap between chunks

    Returns:
        VectorStore instance
    """
    return VectorStore(
        persist_directory=persist_directory,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
