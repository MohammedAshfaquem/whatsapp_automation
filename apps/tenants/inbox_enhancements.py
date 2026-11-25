"""
Release 3 Client Operational Enhancements:
- Inbox media uploads & tenant-scoped private media downloads
- Chat transfer between tenant staff members
- Unread count reset (mark-read)
- Contacts CSV import preview & transactional execute
"""
import csv
import io
import json
import os
import re
import secrets
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.chatbot.models import (
    ChannelChoice,
    ContactLifecycleStatus,
    ContactSource,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    ProcessingStatus,
    SenderType,
)
from apps.whatsapp.delivery import dispatch
from apps.whatsapp.delivery_context import cancel_pending_bot_deliveries
from apps.whatsapp.models import WhatsAppDelivery

from .capabilities import can_perform_action
from .models import AuditLogAction, TenantAuditLog, TenantMembership
from .spa_api import _parse_body, api_login_required

User = get_user_model()

MAX_INBOX_MEDIA_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_INBOX_MEDIA_MIMES = {
    'image/jpeg': 'image',
    'image/png': 'image',
    'image/webp': 'image',
    'application/pdf': 'document',
    'text/plain': 'document',
    'audio/mpeg': 'audio',
    'audio/ogg': 'audio',
    'audio/mp4': 'audio',
    'video/mp4': 'video',
}
MAX_CSV_IMPORT_BYTES = 2 * 1024 * 1024
MAX_CSV_IMPORT_ROWS = 2000


def save_inbox_media(uploaded_file, tenant_id: int, conversation_id: int) -> dict:
    """Validate and persist an inbox attachment safely under tenant-scoped storage."""
    if not uploaded_file:
        raise ValueError('Select a file to upload.')
    if uploaded_file.size > MAX_INBOX_MEDIA_BYTES:
        raise ValueError('Media attachment must be 10 MB or smaller.')
    mime = (getattr(uploaded_file, 'content_type', '') or '').split(';')[0].strip().lower()
    raw_name = os.path.basename(getattr(uploaded_file, 'name', '') or 'attachment')
    ext = os.path.splitext(raw_name)[1].lower()
    ext_fallback = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.pdf': 'application/pdf',
        '.txt': 'text/plain',
        '.mp3': 'audio/mpeg',
        '.ogg': 'audio/ogg',
        '.m4a': 'audio/mp4',
        '.mp4': 'video/mp4',
    }
    if mime not in ALLOWED_INBOX_MEDIA_MIMES:
        mime = ext_fallback.get(ext, mime)
    media_type = ALLOWED_INBOX_MEDIA_MIMES.get(mime)
    if not media_type:
        raise ValueError('Unsupported attachment format. Use JPG, PNG, WEBP, PDF, TXT, MP3, OGG, or MP4.')
    safe_base = ''.join(c if c.isalnum() or c in ('-', '_', '.') else '_' for c in raw_name)[:120] or 'attachment'
    key = f"inbox_media/{tenant_id}/{conversation_id}/{secrets.token_hex(8)}_{safe_base}"
    saved_key = default_storage.save(key, uploaded_file)
    return {
        'media_type': media_type,
        'media_key': saved_key,
        'media_name': safe_base,
        'media_mime': mime[:100],
        'media_size': int(uploaded_file.size or 0),
    }


