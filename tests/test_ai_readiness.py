from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User

from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.models import Customer, Conversation, ConversationStatus
from apps.tenants.models import Tenant, TenantMembership, MembershipRole

pytestmark = pytest.mark.django_db


def test_connection_check_requires_staff(client):
    client.force_login(User.objects.create_user('customer'))
    with patch.object(GeminiChatService, 'generate_reply') as generate:
        response = client.post('/chatbot/connection/test/')
    assert response.status_code == 403
    generate.assert_not_called()


def test_staff_dashboard_routes_to_spa_with_connection_and_handover_access(client):
    staff = User.objects.create_user('staff', is_staff=True)
    tenant = Tenant.objects.create(name='Support workspace', slug='support-workspace')
    TenantMembership.objects.create(user=staff, tenant=tenant, role=MembershipRole.STAFF)
    client.force_login(staff)
    response = client.get('/')
    assert response.status_code == 302
    assert response.url == '/app/dashboard'
    bootstrap = client.get('/api/auth/bootstrap/')
    assert bootstrap.status_code == 200
    assert bootstrap.json()['user']['id'] == staff.id
    tenant_id = (bootstrap.json()['tenant'] or {}).get('id')
    customer = Customer.objects.create(tenant_id=tenant_id, phone_number='+919999000001')
    conversation = Conversation.objects.create(
        tenant_id=tenant_id, customer=customer, status=ConversationStatus.HUMAN_HANDOVER,
    )
    queue = client.get('/api/inbox/conversations/?tab=human')
    assert queue.status_code == 200
    assert [item['id'] for item in queue.json()['conversations']] == [conversation.id]
    assert queue.json()['conversations'][0]['handover_required'] is True
    claim = client.post(f'/conversations/{conversation.id}/action/', {'action': 'claim'})
    assert claim.status_code == 200
    conversation.refresh_from_db()
    assert conversation.assigned_staff_id == staff.id
    assert conversation.status == ConversationStatus.HUMAN_HANDOVER
    connection = client.post('/chatbot/connection/test/')
    assert connection.status_code == 200
    assert 'status' in connection.json()


def test_staff_check_reports_invalid_credentials_without_disclosing_error(client, settings):
    from apps.chatbot.ai_status import get_ai_status
    client.force_login(User.objects.create_user('operator', is_staff=True))
    settings.GEMINI_API_KEY = 'AIzaSy-secret-test'
    provider = MagicMock()
    error = RuntimeError('API key not valid: AIzaSy-secret-test')
    error.code = 400
    provider.models.generate_content.side_effect = error
    with patch.object(GeminiChatService, '_get_client', return_value=provider):
        response = client.post('/chatbot/connection/test/')
    assert response.status_code == 200
    assert response.json()['status'] == 'INVALID_CREDENTIALS'
    assert 'secret-test' not in response.content.decode()
    assert get_ai_status()['status'] == 'INVALID_CREDENTIALS'


def test_success_and_configuration_changes_do_not_reuse_stale_readiness(settings):
    from apps.chatbot.ai_status import get_ai_status
    settings.GEMINI_API_KEY = 'AIzaSy-test-one'
    provider = MagicMock()
    provider.models.generate_content.return_value = SimpleNamespace(text='OK')
    with patch.object(GeminiChatService, '_get_client', return_value=provider):
        assert GeminiChatService.generate_reply('Connection test') == 'OK'
    assert get_ai_status()['status'] == 'READY'
    settings.GEMINI_API_KEY = 'AIzaSy-test-two'
    assert get_ai_status()['status'] == 'UNTESTED'
    settings.GEMINI_API_KEY = ''
    assert get_ai_status()['status'] == 'NOT_CONFIGURED'


def test_unavailable_and_empty_results_are_not_ready(settings):
    from apps.chatbot.ai_status import get_ai_status
    settings.GEMINI_API_KEY = 'AIzaSy-test'
    provider = MagicMock()
    provider.models.generate_content.side_effect = TimeoutError('private provider details')
    with patch.object(GeminiChatService, '_get_client', return_value=provider):
        assert GeminiChatService.generate_reply('Test') is None
    assert get_ai_status()['status'] == 'UNAVAILABLE'
    provider.models.generate_content.side_effect = None
    provider.models.generate_content.return_value = SimpleNamespace(text='')
    with patch.object(GeminiChatService, '_get_client', return_value=provider):
        assert GeminiChatService.generate_reply('Test') is None
    assert get_ai_status()['status'] == 'EMPTY_RESPONSE'
