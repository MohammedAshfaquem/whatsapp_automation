"""
Zero-dependency, standards-compliant PDF 1.4 document generator for Neoriz WhatsApp Automation.
Generates clean, professional quotation and proposal PDFs without external binary dependencies.
"""
from decimal import Decimal


def generate_simple_pdf(title: str, lines: list) -> bytes:
    """
    Generates a valid PDF 1.4 document from structured lines of text.
    Each item in lines can be a string or a tuple: (text, font_size, is_bold, is_highlighted)
    """
    content_stream = []
    content_stream.append("BT")
    content_stream.append("/F1 10 Tf")
    content_stream.append("50 780 Td")
    content_stream.append("14 TL")

    # Header title
    content_stream.append(f"/F2 16 Tf ({escape_pdf_text(title)}) Tj")
    content_stream.append("T*")
    content_stream.append("/F1 10 Tf")
    content_stream.append("T*")

    for line in lines:
        if isinstance(line, str):
            content_stream.append(f"({escape_pdf_text(line)}) Tj T*")
        elif isinstance(line, (tuple, list)):
            text = str(line[0])
            size = line[1] if len(line) > 1 else 10
            is_bold = line[2] if len(line) > 2 else False
            font = "/F2" if is_bold else "/F1"
            content_stream.append(f"{font} {size} Tf ({escape_pdf_text(text)}) Tj")
            content_stream.append("T*")
            content_stream.append(f"/F1 10 Tf")

    content_stream.append("ET")
    stream_data = "\n".join(content_stream).encode('latin-1', errors='replace')
    stream_len = len(stream_data)

    objects = []
    # 1: Catalog
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    # 2: Pages
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    # 3: Page
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 4 0 R /Resources << /Font << "
        b"/F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> "
        b"/F2 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> "
        b">> >> >>"
    )
    # 4: Contents
    objects.append(
        f"<< /Length {stream_len} >>\nstream\n".encode('ascii') +
        stream_data +
        b"\nendstream"
    )

    # Build PDF binary
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode('ascii'))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode('ascii'))
    for off in offsets:
        pdf.extend(f"{off:010d} 00000 n \n".encode('ascii'))

    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode('ascii')
    )
    return bytes(pdf)


def escape_pdf_text(text: str) -> str:
    """Escapes special characters in PDF string literals."""
    if not text:
        return ""
    # Map currency symbol ₹ to Rs. for standard ASCII PDF compatibility
    text = text.replace('₹', 'INR ')
    return (
        text.replace('\\', '\\\\')
            .replace('(', '\\(')
            .replace(')', '\\)')
    )


def generate_quote_pdf_document(quote) -> bytes:
    """
    Renders a complete, professional quotation document for a Deal Quote.
    """
    lines = [
        ("==========================================================================", 10, False),
        (f"QUOTATION: {quote.quote_number} (Version {quote.version})", 14, True),
        (f"Status: {quote.get_status_display()} | Date: {quote.created_at:%Y-%m-%d}", 10, False),
        ("==========================================================================", 10, False),
        ("", 10, False),
        ("ISSUED TO:", 11, True),
        (f"Client: {quote.deal.contact.name or 'Valued Customer'}", 10, False),
        (f"Phone: {quote.deal.contact.phone_number}", 10, False),
    ]

    if quote.deal.contact.email:
        lines.append((f"Email: {quote.deal.contact.email}", 10, False))
    if quote.deal.company:
        lines.append((f"Company: {quote.deal.company.name}", 10, False))

    lines.extend([
        ("", 10, False),
        ("DEAL & PROPOSAL DETAILS:", 11, True),
        (f"Deal Title: {quote.deal.title}", 10, False),
        (f"Quotation Title: {quote.title}", 10, False),
        (f"Valid Until: {quote.valid_until or 'Within 30 Days'}", 10, False),
        ("", 10, False),
        ("LINE ITEMS & SPECIFICATIONS:", 11, True),
        ("--------------------------------------------------------------------------", 10, False),
        (f"{'Item Description':<40} {'Qty':<6} {'Unit Price':<12} {'Total':<10}", 9, True),
        ("--------------------------------------------------------------------------", 10, False),
    ])

    for item in quote.items.all():
        desc = (item.description[:38] + '..') if len(item.description) > 38 else item.description
        qty_str = f"{item.quantity:.0f}" if item.quantity == int(item.quantity) else f"{item.quantity:.2f}"
        price_str = f"{item.unit_price:.2f}"
        tot_str = f"{item.total_price:.2f}"
        lines.append((f"{desc:<40} {qty_str:<6} {price_str:<12} {tot_str:<10}", 9, False))

    lines.extend([
        ("--------------------------------------------------------------------------", 10, False),
        ("", 10, False),
        (f"Subtotal: {quote.currency} {quote.subtotal:.2f}", 10, False),
    ])

    if quote.discount_amount > 0:
        lines.append((f"Discount: -{quote.currency} {quote.discount_amount:.2f}", 10, False))

    lines.extend([
        (f"Tax ({quote.tax_percent}%): {quote.currency} {quote.tax_amount:.2f}", 10, False),
        ("--------------------------------------------------------------------------", 10, False),
        (f"TOTAL AMOUNT: {quote.currency} {quote.total_amount:.2f}", 12, True),
        ("--------------------------------------------------------------------------", 10, False),
        ("", 10, False),
    ])

    if quote.terms_and_conditions:
        lines.extend([
            ("TERMS & CONDITIONS:", 10, True),
            (quote.terms_and_conditions, 9, False),
            ("", 10, False),
        ])

    lines.extend([
        ("Generated by Neoriz WhatsApp Automation SaaS", 8, False),
        ("Neoriz Solutions — WhatsApp-first CRM & Sales Automation", 8, False),
    ])

    return generate_simple_pdf(f"QUOTATION — {quote.quote_number}", lines)
