"""
Report Generator for DocuMatch Architect.

Generates human-readable validation reports from match results.
Extracted from matcher.py to keep report formatting separate from validation logic.
"""

from .models import MatchResult, ThreeWayMatchResult


def generate_report(result: MatchResult) -> str:
    """Generate a human-readable validation report."""
    lines = []

    # Header
    lines.append("=" * 60)
    lines.append("INVOICE VALIDATION REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Summary
    status_emoji = {"PASS": "\u2705", "FAIL": "\u274c", "REVIEW": "\u26a0\ufe0f"}.get(result.status, "\u2753")
    lines.append(f"Status: {status_emoji} {result.status}")
    lines.append(f"Vendor: {result.vendor_name}")
    lines.append(f"Invoice: {result.invoice_number}")
    lines.append(f"Confidence: {result.confidence_score:.0%}")
    lines.append(f"Timestamp: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Issue Summary
    summary = result.issue_summary
    lines.append("-" * 40)
    lines.append("ISSUE SUMMARY")
    lines.append("-" * 40)
    lines.append(f"  Critical: {summary['critical']}")
    lines.append(f"  Errors:   {summary['error']}")
    lines.append(f"  Warnings: {summary['warning']}")
    lines.append(f"  Info:     {summary['info']}")
    lines.append("")

    # Detailed Issues
    if result.issues:
        lines.append("-" * 40)
        lines.append("DETAILED ISSUES")
        lines.append("-" * 40)

        for issue in result.issues:
            severity_icon = {
                "critical": "\U0001f534",
                "error": "\U0001f7e0",
                "warning": "\U0001f7e1",
                "info": "\U0001f535"
            }.get(issue.severity, "\u26aa")

            lines.append(f"\n{severity_icon} [{issue.severity.upper()}] {issue.rule}")
            lines.append(f"   {issue.message}")
            if issue.contract_value is not None:
                lines.append(f"   Invoice: {issue.invoice_value} | Contract: {issue.contract_value}")

    # Matched Clauses
    if result.matched_clauses:
        lines.append("")
        lines.append("-" * 40)
        lines.append("MATCHED CONTRACT CLAUSES")
        lines.append("-" * 40)

        for i, clause in enumerate(result.matched_clauses[:5]):  # Show top 5
            lines.append(f"\n[{i+1}] Score: {clause.similarity_score:.2f}")
            preview = clause.text[:200] + "..." if len(clause.text) > 200 else clause.text
            lines.append(f"    {preview}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("END OF REPORT")
    lines.append("=" * 60)

    return "\n".join(lines)


def generate_three_way_report(result: ThreeWayMatchResult) -> str:
    """Generate a human-readable three-way validation report."""
    lines = []

    # Header
    lines.append("=" * 70)
    lines.append("THREE-WAY INVOICE VALIDATION REPORT")
    lines.append("=" * 70)
    lines.append("")

    # Summary
    status_emoji = {"PASS": "\u2705", "FAIL": "\u274c", "REVIEW": "\u26a0\ufe0f"}.get(result.status, "\u2753")
    lines.append(f"Status: {status_emoji} {result.status}")
    lines.append(f"Vendor: {result.vendor_name}")
    lines.append(f"Invoice: {result.invoice_number}")
    lines.append(f"PO: {result.po_number or 'N/A'}")
    lines.append(f"Overall Score: {result.overall_score:.0%}")
    lines.append(f"Matches Passed: {result.matches_passed}/{result.total_matches}")
    lines.append(f"Timestamp: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Three-Way Match Summary
    lines.append("-" * 50)
    lines.append("THREE-WAY MATCH SUMMARY")
    lines.append("-" * 50)

    def match_status(m):
        if m is None:
            return "\u26aa N/A"
        return f"{'\u2705' if m.passed else '\u274c'} {'PASS' if m.passed else 'FAIL'} ({m.score:.0%})"

    lines.append(f"  Match 1 (Invoice \u2194 PO):       {match_status(result.invoice_po_match)}")
    lines.append(f"  Match 2 (Invoice \u2194 Contract): {match_status(result.invoice_contract_match)}")
    lines.append(f"  Match 3 (PO \u2194 Contract):      {match_status(result.po_contract_match)}")
    lines.append("")

    # Result explanation
    if result.status == "PASS":
        lines.append(f"  \u2705 RESULT: {result.matches_passed} of {result.total_matches} matches passed \u2192 APPROVED")
    else:
        lines.append(f"  \u274c RESULT: Only {result.matches_passed} of {result.total_matches} matches passed \u2192 MANUAL REVIEW REQUIRED")
    lines.append("")

    # Issue Summary
    summary = result.issue_summary
    lines.append("-" * 50)
    lines.append("ISSUE SUMMARY")
    lines.append("-" * 50)
    lines.append(f"  Critical: {summary['critical']}")
    lines.append(f"  Errors:   {summary['error']}")
    lines.append(f"  Warnings: {summary['warning']}")
    lines.append(f"  Info:     {summary['info']}")
    lines.append("")

    # Detailed Issues by Match
    if result.all_issues:
        lines.append("-" * 50)
        lines.append("DETAILED ISSUES BY MATCH")
        lines.append("-" * 50)

        # Group issues by match type
        match_types = {
            "invoice_po": "Match 1 (Invoice \u2194 PO)",
            "invoice_contract": "Match 2 (Invoice \u2194 Contract)",
            "po_contract": "Match 3 (PO \u2194 Contract)",
        }

        for mt, mt_label in match_types.items():
            mt_issues = [i for i in result.all_issues if i.match_type == mt]
            if mt_issues:
                lines.append(f"\n{mt_label}:")
                for issue in mt_issues:
                    severity_icon = {
                        "critical": "\U0001f534",
                        "error": "\U0001f7e0",
                        "warning": "\U0001f7e1",
                        "info": "\U0001f535"
                    }.get(issue.severity, "\u26aa")
                    lines.append(f"  {severity_icon} [{issue.severity.upper()}] {issue.rule}")
                    lines.append(f"     {issue.message}")

    lines.append("")
    lines.append("=" * 70)
    lines.append("END OF REPORT")
    lines.append("=" * 70)

    return "\n".join(lines)
