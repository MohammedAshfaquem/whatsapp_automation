import csv
import io
import re
from datetime import datetime, time
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo

from django.db import transaction, DatabaseError
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from apps.chatbot.models import Customer, Conversation, Message, MessageDirection, SenderType
from apps.bookings.models import Booking
from .models import (
    Company,
    Pipeline,
    DealStage,
    Deal,
    DealStageHistory,
    Activity,
    ActivityType,
    ActivityStatus,
    ActivityPriority,
    ContactNote,
    ContactMergeAudit
)


def get_tenant_timezone(tenant=None) -> ZoneInfo:
    """Returns ZoneInfo for the tenant, defaulting to Asia/Kolkata."""
    return ZoneInfo("Asia/Kolkata")


def normalize_phone_number(raw_phone: str) -> str:
    """
    Standardize phone numbers into E.164-like international format without guessing ambiguous countries.
    - Strips spaces, hyphens, brackets, dots.
    - If 10 digits starting with 6, 7, 8, or 9 (Indian mobile), prefixes +91.
    - If 11 digits starting with 0 followed by 6-9, converts 0 to +91.
    - If 12 digits starting with 91, prefixes +.
    - If starts with +, retains + and digits.
    - If invalid or non-numeric, preserves raw string for validation.
    """
    if not raw_phone:
        return ""
    cleaned = re.sub(r'[\s\-\(\)\.]+', '', str(raw_phone).strip())
    if not cleaned:
        return ""

    if cleaned.startswith('+'):
        digits = re.sub(r'\D', '', cleaned)
        return f"+{digits}" if len(digits) >= 7 else raw_phone.strip()

    # Pure digits check
    digits = re.sub(r'\D', '', cleaned)
    if not digits or len(digits) < 7:
        return raw_phone.strip()

    if len(digits) == 10 and digits[0] in '6789':
        return f"+91{digits}"
    elif len(digits) == 11 and digits.startswith('0') and digits[1] in '6789':
        return f"+91{digits[1:]}"
    elif len(digits) == 12 and digits.startswith('91'):
        return f"+{digits}"
    elif len(digits) >= 10:
        return f"+{digits}"
    return f"+{digits}"


def find_potential_duplicates(tenant, phone: str = "", email: str = "", exclude_contact_id: Optional[int] = None) -> List[Customer]:
    """
    Search for contacts within the same tenant matching normalized phone or email.
    """
    if not tenant:
        return []

    q = Q(tenant=tenant)
    conditions = Q()

    normalized_phone = normalize_phone_number(phone) if phone else ""
    if normalized_phone:
        conditions |= Q(phone_number=normalized_phone)

    clean_email = email.strip().lower() if email else ""
    if clean_email:
        conditions |= Q(email__iexact=clean_email)

    if not conditions:
        return []

    qs = Customer.objects.filter(q & conditions)
    if exclude_contact_id:
        qs = qs.exclude(id=exclude_contact_id)
    return list(qs)


