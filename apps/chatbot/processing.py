"""Serialize a customer's turns without holding a database transaction during AI."""
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from django.db.models import Q
from django.utils import timezone

from .models import Customer


class ConversationBusyError(Exception):
    """The caller should retry after the current turn has completed."""


@contextmanager
def customer_turn(customer):
    token = uuid4().hex
    now = timezone.now()
    claimed = Customer.objects.filter(pk=customer.pk).filter(
        Q(processing_token='') | Q(processing_until__lte=now) | Q(processing_until__isnull=True)
    ).update(processing_token=token, processing_until=now + timedelta(minutes=3))
    if not claimed:
        raise ConversationBusyError('A message for this customer is already being processed.')
    try:
        yield token
    finally:
        Customer.objects.filter(pk=customer.pk, processing_token=token).update(
            processing_token='', processing_until=None)
