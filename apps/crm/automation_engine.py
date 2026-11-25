"""
Durable, tenant-scoped workflow automation engine for Neoriz WhatsApp Automation.
Executes configured action rules upon CRM and messaging events with transactional outbox,
idempotent atomic claiming, causation chain loop prevention, and audit logs.
"""
import hashlib
import json
import logging
import uuid
from datetime import timedelta
from typing import Dict, List, Optional

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.chatbot.models import Conversation, Customer
from apps.crm.assignment_service import assign_lead_round_robin
from apps.crm.models import (
    Activity,
    ActivityPriority,
    ActivityStatus,
    ActivityType,
    AutomationActionType,
    AutomationRule,
    AutomationRunLog,
    AutomationTrigger,
    BusinessEvent,
    ContactNote,
    Deal,
    DealStage,
    OnboardingChecklist,
    OnboardingTask,
)
from apps.crm.webhook_service import enqueue_outbound_webhooks, execute_webhook_delivery_attempt

logger = logging.getLogger(__name__)


def evaluate_rule_conditions(conditions: dict, context: dict) -> bool:
    """
    Evaluates whether an event context satisfies rule conditions.
    Supports case-insensitive string matching and exact value comparisons.
    """
    if not conditions:
        return True

    for key, expected_val in conditions.items():
        actual_val = context.get(key)
        if actual_val is None:
            return False
        # String case-insensitive match
        if isinstance(expected_val, str) and isinstance(actual_val, str):
            if expected_val.strip().lower() != actual_val.strip().lower():
                return False
        elif actual_val != expected_val:
            return False
    return True


