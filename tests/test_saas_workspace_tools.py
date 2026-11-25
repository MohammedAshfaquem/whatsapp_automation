import json
from datetime import timedelta
from unittest.mock import patch, MagicMock
import pytest
from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from django.utils import timezone
from apps.tenants.models import (Tenant,TenantMembership,TenantSubscription,PlanTier,
    SavedReply,ManualBillingEntry,PlatformServiceConfig,TransactionalEmail,AccountActivationToken)
from apps.tenants.saas_api import workspace_tools,platform_tools
from apps.tenants.email_service import seal,unseal,queue_activation,send_email_job,process_emails

pytestmark=pytest.mark.django_db

@pytest.fixture
def state():
    owner=User.objects.create_user('tools_owner',email='owner@example.com',password='StrongPassword987!')
    staff=User.objects.create_user('tools_staff',email='staff@example.com')
    admin=User.objects.create_superuser('tools_admin',email='admin@example.com',password='StrongPassword987!')
    tenant=Tenant.objects.create(name='Tools Client',slug='tools-client')
    plan=PlanTier.objects.create(code='tools',name='Tools',enabled_modules=['shared_inbox'])
    TenantSubscription.objects.create(tenant=tenant,effective_plan=plan,status='ACTIVE')
    for user,role in [(owner,'OWNER'),(staff,'STAFF')]:TenantMembership.objects.create(tenant=tenant,user=user,role=role)
    return owner,staff,admin,tenant

def call(state,resource,method='get',data=None,platform=False,user=None):
    owner,staff,admin,tenant=state
    request=getattr(RequestFactory(),method)('/api/test/',data=json.dumps(data or {}) if method!='get' else {},content_type='application/json')
    request.user=user or (admin if platform else owner);request.tenant=tenant
    return (platform_tools if platform else workspace_tools)(request,resource)

def test_saved_reply_uses_real_tenant_permissions_and_unique_titles(state):
    assert call(state,'replies','post',{'title':'Welcome','body':'Hello there'}).status_code==201
    assert call(state,'replies','post',{'title':'Welcome','body':'Duplicate'}).status_code==409
    assert call(state,'replies','post',{'title':'Staff','body':'No'},user=state[1]).status_code==403
    other=Tenant.objects.create(name='Other Tools',slug='other-tools')
    secret=SavedReply.objects.create(tenant=other,title='Private',body='Other client')
    assert len(json.loads(call(state,'replies').content)['results'])==1
    call(state,'replies','delete',{'id':secret.pk});assert SavedReply.objects.filter(pk=secret.pk).exists()

def test_platform_is_separate_and_delivery_owner_only(state):
    assert call(state,'smtp',platform=True,user=state[0]).status_code==403
    assert call(state,'deliveries',user=state[1]).status_code==403
    assert call(state,'subscription',user=state[1]).status_code==403

def test_manual_payment_dedup_and_renewal_do_not_activate_suspended(state):
    sub=TenantSubscription.objects.get(tenant=state[3]);sub.status='SUSPENDED';sub.save()
    data={'tenant_id':state[3].pk,'amount':'1200.00','reference':'PAY-1','received_on':str(timezone.localdate()),'renew_until':str(timezone.localdate()+timedelta(days=30))}
    assert call(state,'billing','post',data,platform=True).status_code==201
    assert call(state,'billing','post',data,platform=True).status_code==409
    sub.refresh_from_db();assert sub.status=='SUSPENDED' and ManualBillingEntry.objects.count()==1
    data['reference']='PAY-2';data['renew_until']=str(timezone.localdate()+timedelta(days=10))
    assert call(state,'billing','post',data,platform=True).status_code==400
    assert ManualBillingEntry.objects.count()==1

def test_smtp_never_returns_password_and_rejects_private_host(state):
    data={'enabled':True,'host':'smtp.example.com','port':587,'security':'TLS','username':'smtp-user','password':'smtp-secret','from_email':'sender@example.com'}
    with patch('apps.tenants.saas_api.validate_smtp_host'):
        result=call(state,'smtp','post',data,platform=True)
    assert result.status_code==200 and b'smtp-secret' not in result.content
    config=PlatformServiceConfig.objects.get();assert 'smtp-secret' not in config.encrypted_secrets and unseal(config.encrypted_secrets)['smtp_password']=='smtp-secret'
    data['host']='localhost'
    assert call(state,'smtp','post',data,platform=True).status_code==400

def test_email_queue_disabled_encrypted_deduplicated_and_stale_recipient(state):
    token=AccountActivationToken.create_for_user(state[0]);request=RequestFactory().get('/')
    job=queue_activation(request,token,state[3]);again=queue_activation(request,token,state[3])
    assert job.pk==again.pk and token.token not in job.encrypted_payload and process_emails()==0
    PlatformServiceConfig.objects.create(smtp_enabled=True,smtp_host='smtp.example.com',smtp_from_email='sender@example.com')
    state[0].email='changed@example.com';state[0].save()
    with patch('apps.tenants.email_service.get_connection') as connect:
        assert not send_email_job(job.pk);connect.assert_not_called()
    job.refresh_from_db();assert job.status=='EXPIRED'

def test_unknown_email_is_never_retried_and_acceptance_is_not_delivery(state):
    PlatformServiceConfig.objects.create(smtp_enabled=True,smtp_host='smtp.example.com',smtp_from_email='sender@example.com')
    token=AccountActivationToken.create_for_user(state[0]);job=queue_activation(RequestFactory().get('/'),token)
    with patch('apps.tenants.email_service.validate_smtp_host'),patch('apps.tenants.email_service.EmailMessage.send',side_effect=TimeoutError):
        assert not send_email_job(job.pk)
    job.refresh_from_db();assert job.status=='UNKNOWN' and not send_email_job(job.pk)
    assert call(state,'emails','post',{'id':str(job.pk)},platform=True).status_code==409
    job.status='PENDING';job.save()
    with patch('apps.tenants.email_service.validate_smtp_host'),patch('apps.tenants.email_service.EmailMessage.send',return_value=1):assert send_email_job(job.pk)
    job.refresh_from_db();assert job.status=='ACCEPTED'

def test_public_recovery_generic_response_csrf_and_rate_limit(state):
    client=Client(enforce_csrf_checks=True)
    assert client.post('/password-reset/',{'email':state[0].email}).status_code==403
    first=client.get('/password-reset/');assert first.status_code==200 and b'workspace-navigation' not in first.content
    csrf=client.cookies['csrftoken'].value
    for email in [state[0].email]*4+['unknown@example.com']:
        assert client.post('/password-reset/',{'email':email,'csrfmiddlewaretoken':csrf}).status_code==302
    assert TransactionalEmail.objects.filter(purpose='RECOVERY').count()==3

def test_recovery_real_django_token_resets_password_once(state):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    owner=state[0];token=default_token_generator.make_token(owner)
    url=f'/password-reset/confirm/{urlsafe_base64_encode(force_bytes(owner.pk))}/{token}/'
    c=Client();r=c.get(url);assert r.status_code==302
    assert c.get(r.url).status_code==200
    assert c.post(r.url,{'new_password1':'DifferentStrongPassword987!','new_password2':'DifferentStrongPassword987!'}).status_code==302
    owner.refresh_from_db();assert owner.check_password('DifferentStrongPassword987!') and not default_token_generator.check_token(owner,token)
