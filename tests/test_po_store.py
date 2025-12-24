"""
Tests for the PO Store.

Run with: pytest tests/test_po_store.py -v
"""

import tempfile
import shutil

import pytest

from core.po_store import POStore, create_po_store
from core.models import PurchaseOrderSchema, LineItem


class TestPOStoreInit:
    """Test cases for POStore initialization."""

    def test_init_creates_directory(self):
        """Test that init creates persist directory."""
        temp_dir = tempfile.mkdtemp()
        try:
            store = POStore(persist_directory=temp_dir)
            assert store.persist_directory.exists()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init_creates_collection(self):
        """Test that init creates the PO collection."""
        temp_dir = tempfile.mkdtemp()
        try:
            store = POStore(persist_directory=temp_dir)
            assert store._collection is not None
            assert store._collection.name == "purchase_orders"
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestPOIndexing:
    """Test cases for PO indexing."""

    @pytest.fixture
    def store(self):
        """Create a temporary PO store."""
        temp_dir = tempfile.mkdtemp()
        store = POStore(persist_directory=temp_dir)
        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_index_po_basic(self, store):
        """Test basic PO indexing."""
        po = PurchaseOrderSchema(
            po_number="PO-2024-001",
            vendor_name="Acme Corp",
            order_date="2024-01-15",
            total_amount=5000.00,
            currency="USD",
            line_items=[
                LineItem(description="Consulting Services", quantity=10, unit_price=500, total=5000)
            ]
        )

        po_id = store.index_po(po)

        assert po_id == "PO-2024-001"

    def test_index_po_full_details(self, store):
        """Test indexing PO with all fields."""
        po = PurchaseOrderSchema(
            po_number="PO-2024-002",
            vendor_name="Tech Solutions",
            order_date="2024-02-01",
            expected_delivery_date="2024-03-01",
            total_amount=10000.00,
            currency="USD",
            line_items=[
                LineItem(description="Software License", quantity=5, unit_price=1000, total=5000),
                LineItem(description="Support Package", quantity=1, unit_price=5000, total=5000)
            ],
            billing_address="123 Main St",
            shipping_address="456 Oak Ave",
            payment_terms="Net 30",
            contract_reference="MSA-2024-001",
            notes="Urgent delivery required"
        )

        po_id = store.index_po(po)
        assert po_id == "PO-2024-002"

        # Verify we can retrieve it
        retrieved = store.get_po_by_number("PO-2024-002")
        assert retrieved is not None
        assert retrieved.vendor_name == "Tech Solutions"
        assert retrieved.expected_delivery_date == "2024-03-01"
        assert len(retrieved.line_items) == 2

    def test_index_po_update_existing(self, store):
        """Test updating an existing PO."""
        po1 = PurchaseOrderSchema(
            po_number="PO-001",
            vendor_name="Vendor A",
            order_date="2024-01-01",
            total_amount=1000.00
        )
        store.index_po(po1)

        # Update with new total
        po2 = PurchaseOrderSchema(
            po_number="PO-001",
            vendor_name="Vendor A",
            order_date="2024-01-01",
            total_amount=2000.00
        )
        store.index_po(po2)

        retrieved = store.get_po_by_number("PO-001")
        assert retrieved.total_amount == 2000.00

    def test_index_po_requires_number(self, store):
        """Test that PO number is required."""
        po = PurchaseOrderSchema(
            po_number="",
            vendor_name="Test",
            order_date="2024-01-01",
            total_amount=100
        )

        with pytest.raises(ValueError, match="PO number is required"):
            store.index_po(po)

    def test_index_po_requires_vendor(self, store):
        """Test that vendor name is required."""
        po = PurchaseOrderSchema(
            po_number="PO-001",
            vendor_name="",
            order_date="2024-01-01",
            total_amount=100
        )

        with pytest.raises(ValueError, match="Vendor name is required"):
            store.index_po(po)


