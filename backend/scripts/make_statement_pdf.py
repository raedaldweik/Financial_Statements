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
    ("01/09/2026", "OPENING BALANCE", "", "", "21,340.55"),
    ("02/09/2026", "CARD PURCHASE — LULU HYPERMARKET, DUBAI", "214.30", "", "21,126.25"),
    ("03/09/2026", "CARD PURCHASE — ADNOC FUEL STATION", "180.00", "", "20,946.25"),
    ("05/09/2026", "SALARY CREDIT — FUTURE VISION MARKETING LLC", "", "14,200.00", "35,146.25"),
    ("06/09/2026", "CARD PURCHASE — NOON.COM ORDER 5521-8830", "329.50", "", "34,816.75"),
    ("08/09/2026",
     "ONLINE TRANSFER — MUBARAK SALEM / ACC 5660609 / AE600340005660609 / "
     "REF: TRX-2026-0918-4821 PURCHASE OF ELECTRONIC DEVICES",
     "12,500.00", "", "22,316.75"),
    ("09/09/2026", "CARD PURCHASE — CARREFOUR MALL OF THE EMIRATES", "412.80", "", "21,903.95"),
    ("11/09/2026", "UTILITY PAYMENT — DEWA", "518.60", "", "21,385.35"),
    ("12/09/2026", "ATM CASH WITHDRAWAL — DEIRA BRANCH", "800.00", "", "20,585.35"),
    ("14/09/2026", "CARD PURCHASE — TALABAT ORDER", "96.50", "", "20,488.85"),
    ("16/09/2026", "TELECOM PAYMENT — DU MONTHLY PLAN", "189.00", "", "20,299.85"),
    ("17/09/2026", "CARD PURCHASE — AMAZON.AE 771-20455", "145.75", "", "20,154.10"),
    ("18/09/2026", "CLOSING BALANCE", "", "", "20,154.10"),
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
        Paragraph("EXAMPLE BANK", h1),
        Paragraph("People. Progress. Together. — FOR DEMO / TRAINING PURPOSES ONLY. Not a real bank document.", sub),
        Spacer(1, 6 * mm),
    ]

    meta = Table([
        ["Account holder", "AHMED HASSAN", "Statement period", "01/09/2026 – 18/09/2026"],
        ["Account number", "7712045", "Currency", "AED"],
        ["IBAN", "AE310340007712045", "Branch", "Deira, Dubai"],
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
        Paragraph("End of statement. For queries contact Example Bank. Example Bank is a fictional institution — demo/training use only.", sub),
    ]
    doc.build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