def execute_automation_action(rule: AutomationRule, entity_id: int, context: dict, dry_run: bool = False) -> dict:
    """
    Executes a specific automation action against a given entity.
    Returns dictionary summary of the action outcome.
    """
    tenant = rule.tenant
    action = rule.action_type
    config = rule.action_config or {}

    if dry_run:
        return {
            'action': action,
            'dry_run': True,
            'simulated_effect': f"Would execute {action} for entity {entity_id} with config {config}",
        }

    outcome = {'action': action, 'success': True}

    if action == AutomationActionType.CREATE_TASK:
        task_title = config.get('task_title', f"Follow up on {rule.name}")
        due_days = int(config.get('due_days', 1))
        priority = config.get('priority', ActivityPriority.HIGH)
        due_date = timezone.now() + timedelta(days=due_days)

        deal = Deal.objects.filter(tenant=tenant, id=entity_id).first() if 'deal' in rule.trigger_type else None
        contact = None
        if deal:
            contact = deal.contact
        elif 'lead' in rule.trigger_type or 'conversation' in rule.trigger_type:
            contact = Customer.objects.filter(tenant=tenant, id=entity_id).first()

        assignee = deal.owner if deal else (contact.owner if contact else None)

        activity = Activity.objects.create(
            tenant=tenant,
            title=task_title,
            activity_type=ActivityType.FOLLOW_UP,
            priority=priority,
            status=ActivityStatus.PENDING,
            due_date=due_date,
            contact=contact,
            deal=deal,
            assigned_to=assignee,
            notes=f"Automated task created by rule '{rule.name}'"
        )
        outcome['created_activity_id'] = activity.id

    elif action == AutomationActionType.ASSIGN_STAFF:
        contact = Customer.objects.filter(tenant=tenant, id=entity_id).first()
        if contact:
            assigned = assign_lead_round_robin(tenant, contact=contact)
            outcome['assigned_user'] = assigned.username if assigned else None

    elif action == AutomationActionType.ADD_INTERNAL_NOTE:
        contact = Customer.objects.filter(tenant=tenant, id=entity_id).first()
        if not contact and 'deal' in rule.trigger_type:
            deal = Deal.objects.filter(tenant=tenant, id=entity_id).first()
            contact = deal.contact if deal else None

        if contact:
            note_text = config.get('note_text', f"Automated note triggered by rule '{rule.name}'")
            note = ContactNote.objects.create(
                tenant=tenant,
                contact=contact,
                author=None,
                body=note_text
            )
            outcome['created_note_id'] = note.id

    elif action == AutomationActionType.CREATE_ONBOARDING:
        deal = Deal.objects.filter(tenant=tenant, id=entity_id).first()
        if deal:
            checklist = OnboardingChecklist.objects.create(
                tenant=tenant,
                deal=deal,
                contact=deal.contact,
                title=f"Onboarding: {deal.title}",
                is_completed=False
            )
            default_tasks = [
                'Kickoff Call Scheduled',
                'WhatsApp Business Number Verified',
                'Template Catalog Uploaded',
                'Team Staff Seating Complete'
            ]
            for idx, tname in enumerate(default_tasks, 1):
                OnboardingTask.objects.create(
                    checklist=checklist,
                    title=tname,
                    order=idx
                )
            outcome['created_checklist_id'] = checklist.id

    elif action == AutomationActionType.UPDATE_STAGE:
        target_stage_id = config.get('stage_id')
        deal = Deal.objects.filter(tenant=tenant, id=entity_id).first()
        if deal and target_stage_id:
            stage = DealStage.objects.filter(pipeline__tenant=tenant, id=target_stage_id).first()
            if stage:
                deal.stage = stage
                deal.save(update_fields=['stage', 'updated_at'])
                outcome['updated_stage_id'] = stage.id

    elif action == AutomationActionType.ESCALATE:
        contact = Customer.objects.filter(tenant=tenant, id=entity_id).first()
        if contact:
            Activity.objects.create(
                tenant=tenant,
                title=f"ESCALATION: Lead review required for {contact.name or contact.phone_number}",
                activity_type=ActivityType.TASK,
                priority=ActivityPriority.HIGH,
                status=ActivityStatus.PENDING,
                due_date=timezone.now() + timedelta(hours=4),
                contact=contact,
                notes=f"Escalation triggered by rule '{rule.name}'"
            )
            outcome['escalated'] = True

    elif action == AutomationActionType.AUTO_REPLY:
        reply_text = str(config.get('reply_text') or '').strip()[:2000]
        contact = Customer.objects.filter(tenant=tenant, id=entity_id).first()
        if not contact:
            conv = Conversation.objects.filter(tenant=tenant, id=entity_id).select_related('customer').first()
            contact = conv.customer if conv else None
        if contact and reply_text:
            from apps.chatbot.models import ChannelChoice, ConversationStatus, Message, MessageDirection, ProcessingStatus, SenderType
            from apps.whatsapp.delivery import dispatch
            from apps.whatsapp.models import WhatsAppDelivery
            conv = Conversation.objects.filter(
                tenant=tenant, customer=contact, channel=ChannelChoice.WHATSAPP
            ).exclude(status=ConversationStatus.CLOSED).first()
            if conv:
                msg = Message.objects.create(
                    conversation=conv,
                    direction=MessageDirection.OUTBOUND,
                    sender_type=SenderType.BOT,
                    message_text=reply_text,
                    processing_status=ProcessingStatus.PROCESSED,
                    response_data={'automation_rule_id': rule.id},
                )
                d = WhatsAppDelivery.objects.create(
                    tenant=tenant,
                    dedup_key=f"auto:{rule.id}:{msg.pk}",
                    recipient_phone=contact.phone_number,
                    payload={'text': reply_text, 'conversation_id': conv.pk, 'message_id': msg.pk, 'sender_type': 'BOT'},
                )
                transaction.on_commit(lambda d_pk=d.pk: dispatch(d_pk))
                outcome['queued_delivery_id'] = d.pk

    return outcome


def record_business_event(
    tenant,
    event_type: str,
    entity_type: str,
    entity_id: int,
    payload: dict,
    dedup_key: Optional[str] = None,
    correlation_id: Optional[str] = None,
    causation_id: Optional[str] = None,
    causation_depth: int = 1
) -> BusinessEvent:
    """
    Persists a durable outbox event representing an authoritative business state transition.
    Enforces loop prevention via causation_depth <= 3 and idempotency via dedup_key.
    """
    if dedup_key:
        existing = BusinessEvent.objects.filter(dedup_key=dedup_key).first()
        if existing:
            return existing

    if causation_depth > 3:
        logger.warning(
            "Terminated cascading automation loop: causation_depth=%d exceeded limit 3 for tenant=%s, event=%s",
            causation_depth, tenant.slug, event_type
        )
        # Create marked as DEAD_LETTER to preserve audit trail without infinite cascade
        event_id = uuid.uuid4().hex
        return BusinessEvent.objects.create(
            tenant=tenant,
            event_id=event_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            dedup_key=dedup_key,
            correlation_id=correlation_id or event_id,
            causation_id=causation_id or '',
            causation_depth=causation_depth,
            status='DEAD_LETTER',
            last_error="Terminated: Maximum causation depth exceeded (loop prevention)."
        )

    event_id = uuid.uuid4().hex
    event = BusinessEvent.objects.create(
        tenant=tenant,
        event_id=event_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        dedup_key=dedup_key,
        correlation_id=correlation_id or event_id,
        causation_id=causation_id or '',
        causation_depth=causation_depth,
        status='PENDING'
    )
    return event