class TestPORetrieval:
    """Test cases for PO retrieval."""

    @pytest.fixture
    def populated_store(self):
        """Create and populate a PO store."""
        temp_dir = tempfile.mkdtemp()
        store = POStore(persist_directory=temp_dir)

        # Add sample POs
        pos = [
            PurchaseOrderSchema(
                po_number="PO-001",
                vendor_name="Acme Corp",
                order_date="2024-01-15",
                total_amount=5000.00,
                line_items=[
                    LineItem(description="Service A", quantity=10, unit_price=500, total=5000)
                ]
            ),
            PurchaseOrderSchema(
                po_number="PO-002",
                vendor_name="Acme Corp",
                order_date="2024-02-15",
                total_amount=3000.00
            ),
            PurchaseOrderSchema(
                po_number="PO-003",
                vendor_name="Tech Solutions",
                order_date="2024-03-15",
                total_amount=7500.00
            )
        ]

        for po in pos:
            store.index_po(po)

        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_get_po_by_number(self, populated_store):
        """Test retrieving PO by number."""
        po = populated_store.get_po_by_number("PO-001")

        assert po is not None
        assert po.po_number == "PO-001"
        assert po.vendor_name == "Acme Corp"
        assert po.total_amount == 5000.00

    def test_get_po_by_number_not_found(self, populated_store):
        """Test retrieving non-existent PO."""
        po = populated_store.get_po_by_number("PO-NOTEXIST")
        assert po is None

    def test_get_po_by_number_empty(self, populated_store):
        """Test retrieving with empty string."""
        po = populated_store.get_po_by_number("")
        assert po is None

    def test_get_pos_by_vendor(self, populated_store):
        """Test retrieving POs by vendor."""
        pos = populated_store.get_pos_by_vendor("Acme Corp")

        assert len(pos) == 2
        po_numbers = [po.po_number for po in pos]
        assert "PO-001" in po_numbers
        assert "PO-002" in po_numbers

    def test_get_pos_by_vendor_not_found(self, populated_store):
        """Test retrieving POs for unknown vendor."""
        pos = populated_store.get_pos_by_vendor("Unknown Vendor")
        assert len(pos) == 0

    def test_get_pos_by_vendor_empty(self, populated_store):
        """Test retrieving with empty vendor name."""
        pos = populated_store.get_pos_by_vendor("")
        assert len(pos) == 0


class TestPOSearch:
    """Test cases for PO semantic search."""

    @pytest.fixture
    def populated_store(self):
        """Create and populate a PO store."""
        temp_dir = tempfile.mkdtemp()
        store = POStore(persist_directory=temp_dir)

        pos = [
            PurchaseOrderSchema(
                po_number="PO-CONSULT-001",
                vendor_name="Acme Corp",
                order_date="2024-01-15",
                total_amount=5000.00,
                line_items=[
                    LineItem(description="Senior Consultant Services", quantity=10, unit_price=500, total=5000)
                ]
            ),
            PurchaseOrderSchema(
                po_number="PO-SOFTWARE-001",
                vendor_name="Tech Solutions",
                order_date="2024-02-15",
                total_amount=10000.00,
                line_items=[
                    LineItem(description="Software License Annual", quantity=1, unit_price=10000, total=10000)
                ]
            )
        ]

        for po in pos:
            store.index_po(po)

        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_search_pos(self, populated_store):
        """Test semantic search for POs."""
        results = populated_store.search_pos("consulting services")

        assert len(results) > 0
        assert any(po.po_number == "PO-CONSULT-001" for po in results)

    def test_search_pos_with_vendor_filter(self, populated_store):
        """Test search with vendor filter."""
        results = populated_store.search_pos("services", vendor_name="Acme Corp")

        assert len(results) > 0
        for po in results:
            assert po.vendor_name == "Acme Corp"

    def test_search_pos_empty_query(self, populated_store):
        """Test search with empty query."""
        results = populated_store.search_pos("")
        assert len(results) == 0


