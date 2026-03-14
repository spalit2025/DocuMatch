"""
Demo Data Loader for DocuMatch Architect.

Loads a curated subset of eval scenarios into ChromaDB and SQLite
so users can see the full pipeline without uploading their own documents.

Scenarios loaded:
  - exact_01 (Acme Consulting): Perfect match -> PASS
  - partial_01 (BudgetTech): Rate violation -> FAIL
  - mismatch_03 (ChaosVendor): Everything wrong -> FAIL
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .database import Database
from .matcher import Matcher
from .models import InvoiceSchema, LineItem, PurchaseOrderSchema
from .po_store import POStore
from .vector_store import VectorStore

logger = logging.getLogger(__name__)

EVAL_DATA_DIR = Path(__file__).parent.parent / "evals" / "data"

# Scenarios to load for the demo
DEMO_SCENARIOS = ["exact_01", "partial_01", "mismatch_03"]


def load_demo_data(
    vector_store: VectorStore,
    po_store: POStore,
    matcher: Matcher,
    database: Optional[Database] = None,
) -> dict:
    """
    Load demo scenarios into the system.

    Indexes contracts and POs, then runs matching on invoices.
    Optionally saves results to SQLite for the analytics dashboard.

    Returns:
        Summary dict with counts and results
    """
    contracts = _load_json("contracts/contracts.json")
    pos = _load_json("pos/purchase_orders.json")
    invoices = _load_json("invoices/invoices.json")

    results_summary = {
        "contracts_indexed": 0,
        "pos_indexed": 0,
        "invoices_processed": 0,
        "results": [],
    }

    for scenario_id in DEMO_SCENARIOS:
        if scenario_id not in contracts:
            continue

        # Index contract
        contract = contracts[scenario_id]
        try:
            vector_store.index_contract(
                text=contract["markdown"],
                vendor_name=contract["vendor_name"],
                contract_type=contract["contract_type"],
            )
            results_summary["contracts_indexed"] += 1
            logger.info(f"Demo: indexed contract for {contract['vendor_name']}")
        except Exception as e:
            logger.warning(f"Demo: failed to index contract {scenario_id}: {e}")

        # Index PO
        if scenario_id in pos:
            po_data = pos[scenario_id]
            try:
                po = PurchaseOrderSchema(
                    po_number=po_data["po_number"],
                    vendor_name=po_data["vendor_name"],
                    order_date=po_data["order_date"],
                    total_amount=po_data["total_amount"],
                    currency=po_data.get("currency", "USD"),
                    line_items=[LineItem(**item) for item in po_data["line_items"]],
                    payment_terms=po_data.get("payment_terms"),
                )
                po_store.index_po(po)
                results_summary["pos_indexed"] += 1
                logger.info(f"Demo: indexed PO {po_data['po_number']}")
            except Exception as e:
                logger.warning(f"Demo: failed to index PO {scenario_id}: {e}")

        # Process invoice
        if scenario_id in invoices:
            inv_data = invoices[scenario_id]
            try:
                invoice = InvoiceSchema(
                    vendor_name=inv_data["vendor_name"],
                    invoice_number=inv_data["invoice_number"],
                    invoice_date=inv_data["invoice_date"],
                    po_number=inv_data.get("po_number"),
                    total_amount=inv_data["total_amount"],
                    currency=inv_data.get("currency", "USD"),
                    line_items=[LineItem(**item) for item in inv_data["line_items"]],
                    payment_terms=inv_data.get("payment_terms"),
                )

                result = matcher.validate_invoice_three_way(
                    invoice=invoice,
                    po_number=inv_data.get("po_number"),
                )

                results_summary["invoices_processed"] += 1
                results_summary["results"].append({
                    "scenario": scenario_id,
                    "vendor": inv_data["vendor_name"],
                    "invoice": inv_data["invoice_number"],
                    "status": result.status,
                    "matches": f"{result.matches_passed}/{result.total_matches}",
                    "score": round(result.overall_score, 2),
                })

                # Save to database if available
                if database:
                    job = database.create_job(
                        job_type="invoice_process",
                        file_name=f"demo_{scenario_id}.pdf",
                        vendor_name=inv_data["vendor_name"],
                    )
                    database.update_job_status(job.id, "COMPLETE")
                    database.save_result(
                        job_id=job.id,
                        invoice_file=f"demo_{scenario_id}.pdf",
                        vendor_name=inv_data["vendor_name"],
                        invoice_number=inv_data["invoice_number"],
                        status=result.status,
                        confidence=result.overall_score,
                        matches_passed=result.matches_passed,
                        total_matches=result.total_matches,
                    )

                logger.info(
                    f"Demo: processed {inv_data['invoice_number']} -> {result.status}"
                )
            except Exception as e:
                logger.warning(f"Demo: failed to process invoice {scenario_id}: {e}")

    return results_summary


def _load_json(relative_path: str) -> dict:
    path = EVAL_DATA_DIR / relative_path
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)