def process_business_event(event: BusinessEvent, dry_run: bool = False) -> List[dict]:
    """
    Processes a single BusinessEvent against tenant automation rules and outbound webhooks.
    Uses atomic run log claiming with unique constraints for idempotency.
    """
    tenant = event.tenant

    # 1. Tenant & Subscription sanity checks
    if not tenant.is_active:
        event.status = 'FAILED'
        event.last_error = 'Tenant workspace is inactive.'
        event.save(update_fields=['status', 'last_error'])
        return []

    if hasattr(tenant, 'subscription'):
        if tenant.subscription.status == 'SUSPENDED':
            event.status = 'FAILED'
            event.last_error = 'Tenant subscription is suspended.'
            event.save(update_fields=['status', 'last_error'])
            return []

    if event.status == 'PROCESSED' and not dry_run:
        return []

    rules = AutomationRule.objects.filter(
        tenant=tenant,
        trigger_type=event.event_type,
        is_active=True
    )

    results = []

    for rule in rules:
        if not evaluate_rule_conditions(rule.conditions, event.payload):
            continue

        if dry_run:
            simulated = execute_automation_action(rule, event.entity_id, event.payload, dry_run=True)
            results.append({'rule_id': rule.id, 'status': 'DRY_RUN', 'outcome': simulated})
            continue

        # Stable idempotency key: tenant:rule:version:event_id
        idempotency_key = hashlib.sha256(
            f"{tenant.id}:{rule.id}:{rule.version}:{event.event_id}".encode()
        ).hexdigest()

        run_log = None
        now = timezone.now()
        try:
            with transaction.atomic():
                run_log = AutomationRunLog.objects.create(
                    tenant=tenant,
                    rule=rule,
                    event=event,
                    trigger_event=event.event_type,
                    entity_id=event.entity_id,
                    status='CLAIMED',
                    details={'stage': 'claimed'},
                    idempotency_key=idempotency_key,
                    correlation_id=event.correlation_id,
                    causation_id=event.event_id,
                    execution_lease_expires_at=now + timedelta(minutes=5)
                )
        except IntegrityError:
            run_log = AutomationRunLog.objects.filter(idempotency_key=idempotency_key).first()
            if not run_log:
                continue

            # If already succeeded, idempotent skip
            if run_log.status == 'SUCCESS':
                logger.info("Rule %d already succeeded for event %s (idempotent skip)", rule.id, event.event_id)
                continue

            # If currently claimed with active lease, skip concurrent run
            if run_log.status == 'CLAIMED' and run_log.execution_lease_expires_at and run_log.execution_lease_expires_at > now:
                logger.info("Rule %d currently claimed with active lease for event %s (skip)", rule.id, event.event_id)
                continue

            # If max attempts reached, dead-letter it
            if run_log.attempt_count >= 3:
                if run_log.status != 'DEAD_LETTER':
                    run_log.status = 'DEAD_LETTER'
                    run_log.save(update_fields=['status'])
                logger.warning("Rule %d reached max attempts for event %s (dead-lettered)", rule.id, event.event_id)
                continue

            # Reclaim failed or expired run
            run_log.status = 'CLAIMED'
            run_log.attempt_count += 1
            run_log.execution_lease_expires_at = now + timedelta(minutes=5)
            run_log.save(update_fields=['status', 'attempt_count', 'execution_lease_expires_at'])

        # Execute action
        try:
            outcome = execute_automation_action(rule, event.entity_id, event.payload, dry_run=False)
            run_log.status = 'SUCCESS'
            run_log.details = outcome
            run_log.save(update_fields=['status', 'details'])

            AutomationRule.objects.filter(id=rule.id).update(
                execution_count=F('execution_count') + 1,
                updated_at=timezone.now()
            )
            results.append({'rule_id': rule.id, 'status': 'SUCCESS', 'outcome': outcome})

        except Exception as exc:
            logger.error("Automation rule %d execution failed: %s", rule.id, exc, exc_info=True)
            run_log.status = 'FAILED'
            run_log.details = {'error': str(exc)}
            run_log.save(update_fields=['status', 'details'])
            results.append({'rule_id': rule.id, 'status': 'FAILED', 'error': str(exc)})

    if not dry_run:
        # Enqueue outbound webhooks for this event
        deliveries = enqueue_outbound_webhooks(
            tenant=tenant,
            event_type=event.event_type,
            event_id=event.event_id,
            payload_data={
                'event_id': event.event_id,
                'event_type': event.event_type,
                'entity_type': event.entity_type,
                'entity_id': event.entity_id,
                'payload': event.payload,
                'timestamp': event.created_at.isoformat(),
                'tenant': tenant.slug,
            }
        )
        for d in deliveries:
            execute_webhook_delivery_attempt(d)

        event_update_filter = {'id': event.id}
        if event.claim_token:
            event_update_filter['claim_token'] = event.claim_token

        updated = BusinessEvent.objects.filter(**event_update_filter).update(
            status='PROCESSED',
            processed_at=timezone.now(),
            lease_expires_at=None,
            claim_token=''
        )
        if not updated:
            logger.warning("Event %d lease lost or expired before completion (claim_token mismatch)", event.id)

    return results