@api_login_required
@require_POST
@transaction.atomic
def chat_media_reply_api(request, conversation_id):
    """Upload a media file and send it as an outbound staff reply in Human mode."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'inbox', 'send_message')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    origin = get_object_or_404(Conversation.objects.only('id', 'customer_id', 'tenant_id'), pk=conversation_id, tenant=tenant)
    Customer.objects.select_for_update().get(pk=origin.customer_id)
    conversation = get_object_or_404(Conversation.objects.select_for_update(of=('self',)).select_related('customer'), pk=conversation_id, tenant=tenant)

    if conversation.status != ConversationStatus.HUMAN_HANDOVER:
        return JsonResponse({'error': 'Switch to Human mode before sending media attachments.'}, status=409)
    if conversation.assigned_staff_id not in (None, request.user.pk) and not request.user.is_superuser:
        return JsonResponse({'error': f'This conversation is assigned to @{conversation.assigned_staff.username}.'}, status=409)

    uploaded = request.FILES.get('file')
    caption = (request.POST.get('caption') or request.POST.get('text') or '').strip()[:1024]
    try:
        media_meta = save_inbox_media(uploaded, tenant.pk, conversation.pk)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    now = timezone.now()
    if conversation.assigned_staff_id is None:
        conversation.assigned_staff = request.user
        conversation.picked_up_at = conversation.picked_up_at or now
    if conversation.first_human_response_at is None:
        conversation.first_human_response_at = now
    conversation.unread_count = 0
    conversation.last_message_at = now
    conversation.save(update_fields=['assigned_staff', 'picked_up_at', 'first_human_response_at', 'unread_count', 'last_message_at', 'updated_at'])

    display_text = caption or f"[{media_meta['media_type'].upper()}: {media_meta['media_name']}]"
    msg = Message.objects.create(
        conversation=conversation,
        direction=MessageDirection.OUTBOUND,
        sender_type=SenderType.HUMAN,
        message_text=display_text,
        processing_status=ProcessingStatus.PROCESSED,
        media_type=media_meta['media_type'],
        media_key=media_meta['media_key'],
        media_name=media_meta['media_name'],
        media_mime=media_meta['media_mime'],
        media_size=media_meta['media_size'],
        response_data={
            'author_username': request.user.username,
            'author_name': request.user.get_full_name() or request.user.username,
            'media_type': media_meta['media_type'],
            'media_name': media_meta['media_name'],
        },
    )

    delivery_id = None
    if conversation.channel == ChannelChoice.WHATSAPP and conversation.customer:
        delivery = WhatsAppDelivery.objects.create(
            tenant=tenant,
            dedup_key=f'staff:{msg.pk}',
            recipient_phone=conversation.customer.phone_number,
            payload={
                'text': display_text,
                'media': {
                    'media_type': media_meta['media_type'],
                    'storage_key': media_meta['media_key'],
                    'mime_type': media_meta['media_mime'],
                    'filename': media_meta['media_name'],
                    'caption': caption,
                },
                'conversation_id': conversation.pk,
                'message_id': msg.pk,
                'sender_type': 'HUMAN',
            },
        )
        delivery_id = delivery.id
        transaction.on_commit(lambda d_pk=delivery.pk: dispatch(d_pk))

    return JsonResponse({
        'status': 'sent',
        'message': {
            'id': msg.id,
            'direction': msg.direction,
            'sender_type': msg.sender_type,
            'text': msg.message_text,
            'media_type': msg.media_type,
            'media_name': msg.media_name,
            'media_mime': msg.media_mime,
            'media_size': msg.media_size,
            'media_url': f'/api/inbox/media/{msg.id}/',
        },
        'delivery_id': delivery_id,
    }, status=201)


@api_login_required
@require_GET
def inbox_media_download_api(request, message_id):
    """Serve stored inbox attachment strictly to authenticated members of the owning tenant."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'inbox', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    msg = get_object_or_404(
        Message.objects.select_related('conversation'),
        pk=message_id,
        conversation__tenant=tenant,
    )
    expected_prefix = f"inbox_media/{tenant.pk}/{msg.conversation_id}/"
    if not msg.media_key or not msg.media_key.startswith(expected_prefix) or not default_storage.exists(msg.media_key):
        return JsonResponse({'error': 'Attachment not found.'}, status=404)

    with default_storage.open(msg.media_key, 'rb') as fh:
        content = fh.read()
    resp = HttpResponse(content, content_type=msg.media_mime or 'application/octet-stream')
    disp = 'inline' if msg.media_type in ('image', 'audio', 'video') else 'attachment'
    resp['Content-Disposition'] = f'{disp}; filename="{msg.media_name or "attachment"}"'
    resp['X-Content-Type-Options'] = 'nosniff'
    resp['Cache-Control'] = 'private, max-age=300'
    return resp


