"""
Tests for the Vector Store.

Run with: pytest tests/test_vector_store.py -v
"""

import tempfile
import shutil
from pathlib import Path

import pytest

from core.vector_store import VectorStore, create_vector_store
from core.models import RetrievedClause


class TestVectorStoreChunking:
    """Test cases for text chunking functionality."""

    @pytest.fixture
    def temp_store(self):
        """Create a temporary vector store for testing."""
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir, chunk_size=100, chunk_overlap=10)
        yield store
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_chunk_empty_text(self, temp_store):
        """Test chunking empty text."""
        chunks = temp_store.chunk_text("")
        assert chunks == []

        chunks = temp_store.chunk_text("   ")
        assert chunks == []

    def test_chunk_short_text(self, temp_store):
        """Test chunking text shorter than chunk size."""
        text = "This is a short text."
        chunks = temp_store.chunk_text(text)
        assert len(chunks) == 1
        assert "This is a short text" in chunks[0]

    def test_chunk_long_text(self, temp_store):
        """Test chunking text longer than chunk size."""
        # Create text longer than chunk size (100 chars)
        text = "This is sentence one. " * 10  # ~220 chars
        chunks = temp_store.chunk_text(text)
        assert len(chunks) > 1

    def test_chunk_with_paragraphs(self, temp_store):
        """Test chunking text with paragraph breaks."""
        text = """First paragraph here.

Second paragraph here.

Third paragraph with more content."""

        chunks = temp_store.chunk_text(text)
        assert len(chunks) >= 1
        # All content should be preserved
        full_text = " ".join(chunks)
        assert "First paragraph" in full_text
        assert "Second paragraph" in full_text
        assert "Third paragraph" in full_text


class TestVectorStoreIndexing:
    """Test cases for contract indexing."""

    @pytest.fixture
    def temp_store(self):
        """Create a temporary vector store for testing."""
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir, chunk_size=200, chunk_overlap=20)
        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_index_contract_basic(self, temp_store):
        """Test basic contract indexing."""
        text = """
        # Master Service Agreement

        This agreement is between Acme Corp and Client Inc.

        ## Payment Terms

        Payment is due within 30 days of invoice date.
        Late payments subject to 1.5% monthly interest.

        ## Rate Card

        Senior Consultant: $150/hour
        Junior Consultant: $100/hour
        """

        contract_id = temp_store.index_contract(text, "Acme Corp", "MSA")

        assert contract_id is not None
        assert "acme" in contract_id.lower()

        # Verify indexed
        stats = temp_store.get_stats()
        assert stats["total_chunks"] > 0
        assert stats["total_vendors"] == 1

    def test_index_contract_empty_text_fails(self, temp_store):
        """Test that empty text raises error."""
        with pytest.raises(ValueError, match="empty"):
            temp_store.index_contract("", "Vendor")

    def test_index_contract_no_vendor_fails(self, temp_store):
        """Test that missing vendor raises error."""
        with pytest.raises(ValueError, match="required"):
            temp_store.index_contract("Some text", "")

    def test_index_contract_with_metadata(self, temp_store):
        """Test indexing with custom metadata."""
        text = "Contract content here with enough text to create chunks."

        contract_id = temp_store.index_contract(
            text,
            "TestVendor",
            "SOW",
            metadata={"project": "Project Alpha", "year": 2024}
        )

        assert contract_id is not None

    def test_index_duplicate_updates(self, temp_store):
        """Test that re-indexing same content updates rather than duplicates."""
        text = "Original contract content that should be indexed once."

        # Index twice
        id1 = temp_store.index_contract(text, "Vendor1")
        id2 = temp_store.index_contract(text, "Vendor1")

        assert id1 == id2  # Same content, same ID

        # Should only have one set of chunks
        vendors = temp_store.list_vendors()
        assert len(vendors) == 1