def reclaim_expired_business_event_leases() -> int:
    """
    Reclaims business events stuck in PROCESSING past their lease_expires_at.
    Returns them to PENDING if attempts < 5, or DEAD_LETTER if maximum attempts reached.
    """
    now = timezone.now()
    reclaimed = BusinessEvent.objects.filter(
        status='PROCESSING',
        lease_expires_at__lt=now,
        attempts__lt=5
    ).update(
        status='PENDING',
        lease_expires_at=None,
        claim_token='',
        last_error='Processing lease expired; returned to pending queue.'
    )
    dead_lettered = BusinessEvent.objects.filter(
        status='PROCESSING',
        lease_expires_at__lt=now,
        attempts__gte=5
    ).update(
        status='DEAD_LETTER',
        lease_expires_at=None,
        claim_token='',
        last_error='Processing lease expired and maximum attempts reached.'
    )
    return reclaimed + dead_lettered


def process_pending_business_events(tenant=None, batch_size: int = 25) -> int:
    """
    Worker function to claim and process pending outbox business events atomically with unique claim tokens.
    """
    now = timezone.now()
    claim_token = uuid.uuid4().hex
    qs = BusinessEvent.objects.filter(status='PENDING')
    if tenant:
        qs = qs.filter(tenant=tenant)

    with transaction.atomic():
        pending_ids = list(
            qs.select_for_update(skip_locked=True)
            .values_list('id', flat=True)[:batch_size]
        )
        if not pending_ids:
            return 0

        BusinessEvent.objects.filter(id__in=pending_ids).update(
            status='PROCESSING',
            lease_expires_at=now + timedelta(minutes=2),
            claim_token=claim_token,
            attempts=F('attempts') + 1
        )

    processed_count = 0
    for eid in pending_ids:
        try:
            event = BusinessEvent.objects.select_related('tenant').get(id=eid)
            process_business_event(event)
            processed_count += 1
        except Exception as exc:
            logger.error("Error processing business event %d: %s", eid, exc)
            BusinessEvent.objects.filter(id=eid).update(
                status='FAILED',
                last_error=str(exc)
            )

    return processed_count


def dispatch_automation_event(
    tenant,
    trigger_type: str,
    entity_id: int,
    context: dict,
    call_depth: int = 1
) -> List[dict]:
    """
    Synchronous entrypoint maintaining compatibility with existing code and tests.
    Atomically records a BusinessEvent and processes it immediately.
    """
    entity_type = 'deal' if 'deal' in trigger_type else ('contact' if 'lead' in trigger_type else 'general')
    dedup_key = f"{tenant.id}:{trigger_type}:{entity_id}:{uuid.uuid4().hex}"

    event = record_business_event(
        tenant=tenant,
        event_type=trigger_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=context,
        dedup_key=dedup_key,
        causation_depth=call_depth
    )

    if event.status == 'DEAD_LETTER':
        return []

    return process_business_event(event, dry_run=False)


def dry_run_rule(rule: AutomationRule, sample_context: dict) -> dict:
    """
    Executes dry run preview of an automation rule without writing database mutations.
    """
    matches = evaluate_rule_conditions(rule.conditions, sample_context)
    if not matches:
        return {
            'rule_id': rule.id,
            'name': rule.name,
            'matches_conditions': False,
            'message': 'Sample context does not satisfy rule conditions.',
        }

    simulated = execute_automation_action(rule, entity_id=0, context=sample_context, dry_run=True)
    return {
        'rule_id': rule.id,
        'name': rule.name,
        'matches_conditions': True,
        'simulated_outcome': simulated
    }
