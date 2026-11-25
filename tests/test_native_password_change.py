import json
import pytest
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth import login
from apps.tenants import account_api

@pytest.mark.django_db
@pytest.mark.parametrize('kind', ['wrong', 'mismatch', 'weak', 'valid', 'nonstring', 'oversized'])
def test_native_password_change(kind):
    user = get_user_model().objects.create_user('password_user', password='Original!Pass90210')
    payload = {'current_password': 'Original!Pass90210', 'new_password': 'Replacement!Pass78341', 'new_password_confirmation': 'Replacement!Pass78341'}
    if kind == 'wrong': payload['current_password'] = 'wrong'
    if kind == 'mismatch': payload['new_password_confirmation'] = 'Different!Pass78341'
    if kind == 'weak': payload.update(new_password='123', new_password_confirmation='123')
    if kind == 'nonstring': payload['new_password'] = ['Replacement!Pass78341']
    if kind == 'oversized': payload['current_password'] = 'x' * 1025
    request = RequestFactory().post('/api/auth/password/', data=json.dumps(payload), content_type='application/json')
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request.user = user
    login(request, user)
    response = account_api.account_password_api(request)
    assert response.status_code == (200 if kind == 'valid' else 400)
    user.refresh_from_db()
    assert user.check_password('Replacement!Pass78341' if kind == 'valid' else 'Original!Pass90210')
    if kind == 'valid':
        assert request.session['_auth_user_hash'] == user.get_session_auth_hash()
        from apps.tenants.models import TenantAuditLog
        audit = TenantAuditLog.objects.filter(actor=user).latest('pk')
        assert 'Original!Pass90210' not in str(audit.details)
        assert 'Replacement!Pass78341' not in str(audit.details)


@pytest.mark.django_db
def test_password_change_requires_login_and_post():
    from django.contrib.auth.models import AnonymousUser
    factory = RequestFactory()
    anonymous_request = factory.post('/api/auth/password/')
    anonymous_request.user = AnonymousUser()
    assert account_api.account_password_api(anonymous_request).status_code == 302
    request = factory.get('/api/auth/password/')
    request.user = get_user_model().objects.create_user('method_user')
    assert account_api.account_password_api(request).status_code == 405


@pytest.mark.django_db
def test_password_change_keeps_default_csrf_protection():
    from django.middleware.csrf import CsrfViewMiddleware
    request = RequestFactory().post('/api/auth/password/', data='{}', content_type='application/json')
    request.user = get_user_model().objects.create_user('csrf_user')
    rejection = CsrfViewMiddleware(lambda r: None).process_view(request, account_api.account_password_api, (), {})
    assert rejection.status_code == 403
