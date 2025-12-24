"""
Synthetic Data Generator for DocuMatch Evaluation

Generates 12 sets of contracts, POs, and invoices with:
- 7 exact match scenarios (all 3 matches should pass)
- 2 partial match scenarios (2 of 3 matches pass)
- 3 full mismatch scenarios (fewer than 2 matches pass)
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

# Base directory for eval data
EVAL_DATA_DIR = Path(__file__).parent / "data"


# =============================================================================
# SCENARIO DEFINITIONS
# =============================================================================

SCENARIOS = {
    # =========================================================================
    # EXACT MATCH SCENARIOS (7) - All 3 matches should PASS
    # =========================================================================
    "exact_01": {
        "vendor": "Acme Consulting",
        "description": "Perfect match - Senior Consultant services",
        "expected_result": "PASS",
        "expected_matches": 3,
        "contract": {
            "effective_date": "2024-01-01",
            "end_date": "2024-12-31",
            "rates": {"Senior Consultant": 150, "Junior Consultant": 85},
            "payment_terms": "Net 30",
        },
        "po": {
            "po_number": "PO-ACME-001",
            "order_date": "2024-06-01",
            "line_items": [
                {"description": "Senior Consultant", "quantity": 40, "unit_price": 150, "total": 6000}
            ],
            "total_amount": 6000,
        },
        "invoice": {
            "invoice_number": "INV-ACME-001",
            "invoice_date": "2024-06-30",
            "po_number": "PO-ACME-001",
            "line_items": [
                {"description": "Senior Consultant", "quantity": 40, "unit_price": 150, "total": 6000}
            ],
            "total_amount": 6000,
            "payment_terms": "Net 30",
        },
    },
    "exact_02": {
        "vendor": "TechPro Solutions",
        "description": "Perfect match - Software development services",
        "expected_result": "PASS",
        "expected_matches": 3,
        "contract": {
            "effective_date": "2024-01-01",
            "end_date": "2024-12-31",
            "rates": {"Software Developer": 125, "QA Engineer": 95, "Tech Lead": 175},
            "payment_terms": "Net 45",
        },
        "po": {
            "po_number": "PO-TECH-001",
            "order_date": "2024-03-15",
            "line_items": [
                {"description": "Software Developer", "quantity": 80, "unit_price": 125, "total": 10000},
                {"description": "QA Engineer", "quantity": 40, "unit_price": 95, "total": 3800},
            ],
            "total_amount": 13800,
        },
        "invoice": {
            "invoice_number": "INV-TECH-001",
            "invoice_date": "2024-04-15",
            "po_number": "PO-TECH-001",
            "line_items": [
                {"description": "Software Developer", "quantity": 80, "unit_price": 125, "total": 10000},
                {"description": "QA Engineer", "quantity": 40, "unit_price": 95, "total": 3800},
            ],
            "total_amount": 13800,
            "payment_terms": "Net 45",
        },
    },
    "exact_03": {
        "vendor": "DataWise Analytics",
        "description": "Perfect match - Data analysis project",
        "expected_result": "PASS",
        "expected_matches": 3,
        "contract": {
            "effective_date": "2024-02-01",
            "end_date": "2025-01-31",
            "rates": {"Data Analyst": 110, "Data Scientist": 160, "ML Engineer": 180},
            "payment_terms": "Net 30",
        },
        "po": {
            "po_number": "PO-DATA-001",
            "order_date": "2024-05-01",
            "line_items": [
                {"description": "Data Scientist", "quantity": 60, "unit_price": 160, "total": 9600},
            ],
            "total_amount": 9600,
        },
        "invoice": {
            "invoice_number": "INV-DATA-001",
            "invoice_date": "2024-05-31",
            "po_number": "PO-DATA-001",
            "line_items": [
                {"description": "Data Scientist", "quantity": 60, "unit_price": 160, "total": 9600},
            ],
            "total_amount": 9600,
            "payment_terms": "Net 30",
        },
    },
    "exact_04": {
        "vendor": "CloudScale Infrastructure",
        "description": "Perfect match - Cloud services",
        "expected_result": "PASS",
        "expected_matches": 3,
        "contract": {
            "effective_date": "2024-01-01",
            "end_date": "2024-12-31",
            "rates": {"Cloud Architect": 200, "DevOps Engineer": 140, "SRE": 155},
            "payment_terms": "Net 15",
        },
        "po": {
            "po_number": "PO-CLOUD-001",
            "order_date": "2024-07-01",
            "line_items": [
                {"description": "Cloud Architect", "quantity": 20, "unit_price": 200, "total": 4000},
                {"description": "DevOps Engineer", "quantity": 40, "unit_price": 140, "total": 5600},
            ],
            "total_amount": 9600,
        },
        "invoice": {
            "invoice_number": "INV-CLOUD-001",
            "invoice_date": "2024-07-31",
            "po_number": "PO-CLOUD-001",
            "line_items": [
                {"description": "Cloud Architect", "quantity": 20, "unit_price": 200, "total": 4000},
                {"description": "DevOps Engineer", "quantity": 40, "unit_price": 140, "total": 5600},
            ],
            "total_amount": 9600,
            "payment_terms": "Net 15",
        },
    },
    "exact_05": {
        "vendor": "SecureNet Cyber",
        "description": "Perfect match - Security audit",
        "expected_result": "PASS",
        "expected_matches": 3,
        "contract": {
            "effective_date": "2024-03-01",
            "end_date": "2025-02-28",
            "rates": {"Security Analyst": 130, "Penetration Tester": 175, "Security Architect": 210},
            "payment_terms": "Net 30",
        },
        "po": {
            "po_number": "PO-SEC-001",
            "order_date": "2024-06-15",
            "line_items": [
                {"description": "Penetration Tester", "quantity": 40, "unit_price": 175, "total": 7000},
            ],
            "total_amount": 7000,
        },
        "invoice": {
            "invoice_number": "INV-SEC-001",
            "invoice_date": "2024-07-15",
            "po_number": "PO-SEC-001",
            "line_items": [
                {"description": "Penetration Tester", "quantity": 40, "unit_price": 175, "total": 7000},
            ],
            "total_amount": 7000,
            "payment_terms": "Net 30",
        },
    },
    "exact_06": {
        "vendor": "DesignHub Creative",
        "description": "Perfect match - UX design project",
        "expected_result": "PASS",
        "expected_matches": 3,
        "contract": {
            "effective_date": "2024-04-01",
            "end_date": "2024-12-31",
            "rates": {"UX Designer": 120, "UI Designer": 115, "Product Designer": 140},
            "payment_terms": "Net 30",
        },
        "po": {
            "po_number": "PO-DESIGN-001",
            "order_date": "2024-05-01",
            "line_items": [
                {"description": "UX Designer", "quantity": 80, "unit_price": 120, "total": 9600},
                {"description": "UI Designer", "quantity": 40, "unit_price": 115, "total": 4600},
            ],
            "total_amount": 14200,
        },
        "invoice": {
            "invoice_number": "INV-DESIGN-001",
            "invoice_date": "2024-06-01",
            "po_number": "PO-DESIGN-001",
            "line_items": [
                {"description": "UX Designer", "quantity": 80, "unit_price": 120, "total": 9600},
                {"description": "UI Designer", "quantity": 40, "unit_price": 115, "total": 4600},
            ],
            "total_amount": 14200,
            "payment_terms": "Net 30",
        },
    },
    "exact_07": {
        "vendor": "AgileWorks PM",
        "description": "Perfect match - Project management",
        "expected_result": "PASS",
        "expected_matches": 3,
        "contract": {
            "effective_date": "2024-01-01",
            "end_date": "2024-12-31",
            "rates": {"Project Manager": 135, "Scrum Master": 125, "Business Analyst": 115},
            "payment_terms": "Net 30",
        },
        "po": {
            "po_number": "PO-AGILE-001",
            "order_date": "2024-08-01",
            "line_items": [
                {"description": "Project Manager", "quantity": 60, "unit_price": 135, "total": 8100},
                {"description": "Scrum Master", "quantity": 40, "unit_price": 125, "total": 5000},
            ],
            "total_amount": 13100,
        },
        "invoice": {
            "invoice_number": "INV-AGILE-001",
            "invoice_date": "2024-08-31",
            "po_number": "PO-AGILE-001",
            "line_items": [
                {"description": "Project Manager", "quantity": 60, "unit_price": 135, "total": 8100},
                {"description": "Scrum Master", "quantity": 40, "unit_price": 125, "total": 5000},
            ],
            "total_amount": 13100,
            "payment_terms": "Net 30",
        },
    },

    # =========================================================================
    # PARTIAL MATCH SCENARIOS (2) - 2 of 3 matches should PASS
    # =========================================================================
    "partial_01": {
        "vendor": "BudgetTech Services",
        "description": "Partial match - Invoice matches PO but rate exceeds contract",
        "expected_result": "FAIL",  # Only 1 of 3 matches pass
        "expected_matches": 1,
        "notes": "Invoice↔PO: PASS, Invoice↔Contract: FAIL (rate), PO↔Contract: FAIL (rate)",
        "contract": {
            "effective_date": "2024-01-01",
            "end_date": "2024-12-31",
            "rates": {"Developer": 100},  # Contract rate is $100
            "payment_terms": "Net 30",
        },
        "po": {
            "po_number": "PO-BUDGET-001",
            "order_date": "2024-06-01",
            "line_items": [
                {"description": "Developer", "quantity": 50, "unit_price": 130, "total": 6500}  # PO has $130 (exceeds contract)
            ],
            "total_amount": 6500,
        },
        "invoice": {
            "invoice_number": "INV-BUDGET-001",
            "invoice_date": "2024-06-30",
            "po_number": "PO-BUDGET-001",
            "line_items": [
                {"description": "Developer", "quantity": 50, "unit_price": 130, "total": 6500}  # Matches PO exactly
            ],
            "total_amount": 6500,
            "payment_terms": "Net 30",
        },
    },
    "partial_02": {
        "vendor": "FlexiStaff Solutions",
        "description": "Partial match - Invoice matches contract but quantity differs from PO",
        "expected_result": "PASS",  # 2 of 3 matches pass
        "expected_matches": 2,
        "notes": "Invoice↔PO: FAIL (quantity), Invoice↔Contract: PASS, PO↔Contract: PASS",
        "contract": {
            "effective_date": "2024-01-01",
            "end_date": "2024-12-31",
            "rates": {"Consultant": 120},
            "payment_terms": "Net 30",
        },
        "po": {
            "po_number": "PO-FLEXI-001",
            "order_date": "2024-05-01",
            "line_items": [
                {"description": "Consultant", "quantity": 40, "unit_price": 120, "total": 4800}
            ],
            "total_amount": 4800,
        },
        "invoice": {
            "invoice_number": "INV-FLEXI-001",
            "invoice_date": "2024-05-31",
            "po_number": "PO-FLEXI-001",
            "line_items": [
                {"description": "Consultant", "quantity": 60, "unit_price": 120, "total": 7200}  # Different quantity
            ],
            "total_amount": 7200,  # Different total
            "payment_terms": "Net 30",
        },
    },

    # =========================================================================
    # FULL MISMATCH SCENARIOS (3) - Fewer than 2 matches pass = FAIL
    # =========================================================================
    "mismatch_01": {
        "vendor": "GhostVendor Inc",
        "description": "Full mismatch - No contract exists for vendor",
        "expected_result": "FAIL",
        "expected_matches": 0,
        "notes": "No contract indexed for this vendor",
        "contract": None,  # No contract
        "po": {
            "po_number": "PO-GHOST-001",
            "order_date": "2024-06-01",
            "line_items": [
                {"description": "Mystery Service", "quantity": 10, "unit_price": 500, "total": 5000}
            ],
            "total_amount": 5000,
        },
        "invoice": {
            "invoice_number": "INV-GHOST-001",
            "invoice_date": "2024-06-30",
            "po_number": "PO-GHOST-001",
            "line_items": [
                {"description": "Mystery Service", "quantity": 10, "unit_price": 500, "total": 5000}
            ],
            "total_amount": 5000,
            "payment_terms": "Net 30",
        },
    },
    "mismatch_02": {
        "vendor": "ExpiredContract LLC",
        "description": "Full mismatch - Invoice outside contract period with wrong rates",
        "expected_result": "FAIL",
        "expected_matches": 0,
        "notes": "All matches fail: dates outside period, rates exceed limits, quantities mismatch",
        "contract": {
            "effective_date": "2023-01-01",
            "end_date": "2023-12-31",  # Contract expired in 2023
            "rates": {"Engineer": 100},
            "payment_terms": "Net 30",
        },
        "po": {
            "po_number": "PO-EXPIRED-001",
            "order_date": "2024-06-01",  # Outside contract period
            "line_items": [
                {"description": "Engineer", "quantity": 30, "unit_price": 180, "total": 5400}  # Wrong rate
            ],
            "total_amount": 5400,
        },
        "invoice": {
            "invoice_number": "INV-EXPIRED-001",
            "invoice_date": "2024-06-30",  # Outside contract period
            "po_number": "PO-EXPIRED-001",
            "line_items": [
                {"description": "Engineer", "quantity": 50, "unit_price": 200, "total": 10000}  # Different qty and rate
            ],
            "total_amount": 10000,
            "payment_terms": "Net 60",  # Different terms
        },
    },
    "mismatch_03": {
        "vendor": "ChaosVendor Corp",
        "description": "Full mismatch - Everything is wrong",
        "expected_result": "FAIL",
        "expected_matches": 0,
        "notes": "Invoice doesn't match PO, rates exceed contract, dates questionable",
        "contract": {
            "effective_date": "2024-01-01",
            "end_date": "2024-12-31",
            "rates": {"Specialist": 150},
            "payment_terms": "Net 30",
        },
        "po": {
            "po_number": "PO-CHAOS-001",
            "order_date": "2024-04-01",
            "line_items": [
                {"description": "Specialist", "quantity": 20, "unit_price": 150, "total": 3000}
            ],
            "total_amount": 3000,
        },
        "invoice": {
            "invoice_number": "INV-CHAOS-001",
            "invoice_date": "2024-04-30",
            "po_number": "PO-CHAOS-999",  # Wrong PO number
            "line_items": [
                {"description": "Premium Specialist", "quantity": 100, "unit_price": 300, "total": 30000}  # Completely different
            ],
            "total_amount": 30000,
            "payment_terms": "Net 90",
        },
    },
}


def generate_contract_markdown(scenario_id: str, scenario: Dict) -> str:
    """Generate contract markdown text from scenario data."""
    if scenario["contract"] is None:
        return None

    contract = scenario["contract"]
    vendor = scenario["vendor"]

    # Build rate card section
    rate_lines = []
    for role, rate in contract["rates"].items():
        rate_lines.append(f"- {role}: ${rate} per hour")
    rate_card = "\n".join(rate_lines)

    markdown = f"""# Master Service Agreement - {vendor}

