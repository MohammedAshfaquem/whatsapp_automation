"""
Assignment and Sales Work Queue services for Neoriz WhatsApp Automation.
Provides round-robin, least workload assignment, and prioritized work queue aggregations.
"""
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from apps.tenants.models import TenantMembership, TenantRole
from apps.crm.models import Deal, Activity, ActivityStatus, DealStage
from apps.chatbot.models import Conversation, ConversationStatus, Customer

User = get_user_model()


def get_sales_work_queue(tenant, user=None):
    """
    Returns prioritized sales work queue items for a tenant:
    - Unanswered customer enquiries
    - Today's scheduled follow-ups
    - Overdue tasks
    - Stale deals (no activity for 7+ days)
    - Deals without next activity
    """
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    stale_cutoff = now - timedelta(days=7)

    # 1. Unanswered enquiries (Bot active or unassigned in need of staff pickup, or in handover)
    unanswered_convs_qs = Conversation.objects.filter(
        tenant=tenant
    ).exclude(status=ConversationStatus.CLOSED).filter(
        Q(assigned_staff__isnull=True) | Q(unresolved_count__gt=0) | Q(status=ConversationStatus.HUMAN_HANDOVER)
    ).select_related('customer').order_by('-last_message_at')

    unanswered_items = [
        {
            'id': c.id,
            'conversation_id': c.id,
            'type': 'ENQUIRY',
            'title': f"Enquiry from {c.customer.name or c.customer.phone_number}",
            'contact_id': c.customer_id,
            'contact_name': c.customer.name or c.customer.phone_number,
            'phone': c.customer.phone_number,
            'last_message_at': c.last_message_at.isoformat() if c.last_message_at else None,
            'status': c.status,
            'assigned_staff': c.assigned_staff.username if c.assigned_staff else None,
            'urgent': c.unresolved_count > 0 or c.status == ConversationStatus.HUMAN_HANDOVER,
        }
        for c in unanswered_convs_qs[:25]
    ]

    # 2. Today's follow-ups
    today_tasks_qs = Activity.objects.filter(
        tenant=tenant,
        status=ActivityStatus.PENDING,
        due_date__gte=today_start,
        due_date__lt=today_end
    ).select_related('contact', 'deal', 'assigned_to')

    today_followups = [
        {
            'id': a.id,
            'type': 'FOLLOW_UP_TODAY',
            'title': a.title,
            'activity_type': a.activity_type,
            'priority': a.priority,
            'due_date': a.due_date.isoformat() if a.due_date else None,
            'contact_name': a.contact.name or a.contact.phone_number if a.contact else None,
            'deal_title': a.deal.title if a.deal else None,
            'assigned_to': a.assigned_to.username if a.assigned_to else None,
        }
        for a in today_tasks_qs[:25]
    ]

    # 3. Overdue tasks
    overdue_tasks_qs = Activity.objects.filter(
        tenant=tenant,
        status=ActivityStatus.PENDING,
        due_date__lt=now
    ).select_related('contact', 'deal', 'assigned_to')

    overdue_tasks = [
        {
            'id': a.id,
            'type': 'OVERDUE_TASK',
            'title': a.title,
            'activity_type': a.activity_type,
            'priority': a.priority,
            'due_date': a.due_date.isoformat() if a.due_date else None,
            'contact_name': a.contact.name or a.contact.phone_number if a.contact else None,
            'deal_title': a.deal.title if a.deal else None,
            'assigned_to': a.assigned_to.username if a.assigned_to else None,
        }
        for a in overdue_tasks_qs[:25]
    ]

    # 4. Stale deals
    open_stages = DealStage.objects.filter(pipeline__tenant=tenant, is_won=False, is_lost=False)
    stale_deals_qs = Deal.objects.filter(
        tenant=tenant,
        stage__in=open_stages,
        updated_at__lt=stale_cutoff
    ).select_related('contact', 'stage', 'owner')

    stale_deals = [
        {
            'id': d.id,
            'type': 'STALE_DEAL',
            'title': d.title,
            'stage_name': d.stage.name if d.stage else 'Unassigned',
            'amount': str(d.amount) if d.amount else '0',
            'currency': d.currency,
            'updated_at': d.updated_at.isoformat(),
            'owner': d.owner.username if d.owner else 'Unassigned',
            'contact_name': d.contact.name or d.contact.phone_number if d.contact else None,
        }
        for d in stale_deals_qs[:25]
    ]

    # 5. Deals without next activity
    deals_without_action_qs = Deal.objects.filter(
        tenant=tenant,
        stage__in=open_stages
    ).annotate(
        pending_act_count=Count('activities', filter=Q(activities__status=ActivityStatus.PENDING))
    ).filter(pending_act_count=0).select_related('contact', 'stage', 'owner')

    deals_without_action = [
        {
            'id': d.id,
            'type': 'NO_NEXT_ACTION',
            'title': d.title,
            'stage_name': d.stage.name if d.stage else 'Unassigned',
            'amount': str(d.amount) if d.amount else '0',
            'currency': d.currency,
            'owner': d.owner.username if d.owner else 'Unassigned',
            'contact_name': d.contact.name or d.contact.phone_number if d.contact else None,
        }
        for d in deals_without_action_qs[:25]
    ]

    unanswered_count = unanswered_convs_qs.count()
    today_count = today_tasks_qs.count()
    overdue_count = overdue_tasks_qs.count()
    stale_count = stale_deals_qs.count()
    no_action_count = deals_without_action_qs.count()

    return {
        'summary': {
            'unanswered_count': unanswered_count,
            'today_followups_count': today_count,
            'overdue_count': overdue_count,
            'stale_deals_count': stale_count,
            'no_action_deals_count': no_action_count,
            'total_actionable': (
                unanswered_count + today_count +
                overdue_count + stale_count + no_action_count
            )
        },
        'unanswered_enquiries': unanswered_items,
        'today_followups': today_followups,
        'overdue_tasks': overdue_tasks,
        'stale_deals': stale_deals,
        'deals_without_action': deals_without_action,
    }


