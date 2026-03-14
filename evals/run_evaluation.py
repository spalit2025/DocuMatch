"""
Evaluation Runner for DocuMatch Three-Way Matching

This script:
1. Loads synthetic test data (contracts, POs, invoices)
2. Indexes contracts and POs into ChromaDB
3. Runs three-way matching on each invoice
4. Compares results to expected outcomes
5. Calculates evaluation metrics
6. Generates a detailed report
"""

import json
import sys
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.vector_store import VectorStore
from core.po_store import POStore
from core.matcher import Matcher
from core.models import InvoiceSchema, PurchaseOrderSchema, LineItem, ThreeWayMatchResult

# Eval data directory
EVAL_DATA_DIR = Path(__file__).parent / "data"


@dataclass
class EvalResult:
    """Result of evaluating a single scenario."""
    scenario_id: str
    vendor: str
    description: str

    # Expected values
    expected_status: str
    expected_matches: int

    # Actual values
    actual_status: str
    actual_matches: int

    # Individual match results
    invoice_po_passed: bool = None
    invoice_contract_passed: bool = None
    po_contract_passed: bool = None

    # Scores
    overall_score: float = 0.0

    # Correctness
    status_correct: bool = False
    matches_correct: bool = False

    # Issues found
    issues: List[str] = field(default_factory=list)

    # Error if any
    error: str = None


@dataclass
class EvalMetrics:
    """Aggregated evaluation metrics."""
    total_scenarios: int = 0

    # Status prediction accuracy
    status_correct: int = 0
    status_accuracy: float = 0.0

    # Match count accuracy
    matches_correct: int = 0
    matches_accuracy: float = 0.0

    # By category
    exact_match_results: List[EvalResult] = field(default_factory=list)
    partial_match_results: List[EvalResult] = field(default_factory=list)
    mismatch_results: List[EvalResult] = field(default_factory=list)

    # Category accuracies
    exact_match_accuracy: float = 0.0
    partial_match_accuracy: float = 0.0
    mismatch_accuracy: float = 0.0

    # Confusion matrix for status
    true_pass: int = 0  # Expected PASS, Got PASS
    false_pass: int = 0  # Expected FAIL, Got PASS
    true_fail: int = 0  # Expected FAIL, Got FAIL
    false_fail: int = 0  # Expected PASS, Got FAIL

    # Precision/Recall for PASS status
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0