@transaction.atomic
def merge_contacts(tenant, primary_contact: Customer, duplicate_contact: Customer, performed_by: Optional[User] = None, preferred_fields: Optional[Dict[str, Any]] = None) -> Customer:
    """
    Explicit, transactional, tenant-scoped contact merge.
    Transfers deals, activities, conversations, notes, bookings, and audits consolidation.
    """
    if primary_contact.tenant_id != tenant.id or duplicate_contact.tenant_id != tenant.id:
        raise ValidationError("Both contacts must belong to the active workspace to merge.")
    if primary_contact.id == duplicate_contact.id:
        raise ValidationError("Cannot merge a contact into itself.")

    preferred_fields = preferred_fields or {}

    # 1. Update preferred fields onto primary
    if 'name' in preferred_fields and preferred_fields['name']:
        primary_contact.name = preferred_fields['name']
    elif not primary_contact.name and duplicate_contact.name:
        primary_contact.name = duplicate_contact.name

    if 'email' in preferred_fields and preferred_fields['email']:
        primary_contact.email = preferred_fields['email']
    elif not primary_contact.email and duplicate_contact.email:
        primary_contact.email = duplicate_contact.email

    if 'company' in preferred_fields:
        primary_contact.company = preferred_fields['company']
    elif not primary_contact.company and duplicate_contact.company:
        primary_contact.company = duplicate_contact.company

    if 'owner' in preferred_fields:
        primary_contact.owner = preferred_fields['owner']
    elif not primary_contact.owner and duplicate_contact.owner:
        primary_contact.owner = duplicate_contact.owner

    # Combine tags
    combined_tags = list(set((primary_contact.tags or []) + (duplicate_contact.tags or [])))
    primary_contact.tags = combined_tags

    # Keep latest contacted timestamp
    if duplicate_contact.last_contacted_at:
        if not primary_contact.last_contacted_at or duplicate_contact.last_contacted_at > primary_contact.last_contacted_at:
            primary_contact.last_contacted_at = duplicate_contact.last_contacted_at

    # Append notes if duplicate had notes
    if duplicate_contact.notes:
        primary_contact.notes = f"{primary_contact.notes}\n[Merged from {duplicate_contact.phone_number}]: {duplicate_contact.notes}".strip()

    primary_contact.save()

    # 2. Transfer relationships
    transferred_deals = Deal.objects.filter(contact=duplicate_contact).update(contact=primary_contact)
    transferred_activities = Activity.objects.filter(contact=duplicate_contact).update(contact=primary_contact)
    transferred_notes = ContactNote.objects.filter(contact=duplicate_contact).update(contact=primary_contact)
    transferred_bookings = Booking.objects.filter(customer=duplicate_contact).update(customer=primary_contact)
    transferred_conversations = Conversation.objects.filter(customer=duplicate_contact).update(customer=primary_contact)

    # 3. Create Audit Record
    audit = ContactMergeAudit.objects.create(
        tenant=tenant,
        primary_contact=primary_contact,
        merged_phone=duplicate_contact.phone_number,
        merged_name=duplicate_contact.name or '',
        performed_by=performed_by,
        details={
            'transferred_deals': transferred_deals,
            'transferred_activities': transferred_activities,
            'transferred_notes': transferred_notes,
            'transferred_bookings': transferred_bookings,
            'transferred_conversations': transferred_conversations,
            'duplicate_id': duplicate_contact.id,
            'duplicate_email': duplicate_contact.email,
        }
    )

    # 4. Remove duplicate record safely
    duplicate_contact.delete()

    return primary_contact


