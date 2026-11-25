"""Replace tenant template metadata only from a complete provider snapshot."""
import re
from django.utils import timezone
from django.db import transaction
from apps.crm.models import WhatsAppTemplate
from apps.tenants.models import Tenant
from .whatsapp_client import WhatsAppClient


def validate_snapshot(items):
    if not isinstance(items, list):
        raise ValueError('Invalid template snapshot')
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Invalid template record')
        name, language = item.get('name'), item.get('language')
        if (not isinstance(name, str) or not re.fullmatch(r'[a-z0-9_]{1,100}', name)
                or not isinstance(language, str) or not re.fullmatch(r'[a-z]{2,3}(?:_[A-Z]{2})?', language)):
            raise ValueError('Invalid template name or language')
        key = (name, language)
        if key in seen:
            raise ValueError('Duplicate template identity in snapshot')
        seen.add(key)
        if not isinstance(item.get('components'), list) or not all(isinstance(c, dict) and isinstance(c.get('type'), str) for c in item['components']):
            raise ValueError('Invalid template components')
        if 'status' in item and (not isinstance(item['status'], str) or not item['status'] or len(item['status']) > 20):
            raise ValueError('Invalid template status')
        if 'category' in item and item['category'] not in ('UTILITY', 'MARKETING', 'AUTHENTICATION'):
            raise ValueError('Invalid template category')
    return seen


def sync_templates(tenant):
    """Return (success, safe_error); failed fetches leave all local rows unchanged."""
    if tenant is None or not tenant.pk:
        return False, 'Tenant is required'
    try:
        with transaction.atomic():
            # Lock a stable parent even for tenants with no template rows. Keeping
            # fetch within this lock prevents older snapshots overwriting newer ones.
            Tenant.objects.select_for_update().get(pk=tenant.pk)
            ok, items, error = WhatsAppClient.fetch_templates(tenant=tenant)
            if not ok:
                return False, error or 'Template fetch failed'
            seen = validate_snapshot(items)
            for item in items:
                components = item['components']
                body = components[0].get('text') if len(components) == 1 and components[0]['type'] == 'BODY' else None
                supported = isinstance(body, str) and bool(body.strip())
                placeholders = re.findall(r'\{\{(\d+)\}\}', body or '') if isinstance(body, str) else []
                positions = sorted(set(map(int, placeholders)))
                if supported:
                    remainder = re.sub(r'\{\{\d+\}\}', '', body)
                    supported = ('{{' not in remainder and '}}' not in remainder
                                 and positions == list(range(1, len(positions) + 1))
                                 and all(str(int(p)) == p for p in placeholders))
                status = item.get('status', 'UNKNOWN')
                if status == 'APPROVED' and not supported:
                    status = 'UNSUPPORTED'
                WhatsAppTemplate.objects.update_or_create(
                    tenant=tenant, name=item['name'], language=item['language'],
                    defaults={'category': item.get('category', 'UTILITY'),
                              'body_text': body if isinstance(body, str) else '',
                              'variables': [f'Variable {p}' for p in positions] if supported else [],
                              'meta_status': status, 'meta_id': str(item.get('id', ''))[:100],
                              'last_synced_at': timezone.now(), 'submission_error': ''})
            for local in WhatsAppTemplate.objects.filter(tenant=tenant, meta_status='APPROVED'):
                if (local.name, local.language) not in seen:
                    local.meta_status = 'UNKNOWN'
                    local.save(update_fields=['meta_status'])
        return True, ''
    except ValueError:
        return False, 'Invalid or incomplete template snapshot'