class EvaluationRunner:
    """Runs evaluation of the three-way matching system."""

    def __init__(self, use_temp_db: bool = True):
        """
        Initialize the evaluation runner.

        Args:
            use_temp_db: If True, use a temporary database (clean slate)
        """
        self.use_temp_db = use_temp_db
        self.temp_dir = None
        self.vector_store = None
        self.po_store = None
        self.matcher = None

        # Load test data
        self.contracts = self._load_json("contracts/contracts.json")
        self.pos = self._load_json("pos/purchase_orders.json")
        self.invoices = self._load_json("invoices/invoices.json")
        self.expected_results = self._load_json("expected_results.json")
        self.scenario_summary = self._load_json("scenario_summary.json")

    def _load_json(self, relative_path: str) -> Any:
        """Load JSON file from eval data directory."""
        path = EVAL_DATA_DIR / relative_path
        if not path.exists():
            raise FileNotFoundError(f"Data file not found: {path}")
        with open(path) as f:
            return json.load(f)

    def setup(self):
        """Set up the evaluation environment."""
        print("=" * 60)
        print("SETTING UP EVALUATION ENVIRONMENT")
        print("=" * 60)

        if self.use_temp_db:
            self.temp_dir = tempfile.mkdtemp(prefix="documatch_eval_")
            db_path = self.temp_dir
            print(f"Using temporary database: {db_path}")
        else:
            db_path = str(project_root / "data" / "chroma_db_eval")
            print(f"Using persistent database: {db_path}")

        # Initialize stores
        self.vector_store = VectorStore(
            persist_directory=db_path,
            chunk_size=500,
            chunk_overlap=50
        )
        self.po_store = POStore(persist_directory=db_path)
        self.matcher = Matcher(
            vector_store=self.vector_store,
            po_store=self.po_store,
            match_tolerance=0.01
        )

        print("Stores initialized successfully")

    def index_contracts(self):
        """Index all contracts into the vector store."""
        print("\n" + "-" * 40)
        print("INDEXING CONTRACTS")
        print("-" * 40)

        indexed_count = 0
        for scenario_id, contract_data in self.contracts.items():
            vendor = contract_data["vendor_name"]
            markdown = contract_data["markdown"]
            contract_type = contract_data["contract_type"]

            try:
                self.vector_store.index_contract(
                    text=markdown,
                    vendor_name=vendor,
                    contract_type=contract_type
                )
                indexed_count += 1
                print(f"  ✓ Indexed contract for {vendor}")
            except Exception as e:
                print(f"  ✗ Failed to index contract for {vendor}: {e}")

        print(f"\nIndexed {indexed_count}/{len(self.contracts)} contracts")

    def index_pos(self):
        """Index all POs into the PO store."""
        print("\n" + "-" * 40)
        print("INDEXING PURCHASE ORDERS")
        print("-" * 40)

        indexed_count = 0
        for scenario_id, po_data in self.pos.items():
            try:
                # Convert line items
                line_items = [
                    LineItem(**item) for item in po_data["line_items"]
                ]

                po = PurchaseOrderSchema(
                    po_number=po_data["po_number"],
                    vendor_name=po_data["vendor_name"],
                    order_date=po_data["order_date"],
                    total_amount=po_data["total_amount"],
                    currency=po_data.get("currency", "USD"),
                    line_items=line_items,
                    payment_terms=po_data.get("payment_terms"),
                    contract_reference=po_data.get("contract_reference"),
                    notes=po_data.get("notes"),
                )

                self.po_store.index_po(po)
                indexed_count += 1
                print(f"  ✓ Indexed PO {po_data['po_number']} for {po_data['vendor_name']}")
            except Exception as e:
                print(f"  ✗ Failed to index PO {po_data.get('po_number', 'unknown')}: {e}")

        print(f"\nIndexed {indexed_count}/{len(self.pos)} POs")

    def run_evaluation(self) -> List[EvalResult]:
        """Run evaluation on all scenarios."""
        print("\n" + "=" * 60)
        print("RUNNING THREE-WAY MATCHING EVALUATION")
        print("=" * 60)

        results = []

        for expected in self.expected_results:
            scenario_id = expected["scenario_id"]
            print(f"\n--- Evaluating: {scenario_id} ({expected['vendor']}) ---")
            print(f"    Expected: {expected['expected_status']} with {expected['expected_matches_passed']} matches")

            result = self._evaluate_scenario(scenario_id, expected)
            results.append(result)

            if result.error:
                print(f"    ERROR: {result.error}")
            else:
                status_icon = "✓" if result.status_correct else "✗"
                matches_icon = "✓" if result.matches_correct else "✗"
                print(f"    Actual:   {result.actual_status} with {result.actual_matches} matches")
                print(f"    Status:   {status_icon} | Matches: {matches_icon}")

        return results

    def _evaluate_scenario(self, scenario_id: str, expected: Dict) -> EvalResult:
        """Evaluate a single scenario."""
        result = EvalResult(
            scenario_id=scenario_id,
            vendor=expected["vendor"],
            description=expected["description"],
            expected_status=expected["expected_status"],
            expected_matches=expected["expected_matches_passed"],
            actual_status="ERROR",
            actual_matches=0,
        )

        try:
            # Get invoice data
            invoice_data = self.invoices[scenario_id]

            # Convert to InvoiceSchema
            line_items = [
                LineItem(**item) for item in invoice_data["line_items"]
            ]

            invoice = InvoiceSchema(
                vendor_name=invoice_data["vendor_name"],
                invoice_number=invoice_data["invoice_number"],
                invoice_date=invoice_data["invoice_date"],
                po_number=invoice_data.get("po_number"),
                total_amount=invoice_data["total_amount"],
                currency=invoice_data.get("currency", "USD"),
                line_items=line_items,
                payment_terms=invoice_data.get("payment_terms"),
            )

            # Run three-way matching
            match_result = self.matcher.validate_invoice_three_way(
                invoice=invoice,
                po_number=invoice_data.get("po_number")
            )

            # Extract results
            result.actual_status = match_result.status
            result.actual_matches = match_result.matches_passed
            result.overall_score = match_result.overall_score

            # Individual match results
            if match_result.invoice_po_match:
                result.invoice_po_passed = match_result.invoice_po_match.passed
            if match_result.invoice_contract_match:
                result.invoice_contract_passed = match_result.invoice_contract_match.passed
            if match_result.po_contract_match:
                result.po_contract_passed = match_result.po_contract_match.passed

            # Collect issues
            result.issues = [
                f"[{issue.severity}] {issue.rule}: {issue.message}"
                for issue in match_result.all_issues
            ]

            # Check correctness
            result.status_correct = (result.actual_status == result.expected_status)
            result.matches_correct = (result.actual_matches == result.expected_matches)

        except Exception as e:
            result.error = str(e)

        return result

    def calculate_metrics(self, results: List[EvalResult]) -> EvalMetrics:
        """Calculate evaluation metrics from results."""
        metrics = EvalMetrics()
        metrics.total_scenarios = len(results)

        for result in results:
            # Skip errors
            if result.error:
                continue

            # Status accuracy
            if result.status_correct:
                metrics.status_correct += 1

            # Matches accuracy
            if result.matches_correct:
                metrics.matches_correct += 1

            # Confusion matrix
            if result.expected_status == "PASS":
                if result.actual_status == "PASS":
                    metrics.true_pass += 1
                else:
                    metrics.false_fail += 1
            else:  # Expected FAIL
                if result.actual_status == "PASS":
                    metrics.false_pass += 1
                else:
                    metrics.true_fail += 1

            # Categorize by scenario type
            if result.scenario_id.startswith("exact"):
                metrics.exact_match_results.append(result)
            elif result.scenario_id.startswith("partial"):
                metrics.partial_match_results.append(result)
            elif result.scenario_id.startswith("mismatch"):
                metrics.mismatch_results.append(result)

        # Calculate accuracies
        valid_count = len([r for r in results if not r.error])
        if valid_count > 0:
            metrics.status_accuracy = metrics.status_correct / valid_count
            metrics.matches_accuracy = metrics.matches_correct / valid_count

        # Category accuracies
        if metrics.exact_match_results:
            correct = sum(1 for r in metrics.exact_match_results if r.status_correct)
            metrics.exact_match_accuracy = correct / len(metrics.exact_match_results)

        if metrics.partial_match_results:
            correct = sum(1 for r in metrics.partial_match_results if r.status_correct)
            metrics.partial_match_accuracy = correct / len(metrics.partial_match_results)

        if metrics.mismatch_results:
            correct = sum(1 for r in metrics.mismatch_results if r.status_correct)
            metrics.mismatch_accuracy = correct / len(metrics.mismatch_results)

        # Precision, Recall, F1 for PASS prediction
        if (metrics.true_pass + metrics.false_pass) > 0:
            metrics.precision = metrics.true_pass / (metrics.true_pass + metrics.false_pass)

        if (metrics.true_pass + metrics.false_fail) > 0:
            metrics.recall = metrics.true_pass / (metrics.true_pass + metrics.false_fail)

        if (metrics.precision + metrics.recall) > 0:
            metrics.f1_score = 2 * (metrics.precision * metrics.recall) / (metrics.precision + metrics.recall)

        return metrics

    def generate_report(self, results: List[EvalResult], metrics: EvalMetrics) -> str:
        """Generate a detailed evaluation report."""
        lines = []

        lines.append("=" * 70)
        lines.append("DOCUMATCH THREE-WAY MATCHING EVALUATION REPORT")
        lines.append("=" * 70)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Summary
        lines.append("-" * 70)
        lines.append("SUMMARY")
        lines.append("-" * 70)
        lines.append(f"Total Scenarios:     {metrics.total_scenarios}")
        lines.append(f"  - Exact Match:     {len(metrics.exact_match_results)}")
        lines.append(f"  - Partial Match:   {len(metrics.partial_match_results)}")
        lines.append(f"  - Full Mismatch:   {len(metrics.mismatch_results)}")
        lines.append("")

        # Overall Metrics
        lines.append("-" * 70)
        lines.append("OVERALL METRICS")
        lines.append("-" * 70)
        lines.append(f"Status Accuracy:     {metrics.status_accuracy:.1%} ({metrics.status_correct}/{metrics.total_scenarios})")
        lines.append(f"Matches Accuracy:    {metrics.matches_accuracy:.1%} ({metrics.matches_correct}/{metrics.total_scenarios})")
        lines.append("")
        lines.append("Precision (PASS):    {:.1%}".format(metrics.precision))
        lines.append("Recall (PASS):       {:.1%}".format(metrics.recall))
        lines.append("F1 Score:            {:.1%}".format(metrics.f1_score))
        lines.append("")

        # Confusion Matrix
        lines.append("-" * 70)
        lines.append("CONFUSION MATRIX (Status Prediction)")
        lines.append("-" * 70)
        lines.append("                    Predicted")
        lines.append("                    PASS    FAIL")
        lines.append(f"Actual PASS         {metrics.true_pass:4}    {metrics.false_fail:4}")
        lines.append(f"       FAIL         {metrics.false_pass:4}    {metrics.true_fail:4}")
        lines.append("")

        # Category Breakdown
        lines.append("-" * 70)
        lines.append("ACCURACY BY CATEGORY")
        lines.append("-" * 70)
        lines.append(f"Exact Match (7):     {metrics.exact_match_accuracy:.1%}")
        lines.append(f"Partial Match (2):   {metrics.partial_match_accuracy:.1%}")
        lines.append(f"Full Mismatch (3):   {metrics.mismatch_accuracy:.1%}")
        lines.append("")

        # Detailed Results
        lines.append("-" * 70)
        lines.append("DETAILED RESULTS")
        lines.append("-" * 70)

        for result in results:
            status_icon = "✓" if result.status_correct else "✗"
            matches_icon = "✓" if result.matches_correct else "✗"

            lines.append(f"\n{result.scenario_id}: {result.vendor}")
            lines.append(f"  Description: {result.description}")
            lines.append(f"  Expected: {result.expected_status} ({result.expected_matches} matches)")
            lines.append(f"  Actual:   {result.actual_status} ({result.actual_matches} matches)")
            lines.append(f"  Status: {status_icon} | Matches: {matches_icon} | Score: {result.overall_score:.2f}")

            # Individual match details
            if result.invoice_po_passed is not None:
                lines.append(f"    Invoice↔PO: {'PASS' if result.invoice_po_passed else 'FAIL'}")
            if result.invoice_contract_passed is not None:
                lines.append(f"    Invoice↔Contract: {'PASS' if result.invoice_contract_passed else 'FAIL'}")
            if result.po_contract_passed is not None:
                lines.append(f"    PO↔Contract: {'PASS' if result.po_contract_passed else 'FAIL'}")

            if result.error:
                lines.append(f"  ERROR: {result.error}")

            if result.issues:
                lines.append(f"  Issues ({len(result.issues)}):")
                for issue in result.issues[:5]:  # Limit to first 5
                    lines.append(f"    - {issue}")
                if len(result.issues) > 5:
                    lines.append(f"    ... and {len(result.issues) - 5} more")

        lines.append("")
        lines.append("=" * 70)
        lines.append("END OF REPORT")
        lines.append("=" * 70)

        return "\n".join(lines)

    def cleanup(self):
        """Clean up temporary resources."""
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
            print(f"\nCleaned up temporary database: {self.temp_dir}")

    def run(self) -> Tuple[List[EvalResult], EvalMetrics, str]:
        """Run the complete evaluation pipeline."""
        try:
            # Setup
            self.setup()

            # Index data
            self.index_contracts()
            self.index_pos()

            # Run evaluation
            results = self.run_evaluation()

            # Calculate metrics
            metrics = self.calculate_metrics(results)

            # Generate report
            report = self.generate_report(results, metrics)

            return results, metrics, report

        finally:
            self.cleanup()