def change_deal_stage(deal_id: int, new_stage_id: int, user: Optional[User] = None, notes: str = "", lost_reason: str = "") -> Deal:
    """
    Safely transition deal stage with concurrency lock, history recording, and terminal status handling.
    """
    with transaction.atomic():
        deal = Deal.objects.select_for_update().get(id=deal_id)
        new_stage = DealStage.objects.get(id=new_stage_id)

        if new_stage.pipeline_id != deal.pipeline_id:
            raise ValidationError("Target stage does not belong to the deal's active pipeline.")

        old_stage = deal.stage
        if old_stage.id == new_stage.id:
            return deal

        deal.stage = new_stage
        deal.probability = new_stage.probability

        if new_stage.is_won:
            deal.won_at = timezone.now()
            deal.lost_at = None
            deal.lost_reason = ""
        elif new_stage.is_lost:
            deal.lost_at = timezone.now()
            deal.won_at = None
            if lost_reason:
                deal.lost_reason = lost_reason.strip()
        else:
            # Reopening or moving between active stages
            deal.won_at = None
            deal.lost_at = None

        deal.save()

        DealStageHistory.objects.create(
            deal=deal,
            from_stage=old_stage,
            to_stage=new_stage,
            changed_by=user,
            notes=notes.strip()
        )

        # Record durable outbox business events
        from apps.crm.automation_engine import record_business_event, process_pending_business_events
        base_payload = {
            'deal_id': deal.id,
            'deal_title': deal.title,
            'amount': str(deal.amount),
            'from_stage': old_stage.name,
            'to_stage': new_stage.name,
            'stage_name': new_stage.name,
            'pipeline_id': deal.pipeline_id,
            'contact_id': deal.contact_id,
            'owner': deal.owner.username if deal.owner else None,
        }
        event = record_business_event(
            tenant=deal.tenant,
            event_type='deal.stage_changed',
            entity_type='deal',
            entity_id=deal.id,
            payload=base_payload,
            dedup_key=f"deal:{deal.id}:stage:{new_stage.id}:{int(timezone.now().timestamp())}"
        )
        if new_stage.is_won:
            record_business_event(
                tenant=deal.tenant,
                event_type='deal.won',
                entity_type='deal',
                entity_id=deal.id,
                payload=base_payload,
                dedup_key=f"deal:{deal.id}:won:{int(timezone.now().timestamp())}",
                causation_id=event.event_id
            )
        elif new_stage.is_lost:
            lost_payload = dict(base_payload)
            lost_payload['lost_reason'] = deal.lost_reason
            record_business_event(
                tenant=deal.tenant,
                event_type='deal.lost',
                entity_type='deal',
                entity_id=deal.id,
                payload=lost_payload,
                dedup_key=f"deal:{deal.id}:lost:{int(timezone.now().timestamp())}",
                causation_id=event.event_id
            )

        transaction.on_commit(lambda: process_pending_business_events(tenant=deal.tenant))

        return deal


def get_activities_for_tenant(tenant, user: Optional[User] = None, filter_view: str = 'my_tasks'):
    """
    Retrieves filtered activities for a tenant workspace.
    filter_view options: 'my_tasks', 'today', 'upcoming', 'overdue', 'completed', 'all'
    """
    now = timezone.now()
    tz = get_tenant_timezone(tenant)
    today_start = timezone.datetime.combine(timezone.localdate(now, tz), time.min, tzinfo=tz)
    today_end = timezone.datetime.combine(timezone.localdate(now, tz), time.max, tzinfo=tz)

    qs = Activity.objects.filter(tenant=tenant).select_related('contact', 'company', 'deal', 'assigned_to')

    if filter_view == 'my_tasks' and user:
        return qs.filter(assigned_to=user, status=ActivityStatus.PENDING).order_by('due_date', '-priority')
    elif filter_view == 'today':
        return qs.filter(status=ActivityStatus.PENDING, due_date__range=(today_start, today_end)).order_by('due_date', '-priority')
    elif filter_view == 'overdue':
        return qs.filter(status=ActivityStatus.PENDING, due_date__lt=now).order_by('due_date', '-priority')
    elif filter_view == 'upcoming':
        return qs.filter(status=ActivityStatus.PENDING, due_date__gt=today_end).order_by('due_date', '-priority')
    elif filter_view == 'completed':
        return qs.filter(status=ActivityStatus.COMPLETED).order_by('-completed_at')
    return qs.order_by('-due_date')