@api_login_required
@require_POST
@transaction.atomic
def chat_transfer_api(request, conversation_id):
    """Transfer conversation ownership to another active staff member inside the same tenant."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'inbox', 'assign')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    origin = get_object_or_404(Conversation.objects.only('id', 'customer_id', 'tenant_id'), pk=conversation_id, tenant=tenant)
    Customer.objects.select_for_update().get(pk=origin.customer_id)
    conversation = get_object_or_404(Conversation.objects.select_for_update(of=('self',)).select_related('customer', 'assigned_staff'), pk=conversation_id, tenant=tenant)

    data = _parse_body(request)
    target_user_id = data.get('target_user_id')
    note = str(data.get('note') or '').strip()[:300]
    if not target_user_id:
        return JsonResponse({'error': 'Select a target team member.'}, status=400)

    target_membership = TenantMembership.objects.select_related('user').filter(
        tenant=tenant,
        user_id=int(target_user_id),
        is_active=True,
        user__is_active=True,
    ).first()
    if not target_membership:
        return JsonResponse({'error': 'Target staff member must belong actively to this workspace.'}, status=404)

    target_user = target_membership.user
    now = timezone.now()
    previous_staff = conversation.assigned_staff.username if conversation.assigned_staff else 'Unassigned'
    conversation.status = ConversationStatus.HUMAN_HANDOVER
    conversation.assigned_staff = target_user
    if conversation.picked_up_at is None:
        conversation.picked_up_at = now
    transfer_line = f"Transferred from @{previous_staff} to @{target_user.username} by @{request.user.username}"
    if note:
        transfer_line += f" ({note})"
    conversation.handoff_summary = (
        f"{conversation.handoff_summary}\n{transfer_line}".strip()
        if conversation.handoff_summary
        else transfer_line
    )[:1000]
    conversation.save(update_fields=['status', 'assigned_staff', 'picked_up_at', 'handoff_summary', 'updated_at'])

    if conversation.customer and data.get('assign_contact', True):
        conversation.customer.owner = target_user
        conversation.customer.save(update_fields=['owner', 'updated_at'])

    cancel_pending_bot_deliveries(conversation, 'transfer')

    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.CONVERSATION_TRANSFERRED,
        summary=f"Chat #{conversation.pk} transferred to @{target_user.username}",
        details={'conversation_id': conversation.pk, 'from': previous_staff, 'to': target_user.username},
    )

    return JsonResponse({
        'status': conversation.status,
        'status_display': conversation.get_status_display(),
        'assigned_staff': target_user.username,
        'assigned_staff_id': target_user.pk,
        'assigned_staff_name': target_user.get_full_name() or target_user.username,
        'handover_required': True,
        'handoff_summary': conversation.handoff_summary,
    })


@api_login_required
@require_POST
@transaction.atomic
def chat_mark_read_api(request, conversation_id):
    """Reset unread inbound message counter when a staff user opens the conversation."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'inbox', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    conv = get_object_or_404(Conversation.objects.select_for_update(), pk=conversation_id, tenant=tenant)
    if conv.unread_count != 0:
        conv.unread_count = 0
        conv.save(update_fields=['unread_count', 'updated_at'])
    return JsonResponse({'status': 'ok', 'conversation_id': conv.id, 'unread_count': 0})


def _normalize_e164(raw: str) -> str:
    cleaned = re.sub(r'[\s\-\(\)]', '', str(raw or '').strip())
    if not cleaned:
        return ''
    if cleaned.startswith('00'):
        cleaned = '+' + cleaned[2:]
    elif not cleaned.startswith('+'):
        cleaned = '+' + cleaned
    if not re.fullmatch(r'^\+[1-9]\d{7,14}$', cleaned):
        return ''
    return cleaned


def _parse_csv_payload(request) -> tuple[list[str], list[dict], dict]:
    if request.FILES.get('file'):
        upload = request.FILES['file']
        if upload.size > MAX_CSV_IMPORT_BYTES:
            raise ValueError('CSV file must be 2 MB or smaller.')
        raw_text = upload.read().decode('utf-8-sig', errors='replace')
        extra = request.POST.dict()
    else:
        data = _parse_body(request)
        raw_text = str(data.get('csv_text') or '')
        extra = data
    if len(raw_text.encode('utf-8')) > MAX_CSV_IMPORT_BYTES:
        raise ValueError('CSV payload exceeds 2 MB.')
    if not raw_text.strip():
        raise ValueError('Provide a non-empty CSV file or CSV text.')

    reader = csv.DictReader(io.StringIO(raw_text))
    if not reader.fieldnames:
        raise ValueError('CSV must include a header row.')
    headers = [h.strip() for h in reader.fieldnames if h and h.strip()]
    rows = []
    for idx, row in enumerate(reader):
        if idx >= MAX_CSV_IMPORT_ROWS:
            raise ValueError(f'Maximum {MAX_CSV_IMPORT_ROWS} rows supported per CSV import.')
        rows.append({(k or '').strip(): (v or '').strip() for k, v in row.items() if k})
    return headers, rows, extra


