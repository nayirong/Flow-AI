"""
Flow AI Invoice Generator
=========================
Generates professional PDF invoices for Flow AI clients.

Usage (CLI):
    python3 finance/invoice_generator.py \
        --client-name "HeyAircon" \
        --client-contact "HeyAircon Team" \
        --client-address "Singapore" \
        --invoice-number "INV-HA-20260401" \
        --invoice-date "2026-04-18" \
        --due-date "2026-05-02" \
        --services '[{"description": "Phase 1 Project Kickoff", "qty": 1, "unit_price": 350}]' \
        --currency SGD \
        --payment-terms "Net 14 - Bank transfer" \
        --output-dir "clients/hey-aircon/invoices"

Usage (module):
    from finance.invoice_generator import generate_invoice
    path = generate_invoice(client_name="HeyAircon", ...)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    from fpdf import FPDF, XPos, YPos
except ImportError:
    print("fpdf2 is required. Install it with: pip install fpdf2", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ISSUER_NAME = "Flow AI"
ISSUER_ADDRESS = "Blk 450A Sengkang Westway #07-329, Singapore 791450"
ISSUER_EMAIL = "ryan.flowai@gmail.com"
ISSUER_PHONE = "+65 8282 9071"
ISSUER_BANK = "DBS Savings 030-64719-0 | SWIFT: DBSSSGSG | DBS Bank Ltd"
GST_RATE = 0.09  # 9%

# Colour palette (R, G, B)
COLOR_BLACK = (0, 0, 0)
COLOR_DARK = (30, 30, 30)
COLOR_ACCENT = (45, 90, 200)   # Flow AI blue
COLOR_LIGHT_GRAY = (245, 245, 245)
COLOR_MID_GRAY = (180, 180, 180)
COLOR_WHITE = (255, 255, 255)

# Column widths for line-items table (mm)
COL_DESC = 90
COL_QTY = 20
COL_UNIT = 35
COL_TOTAL = 35
TABLE_WIDTH = COL_DESC + COL_QTY + COL_UNIT + COL_TOTAL  # 180 mm


def _sanitize(text: str) -> str:
    """Replace characters outside latin-1 range with safe ASCII equivalents."""
    replacements = {
        "\u2014": "--",   # em dash
        "\u2013": "-",    # en dash
        "\u2018": "'",    # left single quote
        "\u2019": "'",    # right single quote
        "\u201c": '"',    # left double quote
        "\u201d": '"',    # right double quote
        "\u2022": "-",    # bullet
        "\u00b7": ".",    # middle dot (used in footer)
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Final safety net: encode to latin-1, replacing anything unmappable
    return text.encode("latin-1", errors="replace").decode("latin-1")


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------

class InvoicePDF(FPDF):
    """Custom FPDF subclass for Flow AI invoices."""

    def __init__(self, currency: str = "SGD"):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.currency = currency
        self.set_margins(left=15, top=15, right=15)
        self.set_auto_page_break(auto=True, margin=20)

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------

    def _money(self, amount: float) -> str:
        return f"{self.currency} {amount:,.2f}"

    def _sf(self, style: str = "", size: int = 10) -> None:
        self.set_font("Helvetica", style=style, size=size)

    def _tc(self, rgb: tuple[int, int, int]) -> None:
        self.set_text_color(*rgb)

    def _draw_line(self, y_offset: float = 0) -> None:
        y = self.get_y() + y_offset
        self.set_draw_color(*COLOR_MID_GRAY)
        self.line(15, y, 195, y)

    # Shorthand position constants
    _R = XPos.RIGHT
    _L = XPos.LMARGIN
    _N = YPos.NEXT
    _T = YPos.TOP

    # ------------------------------------------------------------------
    # Header block
    # ------------------------------------------------------------------

    def draw_header(self) -> None:
        self._sf("B", 26)
        self._tc(COLOR_ACCENT)
        self.cell(0, 10, ISSUER_NAME, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self._sf("", 12)
        self._tc(COLOR_DARK)
        self.cell(0, 6, "Invoice", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

        self._sf("", 8)
        self._tc((100, 100, 100))
        self.cell(0, 4, ISSUER_ADDRESS, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 4, ISSUER_EMAIL + "  |  " + ISSUER_PHONE, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 4, ISSUER_BANK, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(4)
        self._draw_line()
        self.ln(4)

    # ------------------------------------------------------------------
    # Client + invoice meta block (two-column layout)
    # ------------------------------------------------------------------

    def draw_meta(
        self,
        client_name: str,
        client_contact: str,
        client_address: str,
        invoice_number: str,
        invoice_date: str,
    ) -> None:
        # Section headers
        self._sf("B", 9)
        self._tc(COLOR_ACCENT)
        self.cell(95, 5, "BILL TO", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(0, 5, "INVOICE DETAILS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Client name | Invoice number
        self._sf("B", 10)
        self._tc(COLOR_DARK)
        self.set_x(15)
        self.cell(95, 5, _sanitize(client_name), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self._sf("", 10)
        self.cell(40, 5, "Invoice Number:", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self._sf("B", 10)
        self.cell(0, 5, _sanitize(invoice_number), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Client contact | Invoice date
        self._sf("", 9)
        self._tc((80, 80, 80))
        self.set_x(15)
        self.cell(95, 4, _sanitize(client_contact), new_x=XPos.RIGHT, new_y=YPos.TOP)
        self._sf("", 10)
        self._tc(COLOR_DARK)
        self.cell(40, 4, "Invoice Date:", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self._sf("B", 10)
        self.cell(0, 4, _sanitize(invoice_date), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Client address lines
        addr_lines = client_address.split("\n")
        self._sf("", 9)
        self._tc((80, 80, 80))
        self.set_x(15)
        self.cell(0, 4, _sanitize(addr_lines[0]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Remaining address lines (if any)
        for line in addr_lines[1:]:
            self._sf("", 9)
            self._tc((80, 80, 80))
            self.set_x(15)
            self.cell(95, 4, _sanitize(line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(6)
        self._draw_line()
        self.ln(4)

    # ------------------------------------------------------------------
    # Line-items table
    # ------------------------------------------------------------------

    def draw_table_header(self) -> None:
        self.set_fill_color(*COLOR_ACCENT)
        self._sf("B", 9)
        self._tc(COLOR_WHITE)
        self.cell(COL_DESC, 7, "Description", border=0, fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(COL_QTY, 7, "Qty", border=0, align="C", fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(COL_UNIT, 7, "Unit Price", border=0, align="R", fill=True, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(COL_TOTAL, 7, "Total", border=0, align="R", fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def draw_table_rows(self, services: list[dict[str, Any]]) -> float:
        """Draw service rows, return subtotal."""
        subtotal = 0.0
        for i, svc in enumerate(services):
            description = _sanitize(str(svc.get("description", "")))
            qty = float(svc.get("qty", 1))
            unit_price = float(svc.get("unit_price", 0))
            line_total = qty * unit_price
            subtotal += line_total

            if i % 2 == 0:
                self.set_fill_color(*COLOR_LIGHT_GRAY)
                fill = True
            else:
                self.set_fill_color(*COLOR_WHITE)
                fill = False

            self._sf("", 9)
            self._tc(COLOR_DARK)
            row_h = 7

            self.cell(COL_DESC, row_h, description[:55], border=0, fill=fill, new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.cell(COL_QTY, row_h, f"{qty:g}", border=0, align="C", fill=fill, new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.cell(COL_UNIT, row_h, self._money(unit_price), border=0, align="R", fill=fill, new_x=XPos.RIGHT, new_y=YPos.TOP)
            self.cell(COL_TOTAL, row_h, self._money(line_total), border=0, align="R", fill=fill, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        return subtotal

    def draw_totals(self, subtotal: float) -> None:
        self.ln(2)
        self._draw_line()
        self.ln(4)

        # Right-align two cells that together span the right 120mm (fits within 195mm page width)
        # label starts at x=75, width=90; value starts at x=165, width=30; right margin at 195
        self._sf("B", 9)
        self._tc(COLOR_ACCENT)
        self.set_x(75)
        self.cell(90, 6, "Total Due (GST not applicable):", align="R", new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(30, 6, self._money(subtotal), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(6)

    # ------------------------------------------------------------------
    # Payment terms + notes
    # ------------------------------------------------------------------

    def draw_payment_terms(self, terms: str) -> None:
        self._sf("B", 9)
        self._tc(COLOR_ACCENT)
        self.cell(0, 5, "PAYMENT TERMS", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._sf("", 9)
        self._tc(COLOR_DARK)
        self.multi_cell(0, 5, _sanitize(terms))
        self.ln(4)

    def draw_notes(self, notes: str) -> None:
        if not notes:
            return
        self._sf("B", 9)
        self._tc(COLOR_ACCENT)
        self.cell(0, 5, "NOTES", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._sf("", 9)
        self._tc((80, 80, 80))
        self.multi_cell(0, 5, _sanitize(notes))
        self.ln(4)

    # ------------------------------------------------------------------
    # Footer (called automatically by FPDF on each page)
    # ------------------------------------------------------------------

    def footer(self) -> None:
        self.set_y(-12)
        self._draw_line(-2)
        self._sf("", 7)
        self._tc(COLOR_MID_GRAY)
        self.cell(0, 5, f"{ISSUER_NAME} - Confidential", align="C")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_invoice(
    client_name: str,
    client_contact: str,
    client_address: str,
    invoice_number: str,
    invoice_date: str,
    services: list[dict[str, Any]],
    currency: str = "SGD",
    payment_terms: str = "Net 14 - Bank transfer",
    notes: str = "",
    output_dir: str = "./invoices",
) -> str:
    """
    Generate a PDF invoice and save it to output_dir.

    Returns the absolute path to the created PDF file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", client_name).strip("_").lower()
    filename = f"{invoice_number}_{slug}.pdf"
    filepath = output_path / filename

    pdf = InvoicePDF(currency=currency)
    pdf.add_page()

    pdf.draw_header()
    pdf.draw_meta(
        client_name=client_name,
        client_contact=client_contact,
        client_address=client_address,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
    )
    pdf.draw_table_header()
    subtotal = pdf.draw_table_rows(services)
    pdf.draw_totals(subtotal)
    pdf.draw_payment_terms(payment_terms)
    pdf.draw_notes(notes)

    pdf.output(str(filepath))
    return str(filepath.resolve())


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a PDF invoice for a Flow AI client.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--client-name", required=True, help="Client company name")
    parser.add_argument("--client-contact", required=True, help="Client contact name or team")
    parser.add_argument("--client-address", required=True, help="Client billing address")
    parser.add_argument("--invoice-number", required=True, help="Invoice number, e.g. INV-HA-20260401")
    parser.add_argument("--invoice-date", required=True, help="Invoice date (YYYY-MM-DD or display string)")
    parser.add_argument(
        "--services",
        required=True,
        help='JSON array: [{"description": str, "qty": float, "unit_price": float}]',
    )
    parser.add_argument("--currency", default="SGD", help="Currency code (default: SGD)")
    parser.add_argument("--payment-terms", default="Net 14 - Bank transfer", help="Payment terms text")
    parser.add_argument("--notes", default="", help="Optional notes to include on invoice")
    parser.add_argument("--output-dir", default="./invoices", help="Directory to save the PDF (default: ./invoices)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    try:
        services = json.loads(args.services)
    except json.JSONDecodeError as exc:
        print(f"Error: --services must be valid JSON. {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(services, list) or not services:
        print("Error: --services must be a non-empty JSON array.", file=sys.stderr)
        sys.exit(1)

    filepath = generate_invoice(
        client_name=args.client_name,
        client_contact=args.client_contact,
        client_address=args.client_address,
        invoice_number=args.invoice_number,
        invoice_date=args.invoice_date,
        services=services,
        currency=args.currency,
        payment_terms=args.payment_terms,
        notes=args.notes,
        output_dir=args.output_dir,
    )

    print(f"Invoice created: {filepath}")


if __name__ == "__main__":
    main()