def get_customer_timeline(customer: Customer, page: int = 1, page_size: int = 30) -> Dict[str, Any]:
    """
    Unified Customer Timeline aggregating:
    - WhatsApp / Simulated Messages
    - Conversation handover events
    - Internal staff notes
    - CRM activities & tasks
    - Requests / Bookings
    - Deals & stage history
    """
    timeline = []

    # 1. Messages & Deliveries
    messages_qs = (
        Message.objects
        .filter(conversation__customer=customer)
        .select_related('conversation')
        .order_by('-created_at')[:80]
    )
    for m in messages_qs:
        timeline.append({
            'type': 'MESSAGE',
            'event_type': 'message',
            'timestamp': m.created_at,
            'title': f"{m.get_direction_display()} WhatsApp message" if m.conversation.channel == 'WHATSAPP' else f"{m.get_direction_display()} message",
            'direction': m.direction,
            'sender_type': m.sender_type,
            'text': m.message_text,
            'details': {
                'text': m.message_text,
                'direction': 'inbound' if m.direction == MessageDirection.INBOUND else 'outbound',
                'channel': m.conversation.channel,
            },
            'channel': m.conversation.channel,
            'status': m.processing_status,
            'raw_id': m.id,
        })

    # 2. Handover events
    for conv in customer.conversations.filter(status='HUMAN_HANDOVER'):
        timeline.append({
            'type': 'HANDOVER',
            'event_type': 'handover',
            'timestamp': conv.picked_up_at or conv.updated_at,
            'title': 'AI Assistant Handed Over to Staff',
            'text': conv.handoff_summary or 'Customer requested human assistance.',
            'details': {
                'summary': conv.handoff_summary or 'Customer requested human assistance.',
            },
            'staff': conv.assigned_staff.get_full_name() or conv.assigned_staff.username if conv.assigned_staff else 'Unassigned Queue',
        })

    # 3. Internal Notes
    for note in customer.internal_notes.select_related('author').all():
        timeline.append({
            'type': 'NOTE',
            'event_type': 'note',
            'timestamp': note.created_at,
            'title': f"Internal Note by @{note.author.username if note.author else 'Staff'}",
            'text': note.content,
            'author': note.author.get_full_name() or note.author.username if note.author else 'Staff',
            'details': {
                'content': note.content,
            },
            'raw_id': note.id,
        })

    # 4. Activities / Tasks
    for act in customer.activities.select_related('assigned_to', 'completed_by').all():
        raw_ts = act.completed_at or act.due_date or act.created_at
        if raw_ts:
            if hasattr(raw_ts, 'hour'):
                ts = raw_ts if timezone.is_aware(raw_ts) else timezone.make_aware(raw_ts)
            else:
                ts = timezone.make_aware(datetime.combine(raw_ts, datetime.min.time()))
        else:
            ts = act.created_at or timezone.now()

        timeline.append({
            'type': 'ACTIVITY',
            'event_type': 'activity',
            'timestamp': ts,
            'title': f"Task: {act.title} [{act.get_status_display()}]",
            'activity_type': act.get_activity_type_display(),
            'status': act.status,
            'priority': act.priority,
            'assigned_to': act.assigned_to.get_full_name() or act.assigned_to.username if act.assigned_to else 'Unassigned',
            'text': act.notes,
            'details': {
                'type': act.get_activity_type_display(),
                'priority': act.get_priority_display(),
                'status': act.status,
            },
            'raw_id': act.id,
        })

    # 5. Bookings / Consultation / Demo requests
    for b in customer.bookings.select_related('service').all():
        svc_name = b.service.name if b.service else (b.ac_type or 'General Request')
        timeline.append({
            'type': 'REQUEST',
            'event_type': 'booking',
            'timestamp': b.created_at,
            'title': f"Request #{b.id}: {svc_name}",
            'status': b.get_status_display(),
            'details': {
                'service': svc_name,
                'status': b.get_status_display(),
                'problem_description': b.problem_description,
            },
            'raw_id': b.id,
        })

    # 6. Deals & Stage History
    for deal in customer.deals.prefetch_related('stage_history__to_stage', 'stage_history__from_stage').all():
        stage_title = deal.stage.name if deal.stage else 'Unassigned'
        deal_amount_num = float(deal.amount) if deal.amount else 0.0
        timeline.append({
            'type': 'DEAL',
            'event_type': 'deal',
            'timestamp': deal.created_at,
            'title': f"Deal Created: {deal.title}",
            'text': f"Stage: {stage_title} | Amount: {deal.currency} {deal_amount_num:.2f}",
            'details': {
                'stage': stage_title,
                'amount': deal_amount_num,
                'currency': deal.currency,
            },
            'raw_id': deal.id,
        })
        for sh in deal.stage_history.all():
            timeline.append({
                'type': 'STAGE_CHANGE',
                'event_type': 'stage_change',
                'timestamp': sh.created_at,
                'title': f"Deal Stage Changed: {deal.title}",
                'text': f"{sh.from_stage.name if sh.from_stage else 'Start'} → {sh.to_stage.name}" + (f" ({sh.notes})" if sh.notes else ""),
                'author': sh.changed_by.username if sh.changed_by else 'System',
                'details': {
                    'from_stage': sh.from_stage.name if sh.from_stage else None,
                    'to_stage': sh.to_stage.name,
                    'notes': sh.notes,
                },
                'raw_id': deal.id,
            })

    # Sort descending by timestamp safely
    def _safe_sort_key(item):
        val = item.get('timestamp')
        if val is None:
            return timezone.now()
        if hasattr(val, 'hour'):
            return val if timezone.is_aware(val) else timezone.make_aware(val)
        return timezone.make_aware(datetime.combine(val, datetime.min.time()))

    timeline.sort(key=_safe_sort_key, reverse=True)

    # Paginate
    total_count = len(timeline)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    start = (page - 1) * page_size
    end = start + page_size
    items = timeline[start:end]

    return {
        'total': total_count,
        'total_count': total_count,
        'total_pages': total_pages,
        'page': page,
        'page_size': page_size,
        'has_next': end < total_count,
        'has_previous': page > 1,
        'items': items
    }


