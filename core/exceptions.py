"""
Custom exceptions for DocuMatch Architect.

Provides distinct exception types to distinguish infrastructure errors
from business-logic conditions (e.g., "not found").
"""


class StoreError(Exception):
    """Raised when a ChromaDB infrastructure error occurs.

    Use this for connection failures, collection errors, and other
    infrastructure problems. Do NOT use for business-logic conditions
    like "PO not found" -- return None/[] for those instead.
    """
    pass