def assign_lead_round_robin(tenant, contact=None, conversation=None):
    """
    Assigns contact and/or conversation to tenant staff using least-workload round-robin.
    Idempotent: will not overwrite existing manual assignments unless unassigned.
    """
    eligible_members = TenantMembership.objects.filter(
        tenant=tenant,
        is_active=True
    ).select_related('user')

    if not eligible_members.exists():
        return None

    # Find member with fewest open conversations
    candidate_user = None
    min_workload = float('inf')

    for m in eligible_members:
        u = m.user
        workload = Conversation.objects.filter(
            tenant=tenant,
            assigned_staff=u
        ).exclude(status=ConversationStatus.CLOSED).count()

        if workload < min_workload:
            min_workload = workload
            candidate_user = u

    if not candidate_user:
        candidate_user = eligible_members.first().user

    if contact and not contact.owner:
        contact.owner = candidate_user
        contact.save(update_fields=['owner', 'updated_at'])
        try:
            from apps.crm.automation_engine import record_business_event
            record_business_event(
                tenant=tenant,
                event_type='lead.assigned',
                entity_type='contact',
                entity_id=contact.id,
                payload={'assigned_to': candidate_user.username, 'phone': contact.phone_number},
                dedup_key=f"contact:{contact.id}:assigned:{candidate_user.id}:{int(timezone.now().timestamp())}"
            )
        except Exception:
            pass

    if conversation and not conversation.assigned_staff:
        conversation.assigned_staff = candidate_user
        conversation.save(update_fields=['assigned_staff', 'updated_at'])

    return candidate_user


def track_first_human_response(conversation, staff_user):
    """
    Records staff pickup and first human response timestamp from authorized staff-send lifecycle.
    Separates genuine human response from bot replies and internal notes.
    """
    if not staff_user or not getattr(staff_user, 'is_authenticated', False):
        return None

    now = timezone.now()
    changed = []
    if not conversation.picked_up_at:
        conversation.picked_up_at = now
        conversation.assigned_staff = staff_user
        conversation.status = ConversationStatus.HUMAN_HANDOVER
        conversation.unresolved_count = 0
        changed.extend(['picked_up_at', 'assigned_staff', 'status', 'unresolved_count'])
    if hasattr(conversation, 'first_human_response_at') and not conversation.first_human_response_at:
        conversation.first_human_response_at = now
        changed.append('first_human_response_at')
    if hasattr(conversation, 'unread_count') and conversation.unread_count:
        conversation.unread_count = 0
        changed.append('unread_count')
    if changed:
        changed.append('updated_at')
        conversation.save(update_fields=changed)
    return conversation.picked_up_at
