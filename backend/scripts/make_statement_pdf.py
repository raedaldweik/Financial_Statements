"""One-time generator for the bundled demo bank statement PDF.

Run from the backend/ directory:  python scripts/make_statement_pdf.py
Requires:  pip install reportlab
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

OUT = Path(__file__).resolve().parent.parent / "demo_data" / "bank_statement.pdf"

NAVY = colors.HexColor("#0b2545")
GOLD = colors.HexColor("#c8a44a")
GREY = colors.HexColor("#5a6472")

TXNS = [
    ("01/08/2026", "OPENING BALANCE", "", "", "24,310.55"),
    ("02/08/2026", "CARD PURCHASE — SPINNEYS AL WASL, DUBAI", "412.35", "", "23,898.20"),
    ("03/08/2026", "CARD PURCHASE — CAREEM RIDES", "58.00", "", "23,840.20"),
    ("05/08/2026", "SALARY CREDIT — MERIDIAN CONSULTING DMCC", "", "16,400.00", "40,240.20"),
    ("07/08/2026", "CARD PURCHASE — NOON.COM ORDER 8842-1190", "289.90", "", "39,950.30"),
    ("09/08/2026", "ATM CASH WITHDRAWAL — JBR BRANCH", "1,000.00", "", "38,950.30"),
    ("12/08/2026", "UTILITY PAYMENT — DEWA", "643.20", "", "38,307.10"),
    ("14/08/2026",
     "ONLINE TRANSFER — BRIGHT STAR GENERAL TRADING FZE / GULF TRUST BANK / "
     "AE47 0331 0000 0234 5678 901 / REF: ORDER LT-2214 LUXETIME WATCH",
     "18,500.00", "", "19,807.10"),
    ("15/08/2026", "CARD PURCHASE — LIFE PHARMACY MARINA", "86.50", "", "19,720.60"),
    ("17/08/2026", "CARD PURCHASE — STARBUCKS DIFC", "34.00", "", "19,686.60"),
    ("19/08/2026",
     "ONLINE TRANSFER — BRIGHT STAR GENERAL TRADING FZE / GULF TRUST BANK / "
     "AE47 0331 0000 0234 5678 901 / REF: CUSTOMS LT-2214",
     "2,750.00", "", "16,936.60"),
    ("22/08/2026", "CARD PURCHASE — CARREFOUR MALL OF THE EMIRATES", "523.75", "", "16,412.85"),
    ("25/08/2026", "TELECOM PAYMENT — DU MONTHLY PLAN", "199.00", "", "16,213.85"),
    ("28/08/2026", "CARD PURCHASE — AMAZON.AE 402-99812", "164.99", "", "16,048.86"),
    ("31/08/2026", "CLOSING BALANCE", "", "", "16,048.86"),
]


def build() -> None:
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("bank", parent=styles["Title"], textColor=NAVY,
                        fontSize=20, alignment=0, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=styles["Normal"], textColor=GREY, fontSize=9)
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=8, leading=10)

    doc = SimpleDocTemplate(str(OUT), pagesize=A4,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    story = [
        Paragraph("AL NOOR NATIONAL BANK", h1),
        Paragraph("This is a fictional bank statement generated for a product demonstration.", sub),
        Spacer(1, 6 * mm),
    ]

    meta = Table([
        ["Account holder", "SARA AL MANSOURI", "Statement period", "01/08/2026 – 31/08/2026"],
        ["Account number", "012-345678-01", "Currency", "AED"],
        ["IBAN", "AE21 0260 0000 1234 5678 901", "Branch", "Jumeirah, Dubai"],
    ], colWidths=[30 * mm, 62 * mm, 32 * mm, 54 * mm])
    meta.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (0, -1), GREY),
        ("TEXTCOLOR", (2, 0), (2, -1), GREY),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("LINEBELOW", (0, -1), (-1, -1), 0.75, GOLD),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [meta, Spacer(1, 6 * mm)]

    rows = [["Date", "Description", "Debit (AED)", "Credit (AED)", "Balance (AED)"]]
    for d, desc, debit, credit, bal in TXNS:
        rows.append([d, Paragraph(desc, cell), debit, credit, bal])

    table = Table(rows, colWidths=[20 * mm, 92 * mm, 22 * mm, 22 * mm, 22 * mm],
                  repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f9")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d7dde5")),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]
    for i, (_, desc, *_rest) in enumerate(TXNS, start=1):
        if "OPENING" in desc or "CLOSING" in desc:
            style.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
    table.setStyle(TableStyle(style))
    story.append(table)
    story += [
        Spacer(1, 6 * mm),
        Paragraph("End of statement. For queries contact Al Noor National Bank (fictional entity — demo only).", sub),
    ]
    doc.build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
