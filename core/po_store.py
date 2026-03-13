"""
PO Store for DocuMatch Architect.

Manages Purchase Order storage and retrieval using ChromaDB.
POs are stored as structured documents for exact and semantic search.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

import chromadb
from chromadb.config import Settings as ChromaSettings

from .exceptions import StoreError
from .models import PurchaseOrderSchema, LineItem
from .vector_store import normalize_vendor_name

# Configure logging
logger = logging.getLogger(__name__)


class POStore:
    """
    ChromaDB-based store for Purchase Orders.

    Stores PO data as searchable documents, organized by vendor name
    and PO number for efficient retrieval.

    Usage:
        store = POStore(persist_directory="./data/chroma_db")
        store.index_po(po_data)
        po = store.get_po_by_number("PO-2024-001")
        pos = store.get_pos_by_vendor("VendorA")
    """

    COLLECTION_NAME = "purchase_orders"

    def __init__(
        self,
        persist_directory: str = "./data/chroma_db",
    ):
        """
        Initialize the PO store.

        Args:
            persist_directory: Path for ChromaDB persistence
        """
        self.persist_directory = Path(persist_directory)

        # Ensure directory exists
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client with persistence
        self._client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # Get or create collection
        self._collection = self._get_or_create_collection()

        logger.info(f"POStore initialized at {self.persist_directory}")

    def _get_or_create_collection(self):
        """Get or create the PO collection."""
        try:
            collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            return collection
        except Exception as e:
            logger.error(f"Failed to create PO collection: {e}")
            raise

    def _po_to_document(self, po: PurchaseOrderSchema) -> str:
        """Convert PO to searchable document text."""
        lines = [
            f"Purchase Order: {po.po_number}",
            f"Vendor: {po.vendor_name}",
            f"Order Date: {po.order_date}",
            f"Total Amount: {po.total_amount} {po.currency}",
        ]

        if po.expected_delivery_date:
            lines.append(f"Expected Delivery: {po.expected_delivery_date}")

        if po.payment_terms:
            lines.append(f"Payment Terms: {po.payment_terms}")

        if po.line_items:
            lines.append("\nLine Items:")
            for item in po.line_items:
                lines.append(f"- {item.description}: {item.quantity} x ${item.unit_price:.2f} = ${item.total:.2f}")

        return "\n".join(lines)

    def _po_to_metadata(self, po: PurchaseOrderSchema) -> dict:
        """Convert PO to metadata dict for storage."""
        return {
            "po_number": po.po_number,
            "vendor_name": normalize_vendor_name(po.vendor_name),
            "order_date": po.order_date,
            "expected_delivery_date": po.expected_delivery_date or "",
            "total_amount": po.total_amount,
            "currency": po.currency,
            "payment_terms": po.payment_terms or "",
            "contract_reference": po.contract_reference or "",
            "billing_address": po.billing_address or "",
            "shipping_address": po.shipping_address or "",
            "notes": po.notes or "",
            "line_items_json": json.dumps([item.model_dump() for item in po.line_items]),
            "indexed_at": datetime.now().isoformat(),
        }

    def _metadata_to_po(self, metadata: dict) -> PurchaseOrderSchema:
        """Convert metadata back to PurchaseOrderSchema."""
        line_items = []
        if metadata.get("line_items_json"):
            items_data = json.loads(metadata["line_items_json"])
            line_items = [LineItem(**item) for item in items_data]

        return PurchaseOrderSchema(
            po_number=metadata["po_number"],
            vendor_name=metadata["vendor_name"],
            order_date=metadata["order_date"],
            expected_delivery_date=metadata.get("expected_delivery_date") or None,
            total_amount=float(metadata["total_amount"]),
            currency=metadata.get("currency", "USD"),
            line_items=line_items,
            payment_terms=metadata.get("payment_terms") or None,
            contract_reference=metadata.get("contract_reference") or None,
            billing_address=metadata.get("billing_address") or None,
            shipping_address=metadata.get("shipping_address") or None,
            notes=metadata.get("notes") or None,
        )

    def index_po(self, po: PurchaseOrderSchema) -> str:
        """
        Index a Purchase Order into the store.

        Args:
            po: PurchaseOrderSchema to store

        Returns:
            po_id: The PO number as identifier
        """
        if not po.po_number:
            raise ValueError("PO number is required")

        if not po.vendor_name:
            raise ValueError("Vendor name is required")

        # Check if PO already exists
        existing = self._collection.get(
            where={"po_number": po.po_number}
        )

        if existing and existing["ids"]:
            logger.info(f"PO {po.po_number} already exists, updating...")
            self._collection.delete(
                where={"po_number": po.po_number}
            )

        # Create document and metadata
        document = self._po_to_document(po)
        metadata = self._po_to_metadata(po)

        # Add to collection
        self._collection.add(
            ids=[po.po_number],
            documents=[document],
            metadatas=[metadata],
        )

        logger.info(f"Indexed PO {po.po_number} for vendor '{po.vendor_name}'")
        return po.po_number

    def get_po_by_number(self, po_number: str) -> Optional[PurchaseOrderSchema]:
        """
        Retrieve a PO by its number.

        Args:
            po_number: The PO number to look up

        Returns:
            PurchaseOrderSchema or None if not found
        """
        if not po_number:
            return None

        try:
            results = self._collection.get(
                where={"po_number": po_number}
            )

            if results and results["ids"] and results["metadatas"]:
                metadata = results["metadatas"][0]
                return self._metadata_to_po(metadata)

        except (ConnectionError, OSError) as e:
            raise StoreError(f"ChromaDB infrastructure error retrieving PO {po_number}: {e}") from e
        except Exception as e:
            logger.error(f"Failed to get PO {po_number}: {e}")

        return None

    def get_pos_by_vendor(self, vendor_name: str) -> List[PurchaseOrderSchema]:
        """
        Retrieve all POs for a vendor.

        Args:
            vendor_name: Vendor name to filter by

        Returns:
            List of PurchaseOrderSchema
        """
        if not vendor_name:
            return []

        try:
            results = self._collection.get(
                where={"vendor_name": normalize_vendor_name(vendor_name)}
            )

            if results and results["metadatas"]:
                return [self._metadata_to_po(meta) for meta in results["metadatas"]]

        except (ConnectionError, OSError) as e:
            raise StoreError(f"ChromaDB infrastructure error for vendor {vendor_name}: {e}") from e
        except Exception as e:
            logger.error(f"Failed to get POs for vendor {vendor_name}: {e}")

        return []

    def search_pos(
        self,
        query: str,
        vendor_name: Optional[str] = None,
        top_k: int = 5,
    ) -> List[PurchaseOrderSchema]:
        """
        Semantic search for POs.

        Args:
            query: Search query
            vendor_name: Optional vendor filter
            top_k: Number of results to return

        Returns:
            List of matching PurchaseOrderSchema
        """
        if not query:
            return []

        where_filter = {"vendor_name": normalize_vendor_name(vendor_name)} if vendor_name else None

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter,
            )

            if results and results["metadatas"] and results["metadatas"][0]:
                return [self._metadata_to_po(meta) for meta in results["metadatas"][0]]

        except (ConnectionError, OSError) as e:
            raise StoreError(f"ChromaDB infrastructure error during PO search: {e}") from e
        except Exception as e:
            logger.error(f"Search failed: {e}")

        return []

    def delete_po(self, po_number: str) -> bool:
        """
        Delete a PO from the store.

        Args:
            po_number: PO number to delete

        Returns:
            True if deleted, False otherwise
        """
        if not po_number:
            return False

        try:
            existing = self._collection.get(
                where={"po_number": po_number}
            )

            if existing and existing["ids"]:
                self._collection.delete(
                    where={"po_number": po_number}
                )
                logger.info(f"Deleted PO {po_number}")
                return True

        except Exception as e:
            logger.error(f"Failed to delete PO {po_number}: {e}")

        return False

    def delete_pos_by_vendor(self, vendor_name: str) -> int:
        """
        Delete all POs for a vendor.

        Args:
            vendor_name: Vendor name

        Returns:
            Number of POs deleted
        """
        if not vendor_name:
            return 0

        try:
            normalized_name = normalize_vendor_name(vendor_name)
            existing = self._collection.get(
                where={"vendor_name": normalized_name}
            )

            count = len(existing["ids"]) if existing and existing["ids"] else 0

            if count > 0:
                self._collection.delete(
                    where={"vendor_name": normalized_name}
                )
                logger.info(f"Deleted {count} POs for vendor '{vendor_name}'")

            return count

        except Exception as e:
            logger.error(f"Failed to delete POs for vendor {vendor_name}: {e}")
            return 0

    def list_pos(self) -> List[dict]:
        """
        List all indexed POs with summary info.

        Returns:
            List of dicts with PO summary info
        """
        all_data = self._collection.get()

        if not all_data or not all_data["metadatas"]:
            return []

        pos = []
        for metadata in all_data["metadatas"]:
            pos.append({
                "po_number": metadata.get("po_number", ""),
                "vendor_name": metadata.get("vendor_name", ""),
                "order_date": metadata.get("order_date", ""),
                "total_amount": float(metadata.get("total_amount", 0)),
                "currency": metadata.get("currency", "USD"),
                "indexed_at": metadata.get("indexed_at", ""),
            })

        return sorted(pos, key=lambda x: x["po_number"])

    def get_stats(self) -> dict:
        """
        Get statistics about the PO store.

        Returns:
            Dict with stats
        """
        all_data = self._collection.get()
        total_pos = len(all_data["ids"]) if all_data and all_data["ids"] else 0

        # Get unique vendors
        vendors = set()
        if all_data and all_data["metadatas"]:
            for meta in all_data["metadatas"]:
                vendors.add(meta.get("vendor_name", ""))

        return {
            "total_pos": total_pos,
            "total_vendors": len(vendors),
            "vendors": list(vendors),
            "persist_directory": str(self.persist_directory),
        }


# Convenience function
def create_po_store(persist_directory: str = "./data/chroma_db") -> POStore:
    """
    Create a POStore instance.

    Args:
        persist_directory: Path for persistence

    Returns:
        POStore instance
    """
    return POStore(persist_directory=persist_directory)