def sanitize_csv_cell(value: Any) -> str:
    """
    Prevents spreadsheet formula injection (CSV Injection / Formula Injection).
    If a string starts with =, +, -, @, tab, or carriage return, prefixes with an apostrophe.
    """
    if value is None:
        return ""
    val_str = str(value)
    if val_str and val_str[0] in ('=', '+', '-', '@', '\t', '\r'):
        return f"'{val_str}"
    return val_str


def export_contacts_to_csv(tenant, queryset=None) -> str:
    """
    Exports tenant contacts to sanitized CSV format.
    """
    if queryset is None:
        queryset = Customer.objects.filter(tenant=tenant).select_related('company', 'owner').order_by('name')

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name",
        "Phone Number",
        "Email",
        "Company",
        "Lifecycle Status",
        "Source",
        "Owner",
        "Tags",
        "Notes",
        "Last Contacted At",
        "Created At"
    ])

    for c in queryset:
        tags_str = ", ".join(c.tags or [])
        writer.writerow([
            sanitize_csv_cell(c.name),
            sanitize_csv_cell(c.phone_number),
            sanitize_csv_cell(c.email),
            sanitize_csv_cell(c.company.name if c.company else ""),
            sanitize_csv_cell(c.get_lifecycle_status_display()),
            sanitize_csv_cell(c.get_source_display()),
            sanitize_csv_cell(c.owner.username if c.owner else ""),
            sanitize_csv_cell(tags_str),
            sanitize_csv_cell(c.notes),
            c.last_contacted_at.strftime("%Y-%m-%d %H:%M") if c.last_contacted_at else "",
            c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else ""
        ])

    return output.getvalue()


