import importlib
from unittest.mock import patch
import httpx
import pytest
from apps.whatsapp.whatsapp_client import WhatsAppClient
from apps.crm.models import WhatsAppTemplate
from apps.tenants.models import Tenant


def item(name='booking', language='en', **extra):
    return dict(name=name, language=language, status='APPROVED', category='UTILITY', components=[{'type': 'BODY', 'text': 'Hi {{1}}'}], **extra)


def fetch(pages):
    responses = iter(pages)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=next(responses)))
    real_client = httpx.Client
    with patch('apps.whatsapp.whatsapp_client.WhatsAppConfig.get_settings', return_value={'enabled': True, 'business_account_id': '123', 'access_token': 'secret'}), patch('apps.whatsapp.whatsapp_client.httpx.Client', side_effect=lambda **kw: real_client(transport=transport, **kw)):
        return WhatsAppClient.fetch_templates()


def test_fetch_collects_every_page():
    first = [item(name=f'template_{i}') for i in range(100)]
    ok, templates, error = fetch([{'data': first, 'paging': {'next': 'https://graph.facebook.com/v21.0/123/message_templates?after=next'}}, {'data': [item('last')]}])
    assert ok and not error
    assert len(templates) == 101


@pytest.mark.parametrize('page', [{}, {'data': None}, {'data': [{}]}, {'data': [], 'paging': {'next': 'https://evil.test/steal'}}])
def test_fetch_rejects_incomplete_or_unsafe_snapshot(page):
    ok, templates, error = fetch([page])
    assert not ok and templates == [] and error


@pytest.mark.django_db
def test_sync_reconciles_exact_languages_and_missing_status():
    sync_templates = importlib.import_module('apps.whatsapp.template_sync').sync_templates
    tenant = Tenant.objects.create(name='Sync tenant', slug='sync-tenant')
    old = WhatsAppTemplate.objects.create(tenant=tenant, name='booking', language='fr', body_text='Old', meta_status='APPROVED')
    remote = item()
    del remote['status']
    with patch.object(WhatsAppClient, 'fetch_templates', return_value=(True, [remote], '')):
        assert sync_templates(tenant) == (True, '')
    old.refresh_from_db()
    assert old.meta_status == 'UNKNOWN'
    assert WhatsAppTemplate.objects.get(tenant=tenant, name='booking', language='en').meta_status == 'UNKNOWN'


@pytest.mark.django_db
@pytest.mark.parametrize('snapshot', [None, [item(), {}]])
def test_failed_snapshot_does_not_revoke_approved_templates(snapshot):
    sync_templates = importlib.import_module('apps.whatsapp.template_sync').sync_templates
    tenant = Tenant.objects.create(name='Sync tenant', slug='sync-tenant')
    old = WhatsAppTemplate.objects.create(tenant=tenant, name='old', body_text='Old', meta_status='APPROVED')
    result = (False, [], 'Incomplete response') if snapshot is None else (True, snapshot, '')
    with patch.object(WhatsAppClient, 'fetch_templates', return_value=result):
        assert sync_templates(tenant)[0] is False
    old.refresh_from_db()
    assert old.meta_status == 'APPROVED'
    assert tenant.whatsapp_templates.count() == 1


@pytest.mark.django_db
def test_components_not_supported_by_sender_cannot_be_approved():
    sync_templates = importlib.import_module('apps.whatsapp.template_sync').sync_templates
    tenant = Tenant.objects.create(name='Sync tenant', slug='sync-tenant')
    remote = item()
    remote['components'].insert(0, {'type': 'HEADER', 'format': 'IMAGE'})
    with patch.object(WhatsAppClient, 'fetch_templates', return_value=(True, [remote], '')):
        assert sync_templates(tenant) == (True, '')
    assert tenant.whatsapp_templates.get().meta_status == 'UNSUPPORTED'

@pytest.mark.parametrize('last_page', [{}, {'data': [], 'paging': {'next': 'https://graph.facebook.com/v21.0/123/message_templates?after=next'}}])
def test_invalid_later_page_discards_collected_templates(last_page):
    ok, templates, error = fetch([{'data': [item()], 'paging': {'next': 'https://graph.facebook.com/v21.0/123/message_templates?after=next'}}, last_page])
    assert not ok and templates == [] and error


@pytest.mark.django_db
def test_successful_empty_snapshot_revokes_only_this_tenants_approvals():
    sync_templates = importlib.import_module('apps.whatsapp.template_sync').sync_templates
    tenant = Tenant.objects.create(name='Sync tenant', slug='sync-tenant')
    other = Tenant.objects.create(name='Other tenant', slug='other-tenant')
    old = WhatsAppTemplate.objects.create(tenant=tenant, name='old', body_text='Old', meta_status='APPROVED')
    unrelated = WhatsAppTemplate.objects.create(tenant=other, name='old', body_text='Old', meta_status='APPROVED')
    with patch.object(WhatsAppClient, 'fetch_templates', return_value=(True, [], '')):
        assert sync_templates(tenant) == (True, '')
    old.refresh_from_db()
    unrelated.refresh_from_db()
    assert old.meta_status == 'UNKNOWN'
    assert unrelated.meta_status == 'APPROVED'
