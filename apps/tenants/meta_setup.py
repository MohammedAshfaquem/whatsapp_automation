"""Authoritative client Meta onboarding state and read-only provider verification."""
import re
import requests
from django.utils import timezone
from apps.tenants.models import TenantSubscription
from apps.whatsapp.models import WhatsAppConfig
from apps.whatsapp.whatsapp_client import WhatsAppClient


def normalize_phone(value):
    return '+' + re.sub(r'\D', '', value or '')


def valid_whatsapp_number(value):
    return isinstance(value, str) and bool(re.fullmatch(r'\+[1-9]\d{7,14}', value))


def meta_setup_state(tenant):
    config = WhatsAppConfig.objects.filter(tenant=tenant).first() if tenant else None
    subscription = TenantSubscription.objects.filter(tenant=tenant).first() if tenant else None
    required = bool(tenant and tenant.requires_meta_setup)
    reason = ''
    if not config or not all((config.phone_number_id, config.business_account_id, config.access_token, config.verify_token, config.app_id, config.app_secret)):
        reason = 'Configure your Meta WhatsApp credentials.'
    elif not config.is_enabled:
        reason = 'Enable your Meta WhatsApp connection.'
    elif not subscription or subscription.status != 'ACTIVE' or subscription.start_date > timezone.localdate() or (subscription.end_date and subscription.end_date < timezone.localdate()):
        reason = 'An active subscription is required.'
    elif not config.connection_verified_at:
        reason = 'Verify your Meta WhatsApp connection.'
    elif tenant.whatsapp_number and normalize_phone(config.verified_display_phone_number) != tenant.whatsapp_number:
        reason = 'The Meta number must match your assigned WhatsApp number.'
    return {'required': required, 'ready': not bool(reason), 'reason': reason, 'expected_number': tenant.whatsapp_number if tenant else '', 'display_phone_number': config.verified_display_phone_number if config else ''}


def verify_meta_connection(tenant, config):
    config.refresh_from_db()
    fingerprint = {field: getattr(config, field) for field in (
        'phone_number_id', 'business_account_id', 'access_token', 'verify_token',
        'app_id', 'app_secret', 'is_enabled',
    )}
    expected_number = tenant.whatsapp_number
    config.connection_verified_at = None
    config.verified_display_phone_number = ''
    config.save(update_fields=['connection_verified_at', 'verified_display_phone_number'])
    if not all((config.phone_number_id.isdigit(), config.business_account_id.isdigit(), config.access_token, config.verify_token, config.app_id, config.app_secret, config.is_enabled)):
        raise ValueError('Complete and enable your Meta configuration before verification.')
    subscription = TenantSubscription.objects.filter(tenant=tenant).first()
    if not subscription or subscription.status != 'ACTIVE' or subscription.start_date > timezone.localdate() or (subscription.end_date and subscription.end_date < timezone.localdate()):
        raise ValueError('An active subscription is required.')
    base = f'{WhatsAppClient.GRAPH_API_BASE_URL}/{WhatsAppClient.GRAPH_API_VERSION}'
    headers = {'Authorization': f'Bearer {config.access_token}'}
    def get(url, params):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15, allow_redirects=False)
            if response.status_code != 200:
                raise ValueError('Meta could not verify these credentials. Check your token and account permissions.')
            try:
                body = response.json()
            except ValueError as exc:
                raise ValueError('Meta returned an invalid verification response.') from exc
            if not isinstance(body, dict) or body.get('error'):
                raise ValueError('Meta returned an invalid verification response.')
            return body
        except (requests.RequestException, TypeError, KeyError) as exc:
            raise ValueError('Meta verification is unavailable. Please retry.') from exc
    phone = get(f'{base}/{config.phone_number_id}', {'fields': 'id,display_phone_number,verified_name'})
    if str(phone.get('id', '')) != config.phone_number_id or not phone.get('display_phone_number'):
        raise ValueError('Meta returned a different or incomplete phone number.')
    if tenant.whatsapp_number and normalize_phone(phone['display_phone_number']) != tenant.whatsapp_number:
        raise ValueError('The Meta phone number does not match your assigned WhatsApp number.')
    cursor = None
    seen = set()
    belongs = False
    for _ in range(100):
        params = {'fields': 'id', 'limit': 100}
        if cursor: params['after'] = cursor
        page = get(f'{base}/{config.business_account_id}/phone_numbers', params)
        rows = page.get('data')
        if not isinstance(rows, list):
            raise ValueError('Meta returned an invalid WhatsApp Business Account response.')
        if any(str(row.get('id', '')) == config.phone_number_id for row in rows if isinstance(row, dict)):
            belongs = True
            break
        paging = page.get('paging') or {}
        cursor = (paging.get('cursors') or {}).get('after')
        if not paging.get('next') or not cursor or cursor in seen: break
        seen.add(cursor)
    if not belongs:
        raise ValueError('This phone number does not belong to the configured WhatsApp Business Account.')
    config.connection_verified_at = timezone.now()
    config.verified_display_phone_number = phone['display_phone_number']
    # Commit only to the exact credential set and assigned number verified above.
    # A concurrent credential update may complete while Graph requests are running.
    changed = WhatsAppConfig.objects.filter(
        pk=config.pk, tenant=tenant, tenant__whatsapp_number=expected_number, **fingerprint,
    ).update(connection_verified_at=config.connection_verified_at,
             verified_display_phone_number=config.verified_display_phone_number)
    if not changed:
        config.refresh_from_db()
        raise ValueError('Meta credentials or assigned number changed during verification. Please retry.')
    return meta_setup_state(tenant)