def import_contacts_from_csv(
    tenant,
    file_content: str,
    preview_only: bool = False,
    owner_mapping: Optional[Dict[str, int]] = None,
    duplicate_action: str = 'skip'
) -> Dict[str, Any]:
    """
    Imports contacts from CSV with validation, preview, row errors, and injection checks.
    duplicate_action: 'skip', 'update', 'error'
    """
    owner_mapping = owner_mapping or {}
    reader = csv.DictReader(io.StringIO(file_content.strip()))

    rows_preview = []
    errors = []
    imported_count = 0
    updated_count = 0
    skipped_count = 0

    MAX_ROWS = 500
    rows = list(reader)
    if len(rows) > MAX_ROWS:
        return {
            'success': False,
            'error': f"CSV file exceeds the maximum limit of {MAX_ROWS} contacts per upload."
        }

    # Map available tenant users
    tenant_users = {
        m.user.username.lower(): m.user
        for m in tenant.memberships.filter(is_active=True).select_related('user')
    }

    for idx, row in enumerate(rows, start=2):  # 1-indexed, header is line 1
        # Normalize keys by stripping, lowercasing, and removing underscores/spaces
        row_norm = {re.sub(r'[\s_]+', '', str(k).strip().lower()): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
        name = row_norm.get('name', '')
        raw_phone = row_norm.get('phonenumber', '') or row_norm.get('phone', '')
        email = row_norm.get('email', '')
        company_name = row_norm.get('company', '')
        status_raw = row_norm.get('lifecyclestatus', '') or row_norm.get('status', '')
        source_raw = row_norm.get('source', '')
        owner_name = row_norm.get('owner', '').lower()
        tags_raw = row_norm.get('tags', '')
        notes = row_norm.get('notes', '')

        normalized_phone = normalize_phone_number(raw_phone)
        if not normalized_phone or len(normalized_phone) < 8 or not normalized_phone.startswith('+'):
            errors.append({'row': idx, 'error': f"Invalid or missing phone number '{raw_phone}'."})
            continue

        # Validate owner if given
        assigned_owner = None
        if owner_name and owner_name in tenant_users:
            assigned_owner = tenant_users[owner_name]
        elif owner_name:
            errors.append({'row': idx, 'error': f"Assigned owner '@{owner_name}' is not an active member of this workspace."})
            continue

        # Parse tags
        tags_list = [t.strip() for t in tags_raw.split(',') if t.strip()] if tags_raw else []

        # Check existing duplicate
        existing = Customer.objects.filter(tenant=tenant, phone_number=normalized_phone).first()

        row_data = {
            'row_num': idx,
            'name': name,
            'phone': normalized_phone,
            'phone_number': normalized_phone,
            'email': email,
            'company': company_name,
            'lifecycle_status': status_raw or 'LEAD',
            'owner': assigned_owner.username if assigned_owner else '',
            'tags': tags_list,
            'notes': notes,
            'is_duplicate': bool(existing),
        }
        rows_preview.append(row_data)

        if not preview_only:
            if existing:
                if duplicate_action == 'error':
                    errors.append({'row': idx, 'error': f"Contact with phone '{normalized_phone}' already exists."})
                    continue
                elif duplicate_action == 'skip':
                    skipped_count += 1
                    continue
                elif duplicate_action == 'update':
                    if name:
                        existing.name = name
                    if email:
                        existing.email = email
                    if assigned_owner:
                        existing.owner = assigned_owner
                    if tags_list:
                        existing.tags = list(set((existing.tags or []) + tags_list))
                    if notes:
                        existing.notes = f"{existing.notes}\n{notes}".strip()
                    existing.save()
                    updated_count += 1
                    continue

            # Check contact limit before creating new record
            if not tenant.can_add_contact():
                errors.append({'row': idx, 'error': f"Contact limit reached ({tenant.effective_max_contacts} contacts) for your current subscription plan."})
                break

            # Create Company if given
            company_obj = None
            if company_name:
                company_obj, _ = Company.objects.get_or_create(tenant=tenant, name=company_name)

            Customer.objects.create(
                tenant=tenant,
                phone_number=normalized_phone,
                name=name,
                email=email,
                company=company_obj,
                owner=assigned_owner,
                lifecycle_status=status_raw if status_raw in [c[0] for c in Customer._meta.get_field('lifecycle_status').choices] else 'LEAD',
                tags=tags_list,
                notes=notes,
                source=source_raw or 'IMPORT'
            )
            imported_count += 1

    return {
        'success': len(errors) == 0 or not preview_only,
        'total_rows': len(rows),
        'valid_rows_count': len(rows_preview),
        'invalid_rows_count': len(errors),
        'preview': rows_preview[:15],
        'preview_rows': rows_preview[:15],
        'imported_count': imported_count,
        'updated_count': updated_count,
        'skipped_count': skipped_count,
        'errors': errors,
    }


def get_crm_metrics(tenant) -> Dict[str, Any]:
    """
    Computes tenant-scoped CRM metrics and pipeline analytics.
    Distinguishes currencies strictly without cross-currency mathematical pollution.
    """
    now = timezone.now()
    deals_qs = Deal.objects.filter(tenant=tenant).select_related('stage', 'owner', 'pipeline')

    # 1. Pipeline Value grouped by Currency
    open_deals = deals_qs.filter(won_at__isnull=True, lost_at__isnull=True)
    currency_pipeline_values = {}
    for row in open_deals.values('currency').annotate(total=Sum('amount'), count=Count('id')):
        curr = row['currency'] or 'INR'
        currency_pipeline_values[curr] = {
            'total': row['total'] or Decimal('0.00'),
            'count': row['count'],
        }

    # 2. Won Deals value grouped by Currency
    won_deals = deals_qs.filter(won_at__isnull=False)
    currency_won_values = {}
    for row in won_deals.values('currency').annotate(total=Sum('amount'), count=Count('id')):
        curr = row['currency'] or 'INR'
        currency_won_values[curr] = {
            'total': row['total'] or Decimal('0.00'),
            'count': row['count'],
        }

    # 3. Deals by Stage
    deals_by_stage = []
    for stage in DealStage.objects.filter(pipeline__tenant=tenant).order_by('pipeline', 'order'):
        cnt = deals_qs.filter(stage=stage).count()
        deals_by_stage.append({
            'stage_id': stage.id,
            'stage_name': stage.name,
            'pipeline_name': stage.pipeline.name,
            'count': cnt,
            'is_won': stage.is_won,
            'is_lost': stage.is_lost,
        })

    # 4. Deals by Owner
    deals_by_owner = []
    for m in tenant.memberships.filter(is_active=True).select_related('user'):
        u = m.user
        cnt = deals_qs.filter(owner=u, won_at__isnull=True, lost_at__isnull=True).count()
        won_cnt = deals_qs.filter(owner=u, won_at__isnull=False).count()
        deals_by_owner.append({
            'username': u.username,
            'name': u.get_full_name() or u.username,
            'open_deals': cnt,
            'won_deals': won_cnt,
        })

    # 5. Overdue activities
    overdue_activities_count = Activity.objects.filter(
        tenant=tenant,
        status=ActivityStatus.PENDING,
        due_date__lt=now
    ).count()

    # 6. Deals without next activity
    deals_without_activity = (
        open_deals
        .annotate(pending_acts=Count('activities', filter=Q(activities__status=ActivityStatus.PENDING)))
        .filter(pending_acts=0)
        .count()
    )

    # 7. Contacts by Source
    contacts_qs = Customer.objects.filter(tenant=tenant)
    contacts_by_source = list(contacts_qs.values('source').annotate(count=Count('id')).order_by('-count'))

    # 8. Unassigned contacts
    unassigned_contacts_count = contacts_qs.filter(owner__isnull=True).count()

    return {
        'total_contacts': contacts_qs.count(),
        'unassigned_contacts': unassigned_contacts_count,
        'open_deals_count': open_deals.count(),
        'won_deals_count': won_deals.count(),
        'lost_deals_count': deals_qs.filter(lost_at__isnull=False).count(),
        'pipeline_values': currency_pipeline_values,
        'won_values': currency_won_values,
        'deals_by_stage': deals_by_stage,
        'deals_by_owner': deals_by_owner,
        'overdue_activities': overdue_activities_count,
        'deals_without_activity': deals_without_activity,
        'contacts_by_source': contacts_by_source,
    }
