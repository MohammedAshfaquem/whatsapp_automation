"""Business-specific conversation behavior selected by deployment configuration."""
from django.conf import settings


def is_it_business():
    return getattr(settings, 'BUSINESS_INDUSTRY', 'ac').lower() == 'it'
