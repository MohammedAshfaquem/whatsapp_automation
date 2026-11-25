from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.whatsapp.models import WhatsAppDelivery
from apps.whatsapp.delivery import dispatch


class Command(BaseCommand):
    help = 'Retry pending and definitively failed WhatsApp deliveries (maximum 3 attempts).'

    def handle(self, *args, **options):
        # A process may have exited after sending but before recording the result.
        WhatsAppDelivery.objects.filter(status='SENDING', updated_at__lt=timezone.now() - timedelta(minutes=5)).update(
            status='UNKNOWN', last_error='Interrupted send; inspect delivery before retrying.')
        count = 0
        for delivery in WhatsAppDelivery.objects.filter(status__in=['PENDING', 'FAILED'], attempts__lt=3).exclude(campaignrecipient__campaign__status__in=['PAUSED', 'SCHEDULED']).order_by('created_at')[:100]:
            if delivery.created_at < timezone.now() - timedelta(hours=23) and not delivery.payload.get('template'):
                delivery.status = 'BLOCKED'
                delivery.last_error = 'Reply is stale; use an approved template or wait for a new customer message.'
                delivery.save()
                continue
            count += int(dispatch(delivery.pk))
        self.stdout.write(f'Successfully dispatched {count} deliveries. UNKNOWN and BLOCKED records need staff review.')