class TestPODeletion:
    """Test cases for PO deletion."""

    @pytest.fixture
    def populated_store(self):
        """Create and populate a PO store."""
        temp_dir = tempfile.mkdtemp()
        store = POStore(persist_directory=temp_dir)

        pos = [
            PurchaseOrderSchema(po_number="PO-001", vendor_name="Vendor A", order_date="2024-01-01", total_amount=1000),
            PurchaseOrderSchema(po_number="PO-002", vendor_name="Vendor A", order_date="2024-01-02", total_amount=2000),
            PurchaseOrderSchema(po_number="PO-003", vendor_name="Vendor B", order_date="2024-01-03", total_amount=3000)
        ]

        for po in pos:
            store.index_po(po)

        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_delete_po(self, populated_store):
        """Test deleting a PO."""
        result = populated_store.delete_po("PO-001")

        assert result is True
        assert populated_store.get_po_by_number("PO-001") is None

    def test_delete_po_not_found(self, populated_store):
        """Test deleting non-existent PO."""
        result = populated_store.delete_po("PO-NOTEXIST")
        assert result is False

    def test_delete_po_empty(self, populated_store):
        """Test deleting with empty string."""
        result = populated_store.delete_po("")
        assert result is False

    def test_delete_pos_by_vendor(self, populated_store):
        """Test deleting all POs for a vendor."""
        count = populated_store.delete_pos_by_vendor("Vendor A")

        assert count == 2
        assert len(populated_store.get_pos_by_vendor("Vendor A")) == 0
        assert len(populated_store.get_pos_by_vendor("Vendor B")) == 1


class TestPOListing:
    """Test cases for PO listing."""

    @pytest.fixture
    def populated_store(self):
        """Create and populate a PO store."""
        temp_dir = tempfile.mkdtemp()
        store = POStore(persist_directory=temp_dir)

        pos = [
            PurchaseOrderSchema(po_number="PO-001", vendor_name="Vendor A", order_date="2024-01-01", total_amount=1000),
            PurchaseOrderSchema(po_number="PO-002", vendor_name="Vendor B", order_date="2024-01-02", total_amount=2000)
        ]

        for po in pos:
            store.index_po(po)

        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_list_pos(self, populated_store):
        """Test listing all POs."""
        pos = populated_store.list_pos()

        assert len(pos) == 2
        po_numbers = [po["po_number"] for po in pos]
        assert "PO-001" in po_numbers
        assert "PO-002" in po_numbers

    def test_list_pos_empty(self):
        """Test listing from empty store."""
        temp_dir = tempfile.mkdtemp()
        try:
            store = POStore(persist_directory=temp_dir)
            pos = store.list_pos()
            assert len(pos) == 0
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestPOStats:
    """Test cases for PO store statistics."""

    @pytest.fixture
    def populated_store(self):
        """Create and populate a PO store."""
        temp_dir = tempfile.mkdtemp()
        store = POStore(persist_directory=temp_dir)

        pos = [
            PurchaseOrderSchema(po_number="PO-001", vendor_name="Vendor A", order_date="2024-01-01", total_amount=1000),
            PurchaseOrderSchema(po_number="PO-002", vendor_name="Vendor A", order_date="2024-01-02", total_amount=2000),
            PurchaseOrderSchema(po_number="PO-003", vendor_name="Vendor B", order_date="2024-01-03", total_amount=3000)
        ]

        for po in pos:
            store.index_po(po)

        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_get_stats(self, populated_store):
        """Test getting statistics."""
        stats = populated_store.get_stats()

        assert stats["total_pos"] == 3
        assert stats["total_vendors"] == 2
        assert "Vendor A" in stats["vendors"]
        assert "Vendor B" in stats["vendors"]


class TestConvenienceFunction:
    """Test the convenience function."""

    def test_create_po_store(self):
        """Test create_po_store convenience function."""
        temp_dir = tempfile.mkdtemp()
        try:
            store = create_po_store(persist_directory=temp_dir)
            assert isinstance(store, POStore)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