def metrics_to_json(metrics: EvalMetrics, results: List[EvalResult]) -> dict:
    """Convert metrics to a JSON-serializable dict for CI/programmatic access."""
    return {
        "total_scenarios": metrics.total_scenarios,
        "status_accuracy": round(metrics.status_accuracy, 4),
        "matches_accuracy": round(metrics.matches_accuracy, 4),
        "precision": round(metrics.precision, 4),
        "recall": round(metrics.recall, 4),
        "f1_score": round(metrics.f1_score, 4),
        "confusion_matrix": {
            "true_pass": metrics.true_pass,
            "false_pass": metrics.false_pass,
            "true_fail": metrics.true_fail,
            "false_fail": metrics.false_fail,
        },
        "by_category": {
            "exact_match": round(metrics.exact_match_accuracy, 4),
            "partial_match": round(metrics.partial_match_accuracy, 4),
            "mismatch": round(metrics.mismatch_accuracy, 4),
        },
        "scenarios": [
            {
                "id": r.scenario_id,
                "vendor": r.vendor,
                "expected": r.expected_status,
                "actual": r.actual_status,
                "correct": r.status_correct,
            }
            for r in results if not r.error
        ],
    }


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="DocuMatch Evaluation Suite")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--ci", action="store_true", help="CI mode: JSON output + exit code")
    args = parser.parse_args()

    # First, generate synthetic data if not exists
    expected_path = EVAL_DATA_DIR / "expected_results.json"
    if not expected_path.exists():
        if not args.json and not args.ci:
            print("Generating synthetic test data...")
        from synthetic_data import save_all_data
        save_all_data()

    # Run evaluation
    runner = EvaluationRunner(use_temp_db=True)
    results, metrics, report = runner.run()

    # Output based on mode
    if args.json or args.ci:
        summary = metrics_to_json(metrics, results)
        print(json.dumps(summary, indent=2))
    else:
        print("\n")
        print(report)

        # Save report
        report_path = EVAL_DATA_DIR / f"eval_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\nReport saved to: {report_path}")

    # Return exit code based on accuracy
    if metrics.status_accuracy >= 0.9:
        if not args.json:
            print("\n✓ Evaluation PASSED (>= 90% accuracy)")
        return 0
    else:
        if not args.json:
            print(f"\n✗ Evaluation NEEDS IMPROVEMENT ({metrics.status_accuracy:.1%} accuracy)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
