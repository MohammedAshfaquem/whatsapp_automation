"""
Unified Operational Background Worker for Neoriz WhatsApp Automation.
Executes periodic queue processing and lease reclamation across:
1. Expired processing lease reclamation (Business Events & Webhook Deliveries)
2. Outbox business events processing
3. Outbound webhook retries and delivery dispatch
4. WhatsApp messaging retries
"""
import logging
import os
import signal
from threading import Event

import django
from django.core.management import call_command
from django.db import close_old_connections


def run_worker_cycle(logger):
    """
    Executes a single operational worker cycle across all asynchronous queues.
    Each queue is isolated in its own try/except block so errors in one queue
    never block or delay execution in others.
    """
    # 1. Expired lease reclamation
    try:
        from apps.crm.automation_engine import reclaim_expired_business_event_leases
        reclaimed_events = reclaim_expired_business_event_leases()
        if reclaimed_events:
            logger.info("Reclaimed %d expired business event leases", reclaimed_events)
    except Exception:
        logger.exception("Error reclaiming business event leases")

    try:
        from apps.crm.webhook_service import reclaim_expired_webhook_leases
        reclaimed_webhooks = reclaim_expired_webhook_leases()
        if reclaimed_webhooks:
            logger.info("Reclaimed %d expired webhook delivery leases", reclaimed_webhooks)
    except Exception:
        logger.exception("Error reclaiming webhook leases")

    # 2. Process pending outbox business events
    try:
        from apps.crm.automation_engine import process_pending_business_events
        processed_events = process_pending_business_events(batch_size=50)
        if processed_events:
            logger.info("Processed %d pending business events", processed_events)
    except Exception:
        logger.exception("Error processing pending business events")

    # 3. Process pending outbound webhook deliveries
    try:
        from apps.crm.webhook_service import process_pending_webhook_deliveries
        processed_webhooks = process_pending_webhook_deliveries(batch_size=50)
        if processed_webhooks:
            logger.info("Processed %d pending webhook deliveries", processed_webhooks)
    except Exception:
        logger.exception("Error processing pending webhook deliveries")

    # Consent-aware campaign recipients are materialized into the existing durable queue.
    try:
        from apps.crm.broadcasts import run_campaigns
        run_campaigns(batch_size=50)
    except Exception:
        logger.exception('Campaign queue processing failed')

    try:
        from apps.tenants.email_service import process_emails
        process_emails(limit=20)
    except Exception:
        logger.exception('Transactional email queue failed')

    try:
        from apps.tenants.support_service import process_support_escalations
        escalated = process_support_escalations(batch_size=25)
        if escalated:
            logger.info("Processed %d support SLA escalation(s)", escalated)
    except Exception:
        logger.exception('Platform support escalation check failed')

    try:
        from apps.crm.business_hours import process_no_response_followups
        followups = process_no_response_followups(batch_size=50)
        if followups:
            logger.info("Processed %d no-response follow-up task(s)", followups)
    except Exception:
        logger.exception('No-response follow-up scan failed')

    # 4. WhatsApp durable messaging retries
    try:
        call_command('retry_whatsapp')
    except Exception:
        logger.exception("Delivery retry failed for WhatsApp")


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    stopped = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: stopped.set())
        except ValueError:
            # Running on threads or non-main thread in certain environments
            pass
    logger = logging.getLogger(__name__)
    logger.info("Operational retry worker started")

    while not stopped.is_set():
        try:
            close_old_connections()
            run_worker_cycle(logger)
        except Exception:
            logger.exception("Unexpected error in worker cycle; retrying")
        finally:
            close_old_connections()
        stopped.wait(30)


if __name__ == '__main__':
    main()