class TestVectorStoreRetrieval:
    """Test cases for clause retrieval."""

    @pytest.fixture
    def populated_store(self):
        """Create and populate a vector store for testing."""
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir, chunk_size=300, chunk_overlap=30)

        # Index sample contracts
        contract1 = """
        # Acme Corp Master Service Agreement

        ## Payment Terms
        All invoices are due within Net 30 days of receipt.
        Late payments will incur a 1.5% monthly interest charge.

        ## Rate Card
        Senior Developer: $175 per hour
        Junior Developer: $95 per hour
        Project Manager: $150 per hour

        ## Termination
        Either party may terminate with 30 days written notice.
        """

        contract2 = """
        # Beta Inc Statement of Work

        ## Project Scope
        Development of mobile application for iOS and Android.

        ## Payment Schedule
        50% upfront, 50% upon delivery.
        Payment due within 15 days of invoice.

        ## Rates
        Mobile Developer: $160 per hour
        QA Engineer: $90 per hour
        """

        store.index_contract(contract1, "Acme Corp", "MSA")
        store.index_contract(contract2, "Beta Inc", "SOW")

        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_retrieve_by_vendor(self, populated_store):
        """Test retrieving clauses for specific vendor."""
        clauses = populated_store.retrieve_clauses("Acme Corp", "payment terms")

        assert len(clauses) > 0
        assert all(isinstance(c, RetrievedClause) for c in clauses)
        assert all(c.vendor_name == "Acme Corp" for c in clauses)

    def test_retrieve_semantic_match(self, populated_store):
        """Test semantic matching in retrieval."""
        clauses = populated_store.retrieve_clauses("Acme Corp", "hourly rates")

        assert len(clauses) > 0
        # Should find rate-related content
        combined_text = " ".join(c.text for c in clauses)
        assert "per hour" in combined_text.lower() or "rate" in combined_text.lower()

    def test_retrieve_with_similarity_scores(self, populated_store):
        """Test that similarity scores are returned."""
        clauses = populated_store.retrieve_clauses("Acme Corp", "payment")

        assert len(clauses) > 0
        for clause in clauses:
            assert 0 <= clause.similarity_score <= 1

    def test_retrieve_top_k(self, populated_store):
        """Test top_k parameter."""
        clauses_1 = populated_store.retrieve_clauses("Acme Corp", "terms", top_k=1)
        clauses_3 = populated_store.retrieve_clauses("Acme Corp", "terms", top_k=3)

        assert len(clauses_1) <= 1
        assert len(clauses_3) <= 3

    def test_retrieve_empty_query(self, populated_store):
        """Test with empty query."""
        clauses = populated_store.retrieve_clauses("Acme Corp", "")
        assert clauses == []

    def test_retrieve_nonexistent_vendor(self, populated_store):
        """Test retrieval for vendor with no contracts."""
        clauses = populated_store.retrieve_clauses("Nonexistent Vendor", "payment")
        assert clauses == []

    def test_search_all_vendors(self, populated_store):
        """Test searching across all vendors."""
        clauses = populated_store.search_all_vendors("payment", top_k=5)

        assert len(clauses) > 0
        # Should find results from multiple vendors
        vendors = set(c.vendor_name for c in clauses)
        assert len(vendors) >= 1  # At least one vendor


class TestVectorStoreManagement:
    """Test cases for store management operations."""

    @pytest.fixture
    def temp_store(self):
        """Create a temporary vector store for testing."""
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir)
        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_list_vendors_empty(self, temp_store):
        """Test listing vendors when store is empty."""
        vendors = temp_store.list_vendors()
        assert vendors == []

    def test_list_vendors_populated(self, temp_store):
        """Test listing vendors after indexing."""
        temp_store.index_contract("Contract A content here.", "Vendor A", "MSA")
        temp_store.index_contract("Contract B content here.", "Vendor B", "SOW")

        vendors = temp_store.list_vendors()

        assert len(vendors) == 2
        vendor_names = [v["vendor_name"] for v in vendors]
        assert "Vendor A" in vendor_names
        assert "Vendor B" in vendor_names

    def test_delete_contract(self, temp_store):
        """Test deleting a contract."""
        temp_store.index_contract("Content to delete.", "DeleteMe")

        # Verify indexed
        assert temp_store.get_stats()["total_chunks"] > 0

        # Delete
        deleted = temp_store.delete_contract("DeleteMe")
        assert deleted > 0

        # Verify deleted
        assert temp_store.get_stats()["total_chunks"] == 0

    def test_get_stats(self, temp_store):
        """Test getting store statistics."""
        temp_store.index_contract("Some content here.", "Vendor1")

        stats = temp_store.get_stats()

        assert "total_chunks" in stats
        assert "total_vendors" in stats
        assert "vendors" in stats
        assert stats["total_vendors"] == 1


class TestVectorStorePersistence:
    """Test cases for persistence across restarts."""

    def test_persistence(self):
        """Test that data persists after store is closed and reopened."""
        temp_dir = tempfile.mkdtemp()

        try:
            # Create and populate store
            store1 = VectorStore(persist_directory=temp_dir)
            store1.index_contract("Persistent content here.", "PersistentVendor")
            stats1 = store1.get_stats()

            # Create new store instance (simulating restart)
            store2 = VectorStore(persist_directory=temp_dir)
            stats2 = store2.get_stats()

            # Data should persist
            assert stats2["total_chunks"] == stats1["total_chunks"]
            assert stats2["total_vendors"] == stats1["total_vendors"]

            # Should be able to retrieve
            clauses = store2.retrieve_clauses("PersistentVendor", "content")
            assert len(clauses) > 0

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestConvenienceFunction:
    """Test the convenience function."""

    def test_create_vector_store(self):
        """Test create_vector_store function."""
        temp_dir = tempfile.mkdtemp()

        try:
            store = create_vector_store(
                persist_directory=temp_dir,
                chunk_size=256,
                chunk_overlap=25
            )

            assert isinstance(store, VectorStore)
            assert store.chunk_size == 256
            assert store.chunk_overlap == 25

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