def _infer_column_mapping(headers: list[str], provided: dict | None = None) -> dict:
    if isinstance(provided, dict) and provided:
        return {k: str(v).strip() for k, v in provided.items() if v}
    lowered = {h.lower(): h for h in headers}
    mapping = {}
    for target, candidates in (
        ('phone_number', ('phone_number', 'phone', 'whatsapp', 'mobile', 'tel', 'number')),
        ('name', ('name', 'full_name', 'customer_name', 'contact_name')),
        ('email', ('email', 'email_address', 'mail')),
        ('lifecycle_status', ('lifecycle_status', 'lifecycle_stage', 'stage', 'status')),
        ('tags', ('tags', 'tag', 'labels', 'segment')),
    ):
        for cand in candidates:
            if cand in lowered:
                mapping[target] = lowered[cand]
                break
    return mapping


def _plan_csv_import(tenant, headers, rows, mapping, extra):
    existing_phones = set(Customer.objects.filter(tenant=tenant).values_list('phone_number', flat=True))
    seen_in_file = set()
    preview_rows = []
    valid_records = []
    invalid_count = 0
    duplicate_existing_count = 0
    duplicate_file_count = 0

    default_stage = str(extra.get('default_lifecycle') or ContactLifecycleStatus.LEAD).strip().upper()
    if default_stage not in ContactLifecycleStatus.values:
        default_stage = ContactLifecycleStatus.LEAD
    raw_default_tags = extra.get('default_tags') or []
    if isinstance(raw_default_tags, str):
        default_tags = [t.strip() for t in raw_default_tags.split(',') if t.strip()]
    elif isinstance(raw_default_tags, list):
        default_tags = [str(t).strip() for t in raw_default_tags if str(t).strip()]
    else:
        default_tags = []

    mapped_cols = set(mapping.values())
    custom_cols = [h for h in headers if h not in mapped_cols][:20]

    for row_num, row in enumerate(rows, start=2):
        phone = _normalize_e164(row.get(mapping.get('phone_number', ''), ''))
        name = row.get(mapping.get('name', ''), '').strip()[:150]
        email = row.get(mapping.get('email', ''), '').strip()[:254]
        stage = row.get(mapping.get('lifecycle_status', ''), '').strip().upper() or default_stage
        if stage not in ContactLifecycleStatus.values:
            stage = default_stage
        raw_tags = row.get(mapping.get('tags', ''), '')
        row_tags = list(dict.fromkeys([t.strip()[:40] for t in raw_tags.replace(';', ',').split(',') if t.strip()] + default_tags))[:20]
        custom_fields = {col[:50]: str(row[col])[:250] for col in custom_cols if row.get(col)}

        status_flag = 'READY'
        if not phone:
            status_flag = 'INVALID_PHONE'
            invalid_count += 1
        elif phone in seen_in_file:
            status_flag = 'DUPLICATE_IN_FILE'
            duplicate_file_count += 1
        elif phone in existing_phones:
            status_flag = 'EXISTING_CONTACT'
            duplicate_existing_count += 1
            seen_in_file.add(phone)
        else:
            seen_in_file.add(phone)

        rec = {
            'row': row_num,
            'phone_number': phone or row.get(mapping.get('phone_number', ''), ''),
            'name': name,
            'email': email,
            'lifecycle_status': stage,
            'tags': row_tags,
            'custom_fields': custom_fields,
            'status': status_flag,
        }
        if len(preview_rows) < 15:
            preview_rows.append(rec)
        if status_flag in ('READY', 'EXISTING_CONTACT'):
            valid_records.append(rec)

    return {
        'headers': headers,
        'mapping': mapping,
        'custom_columns': custom_cols,
        'total_rows': len(rows),
        'valid_new_count': sum(1 for r in valid_records if r['status'] == 'READY'),
        'existing_count': duplicate_existing_count,
        'duplicate_in_file_count': duplicate_file_count,
        'invalid_count': invalid_count,
        'quota_remaining': max(0, tenant.effective_max_contacts - tenant.active_contacts_count),
        'preview_rows': preview_rows,
        '_valid_records': valid_records,
    }