## Contract Information

**Vendor:** {vendor}
**Contract Type:** Master Service Agreement (MSA)

## Effective Period

This agreement is effective from {contract['effective_date']} and terminates on {contract['end_date']}.

All services must be delivered within this period. Invoices dated outside this period will not be honored.

## Rate Card

The following hourly rates apply to all services provided under this agreement:

{rate_card}

All rates are in USD and are fixed for the duration of this contract.
Rate increases require written amendment to this agreement.

## Payment Terms

{contract['payment_terms']} - All invoices are due within {contract['payment_terms'].replace('Net ', '')} days of receipt.

Late payments may incur a 1.5% monthly interest charge.

## Invoicing Requirements

1. All invoices must reference a valid Purchase Order number
2. Line items must match PO quantities and rates
3. Invoice date must fall within contract period
4. Itemized breakdown of hours and rates required

## General Terms

This agreement represents the entire understanding between the parties.
Any modifications must be in writing and signed by both parties.
"""
    return markdown


def generate_po_data(scenario_id: str, scenario: Dict) -> Dict:
    """Generate PO data structure from scenario."""
    po = scenario["po"]
    return {
        "po_number": po["po_number"],
        "vendor_name": scenario["vendor"],
        "order_date": po["order_date"],
        "expected_delivery_date": None,
        "total_amount": po["total_amount"],
        "currency": "USD",
        "line_items": po["line_items"],
        "payment_terms": scenario["contract"]["payment_terms"] if scenario["contract"] else "Net 30",
        "billing_address": "123 Corporate Way, Business City, BC 12345",
        "shipping_address": None,
        "contract_reference": f"MSA-{scenario['vendor'].replace(' ', '-').upper()}-2024" if scenario["contract"] else None,
        "notes": scenario.get("notes", ""),
    }


def generate_invoice_data(scenario_id: str, scenario: Dict) -> Dict:
    """Generate invoice data structure from scenario."""
    invoice = scenario["invoice"]
    return {
        "vendor_name": scenario["vendor"],
        "invoice_number": invoice["invoice_number"],
        "invoice_date": invoice["invoice_date"],
        "due_date": None,
        "po_number": invoice.get("po_number"),
        "total_amount": invoice["total_amount"],
        "currency": "USD",
        "line_items": invoice["line_items"],
        "payment_terms": invoice.get("payment_terms", "Net 30"),
        "billing_address": "123 Corporate Way, Business City, BC 12345",
    }


def generate_expected_results(scenario_id: str, scenario: Dict) -> Dict:
    """Generate expected evaluation results for a scenario."""
    return {
        "scenario_id": scenario_id,
        "vendor": scenario["vendor"],
        "description": scenario["description"],
        "expected_status": scenario["expected_result"],
        "expected_matches_passed": scenario["expected_matches"],
        "notes": scenario.get("notes", ""),
        "has_contract": scenario["contract"] is not None,
        "po_number": scenario["po"]["po_number"],
        "invoice_number": scenario["invoice"]["invoice_number"],
    }


def save_all_data():
    """Generate and save all synthetic data files."""
    contracts_dir = EVAL_DATA_DIR / "contracts"
    pos_dir = EVAL_DATA_DIR / "pos"
    invoices_dir = EVAL_DATA_DIR / "invoices"

    # Ensure directories exist
    contracts_dir.mkdir(parents=True, exist_ok=True)
    pos_dir.mkdir(parents=True, exist_ok=True)
    invoices_dir.mkdir(parents=True, exist_ok=True)

    # Collect all data
    all_contracts = {}
    all_pos = {}
    all_invoices = {}
    expected_results = []

    for scenario_id, scenario in SCENARIOS.items():
        print(f"Generating data for {scenario_id}: {scenario['vendor']}")

        # Contract
        contract_md = generate_contract_markdown(scenario_id, scenario)
        if contract_md:
            all_contracts[scenario_id] = {
                "vendor_name": scenario["vendor"],
                "contract_type": "MSA",
                "markdown": contract_md,
            }

        # PO
        all_pos[scenario_id] = generate_po_data(scenario_id, scenario)

        # Invoice
        all_invoices[scenario_id] = generate_invoice_data(scenario_id, scenario)

        # Expected results
        expected_results.append(generate_expected_results(scenario_id, scenario))

    # Save to files
    with open(contracts_dir / "contracts.json", "w") as f:
        json.dump(all_contracts, f, indent=2)

    with open(pos_dir / "purchase_orders.json", "w") as f:
        json.dump(all_pos, f, indent=2)

    with open(invoices_dir / "invoices.json", "w") as f:
        json.dump(all_invoices, f, indent=2)

    with open(EVAL_DATA_DIR / "expected_results.json", "w") as f:
        json.dump(expected_results, f, indent=2)

    # Save scenario summary
    summary = {
        "total_scenarios": len(SCENARIOS),
        "exact_match_count": 7,
        "partial_match_count": 2,
        "mismatch_count": 3,
        "scenarios": {
            sid: {
                "vendor": s["vendor"],
                "description": s["description"],
                "expected_result": s["expected_result"],
                "expected_matches": s["expected_matches"],
            }
            for sid, s in SCENARIOS.items()
        }
    }

    with open(EVAL_DATA_DIR / "scenario_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nGenerated data saved to {EVAL_DATA_DIR}")
    print(f"  - {len(all_contracts)} contracts")
    print(f"  - {len(all_pos)} purchase orders")
    print(f"  - {len(all_invoices)} invoices")
    print(f"  - {len(expected_results)} expected results")


if __name__ == "__main__":
    save_all_data()
