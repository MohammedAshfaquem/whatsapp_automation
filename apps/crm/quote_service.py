"""
Quote and proposal management service for Neoriz WhatsApp Automation.
Handles versioned quotes, item calculations, status progression, and PDF export.
"""
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from apps.crm.models import Deal, Quote, QuoteItem, QuoteStatus
from apps.crm.pdf_generator import generate_quote_pdf_document


def create_or_version_quote(deal, title, items_data, user, discount=Decimal('0'), tax_percent=Decimal('18.0'), terms=''):
    """
    Creates a new quote for a deal or creates the next incremented version if one exists.
    """
    tenant = deal.tenant
    existing_quotes = Quote.objects.filter(deal=deal).order_by('-version')
    latest_quote = existing_quotes.first()

    if latest_quote:
        version = latest_quote.version + 1
        quote_number = latest_quote.quote_number
    else:
        # Generate new quote number QT-YYYY-XXXX
        year = timezone.now().year
        count = Quote.objects.filter(tenant=tenant).count() + 1
        quote_number = f"QT-{year}-{count:04d}"
        version = 1

    valid_until = timezone.now().date() + timedelta(days=30)

    quote = Quote.objects.create(
        tenant=tenant,
        deal=deal,
        quote_number=quote_number,
        version=version,
        title=title,
        discount_amount=Decimal(str(discount)),
        tax_percent=Decimal(str(tax_percent)),
        terms_and_conditions=terms or "Standard terms apply. Quotation valid for 30 days.",
        valid_until=valid_until,
        status=QuoteStatus.DRAFT,
        created_by=user
    )

    for item_data in items_data:
        desc = item_data.get('description', 'Service Item')
        qty = Decimal(str(item_data.get('quantity', 1)))
        price = Decimal(str(item_data.get('unit_price', 0)))
        disc_pct = Decimal(str(item_data.get('discount_percent', 0)))

        QuoteItem.objects.create(
            quote=quote,
            description=desc,
            quantity=qty,
            unit_price=price,
            discount_percent=disc_pct
        )

    quote.recalculate_totals()
    return quote


def update_quote_status(quote, new_status, user=None):
    """
    Transitions quote status (e.g. DRAFT -> SENT -> APPROVED / REJECTED).
    Updates deal amount and triggers stage update if approved.
    """
    quote.status = new_status
    now = timezone.now()
    if new_status == QuoteStatus.SENT and not quote.sent_at:
        quote.sent_at = now
    elif new_status == QuoteStatus.APPROVED and not quote.approved_at:
        quote.approved_at = now
        # Sync deal amount with approved quote
        if quote.deal:
            quote.deal.amount = quote.total_amount
            quote.deal.save(update_fields=['amount', 'updated_at'])
    elif new_status == QuoteStatus.REJECTED and not quote.rejected_at:
        quote.rejected_at = now

    quote.save(update_fields=['status', 'sent_at', 'approved_at', 'rejected_at', 'updated_at'])
    return quote


def get_quote_pdf_bytes(quote):
    """
    Generates and returns the PDF binary representation of the quote.
    """
    return generate_quote_pdf_document(quote)