@api_login_required
@require_POST
def crm_contacts_import_preview_api(request):
    """Validate CSV rows and show column mapping + quota impact without writing contacts."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'contacts', 'create')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)
    try:
        headers, rows, extra = _parse_csv_payload(request)
        raw_map = extra.get('column_mapping')
        if isinstance(raw_map, str) and raw_map.strip():
            raw_map = json.loads(raw_map)
        mapping = _infer_column_mapping(headers, raw_map if isinstance(raw_map, dict) else None)
        plan = _plan_csv_import(tenant, headers, rows, mapping, extra)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    plan.pop('_valid_records', None)
    return JsonResponse(plan)


@api_login_required
@require_POST
@transaction.atomic
def crm_contacts_import_api(request):
    """Transactionally import validated contacts from CSV without auto-granting marketing consent."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'contacts', 'create')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    try:
        headers, rows, extra = _parse_csv_payload(request)
        raw_map = extra.get('column_mapping')
        if isinstance(raw_map, str) and raw_map.strip():
            raw_map = json.loads(raw_map)
        mapping = _infer_column_mapping(headers, raw_map if isinstance(raw_map, dict) else None)
        if 'phone_number' not in mapping:
            raise ValueError('Map a CSV column to phone_number before importing.')
        duplicate_strategy = str(extra.get('duplicate_strategy') or 'skip').lower()
        if duplicate_strategy not in ('skip', 'update'):
            duplicate_strategy = 'skip'
        plan = _plan_csv_import(tenant, headers, rows, mapping, extra)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    new_count = plan['valid_new_count']
    quota_remaining = max(0, tenant.effective_max_contacts - tenant.active_contacts_count)
    if new_count > quota_remaining:
        return JsonResponse({
            'error': f'Import would add {new_count} new contacts, exceeding remaining plan quota ({quota_remaining}).',
            'quota_remaining': quota_remaining,
        }, status=400)

    created_count = 0
    updated_count = 0
    skipped_count = plan['invalid_count'] + plan['duplicate_in_file_count']

    for rec in plan['_valid_records']:
        if rec['status'] == 'EXISTING_CONTACT':
            if duplicate_strategy != 'update':
                skipped_count += 1
                continue
            contact = Customer.objects.select_for_update().filter(tenant=tenant, phone_number=rec['phone_number']).first()
            if contact:
                if rec['name'] and not contact.name:
                    contact.name = rec['name']
                if rec['email'] and not contact.email:
                    contact.email = rec['email']
                merged_tags = list(dict.fromkeys(list(contact.tags or []) + rec['tags']))[:30]
                merged_custom = {**(contact.custom_fields or {}), **rec['custom_fields']}
                contact.tags = merged_tags
                contact.custom_fields = merged_custom
                contact.save(update_fields=['name', 'email', 'tags', 'custom_fields', 'updated_at'])
                updated_count += 1
        else:
            Customer.objects.create(
                tenant=tenant,
                phone_number=rec['phone_number'],
                name=rec['name'] or f"Contact {rec['phone_number'][-4:]}",
                email=rec['email'],
                lifecycle_status=rec['lifecycle_status'],
                source=ContactSource.IMPORT,
                tags=rec['tags'],
                custom_fields=rec['custom_fields'],
                owner=request.user,
            )
            created_count += 1

    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.CONTACTS_IMPORTED,
        summary=f"Imported {created_count} contacts ({updated_count} updated, {skipped_count} skipped) from CSV",
        details={'created': created_count, 'updated': updated_count, 'skipped': skipped_count},
    )

    return JsonResponse({
        'status': 'imported',
        'created_count': created_count,
        'updated_count': updated_count,
        'skipped_count': skipped_count,
    }, status=201)
