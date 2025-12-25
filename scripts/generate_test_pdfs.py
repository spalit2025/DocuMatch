#!/usr/bin/env python3
"""Generate synthetic PDF files for testing the DocuMatch application."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from pathlib import Path
from datetime import date, timedelta


def create_contract_pdf(output_path: Path):
    """Create a professional services contract PDF."""
    doc = SimpleDocTemplate(str(output_path), pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=72)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=TA_CENTER,
        spaceAfter=30
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=20,
        spaceAfter=10
    )
    normal_style = styles['Normal']

    story = []

    # Title
    story.append(Paragraph("MASTER SERVICES AGREEMENT", title_style))
    story.append(Paragraph("Contract Number: MSA-2024-001", styles['Normal']))
    story.append(Spacer(1, 20))

    # Parties
    story.append(Paragraph("PARTIES", heading_style))
    story.append(Paragraph(
        "This Master Services Agreement (\"Agreement\") is entered into as of January 1, 2024, "
        "by and between:", normal_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>Client:</b> Acme Corporation, located at 123 Business Ave, San Francisco, CA 94102", normal_style))
    story.append(Paragraph("<b>Vendor:</b> TechPro Solutions Inc., located at 456 Tech Park, Austin, TX 78701", normal_style))
    story.append(Spacer(1, 10))

    # Term
    story.append(Paragraph("1. TERM", heading_style))
    story.append(Paragraph(
        "This Agreement shall be effective from <b>January 1, 2024</b> through <b>December 31, 2025</b>, "
        "unless earlier terminated in accordance with the provisions herein.", normal_style))

    # Services
    story.append(Paragraph("2. SERVICES", heading_style))
    story.append(Paragraph(
        "Vendor agrees to provide professional consulting and software development services "
        "as described in individual Statements of Work (SOW) issued under this Agreement.", normal_style))

    # Rate Card
    story.append(Paragraph("3. RATE CARD", heading_style))
    story.append(Paragraph(
        "The following hourly rates shall apply to services rendered under this Agreement:", normal_style))
    story.append(Spacer(1, 10))

    rate_data = [
        ['Role', 'Hourly Rate (USD)'],
        ['Senior Consultant', '$150.00'],
        ['Software Developer', '$125.00'],
        ['Project Manager', '$140.00'],
        ['Technical Architect', '$175.00'],
        ['Quality Analyst', '$100.00'],
    ]

    rate_table = Table(rate_data, colWidths=[3*inch, 2*inch])
    rate_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(rate_table)

    # Payment Terms
    story.append(Paragraph("4. PAYMENT TERMS", heading_style))
    story.append(Paragraph(
        "Payment shall be due within <b>Net 30</b> days of invoice receipt. "
        "Late payments shall accrue interest at 1.5% per month.", normal_style))

    # Signatures
    story.append(Spacer(1, 40))
    story.append(Paragraph("SIGNATURES", heading_style))
    story.append(Spacer(1, 20))

    sig_data = [
        ['For Acme Corporation:', 'For TechPro Solutions Inc.:'],
        ['', ''],
        ['_________________________', '_________________________'],
        ['Authorized Signatory', 'Authorized Signatory'],
        ['Date: January 1, 2024', 'Date: January 1, 2024'],
    ]

    sig_table = Table(sig_data, colWidths=[3*inch, 3*inch])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(sig_table)

    doc.build(story)
    print(f"Created contract: {output_path}")


def create_po_pdf(output_path: Path):
    """Create a purchase order PDF."""
    doc = SimpleDocTemplate(str(output_path), pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=72)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        alignment=TA_CENTER,
        spaceAfter=20
    )
    right_style = ParagraphStyle(
        'RightAlign',
        parent=styles['Normal'],
        alignment=TA_RIGHT
    )

    story = []

    # Header
    story.append(Paragraph("PURCHASE ORDER", title_style))
    story.append(Spacer(1, 10))

    # PO Details Table
    header_data = [
        ['PO Number:', 'PO-2024-0042'],
        ['Order Date:', 'March 15, 2024'],
        ['Contract Reference:', 'MSA-2024-001'],
    ]

    header_table = Table(header_data, colWidths=[1.5*inch, 2.5*inch])
    header_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 20))

    # Vendor and Bill To
    address_data = [
        ['VENDOR:', 'BILL TO:'],
        ['TechPro Solutions Inc.', 'Acme Corporation'],
        ['456 Tech Park', '123 Business Ave'],
        ['Austin, TX 78701', 'San Francisco, CA 94102'],
    ]

    address_table = Table(address_data, colWidths=[3*inch, 3*inch])
    address_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(address_table)
    story.append(Spacer(1, 30))

    # Line Items
    story.append(Paragraph("<b>ORDER DETAILS</b>", styles['Heading2']))
    story.append(Spacer(1, 10))

    items_data = [
        ['Description', 'Quantity (Hours)', 'Unit Price', 'Amount'],
        ['Senior Consultant', '40', '$150.00', '$6,000.00'],
        ['Software Developer', '80', '$125.00', '$10,000.00'],
        ['Project Manager', '20', '$140.00', '$2,800.00'],
    ]

    items_table = Table(items_data, colWidths=[2.5*inch, 1.5*inch, 1.25*inch, 1.25*inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    # Total
    total_data = [
        ['', '', 'TOTAL:', '$18,800.00'],
    ]
    total_table = Table(total_data, colWidths=[2.5*inch, 1.5*inch, 1.25*inch, 1.25*inch])
    total_table.setStyle(TableStyle([
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('ALIGN', (3, 0), (3, 0), 'CENTER'),
        ('FONTNAME', (2, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (2, 0), (-1, 0), 12),
        ('BACKGROUND', (2, 0), (-1, 0), colors.lightblue),
        ('BOX', (2, 0), (-1, 0), 1, colors.black),
    ]))
    story.append(total_table)
    story.append(Spacer(1, 30))

    # Terms
    story.append(Paragraph("<b>TERMS AND CONDITIONS</b>", styles['Heading2']))
    story.append(Paragraph("1. This Purchase Order is subject to the terms of Master Services Agreement MSA-2024-001.", styles['Normal']))
    story.append(Paragraph("2. Payment Terms: Net 30", styles['Normal']))
    story.append(Paragraph("3. Delivery: Services to be rendered at Acme Corporation premises or remotely as agreed.", styles['Normal']))
    story.append(Spacer(1, 30))

    # Authorization
    story.append(Paragraph("_________________________", styles['Normal']))
    story.append(Paragraph("Authorized Signature", styles['Normal']))
    story.append(Paragraph("Acme Corporation", styles['Normal']))

    doc.build(story)
    print(f"Created PO: {output_path}")


def create_invoice_pdf(output_path: Path):
    """Create an invoice PDF."""
    doc = SimpleDocTemplate(str(output_path), pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=72)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        alignment=TA_CENTER,
        spaceAfter=20,
        textColor=colors.darkblue
    )

    story = []

    # Company Header
    story.append(Paragraph("<b>TechPro Solutions Inc.</b>", title_style))
    story.append(Paragraph("456 Tech Park, Austin, TX 78701",
                          ParagraphStyle('Center', parent=styles['Normal'], alignment=TA_CENTER)))
    story.append(Paragraph("Phone: (512) 555-0100 | Email: billing@techpro.com",
                          ParagraphStyle('Center', parent=styles['Normal'], alignment=TA_CENTER)))
    story.append(Spacer(1, 30))

    # Invoice Title
    story.append(Paragraph("INVOICE", ParagraphStyle('InvTitle', parent=styles['Heading1'],
                                                      fontSize=18, alignment=TA_CENTER,
                                                      textColor=colors.grey)))
    story.append(Spacer(1, 20))

    # Invoice Details and Bill To
    details_data = [
        ['INVOICE DETAILS', '', 'BILL TO'],
        ['Invoice Number: INV-2024-0089', '', 'Acme Corporation'],
        ['Invoice Date: April 1, 2024', '', '123 Business Ave'],
        ['Due Date: May 1, 2024', '', 'San Francisco, CA 94102'],
        ['PO Reference: PO-2024-0042', '', 'Attn: Accounts Payable'],
        ['Contract: MSA-2024-001', '', ''],
    ]

    details_table = Table(details_data, colWidths=[2.5*inch, 0.5*inch, 2.5*inch])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 30))

    # Line Items
    items_data = [
        ['Description', 'Hours', 'Rate', 'Amount'],
        ['Senior Consultant - Strategic Planning', '40', '$150.00/hr', '$6,000.00'],
        ['Software Developer - Backend Development', '80', '$125.00/hr', '$10,000.00'],
        ['Project Manager - Project Oversight', '20', '$140.00/hr', '$2,800.00'],
    ]

    items_table = Table(items_data, colWidths=[3*inch, 1*inch, 1.25*inch, 1.25*inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 5))

    # Subtotal, Tax, Total
    totals_data = [
        ['', '', 'Subtotal:', '$18,800.00'],
        ['', '', 'Tax (0%):', '$0.00'],
        ['', '', 'TOTAL DUE:', '$18,800.00'],
    ]

    totals_table = Table(totals_data, colWidths=[3*inch, 1*inch, 1.25*inch, 1.25*inch])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('FONTNAME', (2, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (2, -1), (-1, -1), 12),
        ('BACKGROUND', (2, -1), (-1, -1), colors.lightblue),
        ('BOX', (2, -1), (-1, -1), 1, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 40))

    # Payment Information
    story.append(Paragraph("<b>PAYMENT INFORMATION</b>", styles['Heading2']))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Payment Terms: Net 30", styles['Normal']))
    story.append(Paragraph("Please remit payment to:", styles['Normal']))
    story.append(Spacer(1, 5))
    story.append(Paragraph("Bank: First National Bank", styles['Normal']))
    story.append(Paragraph("Account Name: TechPro Solutions Inc.", styles['Normal']))
    story.append(Paragraph("Account Number: XXXX-XXXX-1234", styles['Normal']))
    story.append(Paragraph("Routing Number: 021000021", styles['Normal']))
    story.append(Spacer(1, 20))

    # Footer
    story.append(Paragraph("<i>Thank you for your business!</i>",
                          ParagraphStyle('Footer', parent=styles['Normal'],
                                        alignment=TA_CENTER, textColor=colors.grey)))

    doc.build(story)
    print(f"Created invoice: {output_path}")


def main():
    """Generate all test PDF files."""
    # Create output directory
    output_dir = Path(__file__).parent.parent / "data" / "test_samples"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate PDFs
    create_contract_pdf(output_dir / "TechPro_Contract_MSA-2024-001.pdf")
    create_po_pdf(output_dir / "TechPro_PO-2024-0042.pdf")
    create_invoice_pdf(output_dir / "TechPro_Invoice_INV-2024-0089.pdf")

    print(f"\nAll test PDFs created in: {output_dir}")
    print("\nUpload order:")
    print("1. First: TechPro_Contract_MSA-2024-001.pdf (Ingest Contracts page)")
    print("2. Second: TechPro_PO-2024-0042.pdf (Process POs page)")
    print("3. Third: TechPro_Invoice_INV-2024-0089.pdf (Process Invoices page)")
    print("\nThis should result in a PASS for three-way matching as all documents are aligned.")


if __name__ == "__main__":
    main()
