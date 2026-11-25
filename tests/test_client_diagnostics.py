import json
import pytest
from django.contrib.auth.models import User
from apps.tenants.models import Tenant,TenantMembership
from apps.whatsapp.models import WhatsAppDelivery

@pytest.mark.django_db
def test_client_diagnostics_cannot_read_other_clients_or_global_records(client):
    u=User.objects.create_user('diag_owner',is_staff=True)
    t=Tenant.objects.create(name='Own diagnostics',slug='own-diag')
    other=Tenant.objects.create(name='Other diagnostics',slug='other-diag')
    TenantMembership.objects.create(user=u,tenant=t,role='OWNER')
    own=WhatsAppDelivery.objects.create(tenant=t,dedup_key='own-diag',recipient_phone='123',status='FAILED',last_error='access_token=secret-test')
    foreign=WhatsAppDelivery.objects.create(tenant=other,dedup_key='other-diag',recipient_phone='456')
    client.force_login(u)
    r=client.get('/api/client/operations/deliveries/')
    assert r.status_code==200 and r.json()['total']==1
    assert client.get(f'/api/client/operations/deliveries/{foreign.pk}/').status_code==404
    detail=client.get(f'/api/client/operations/deliveries/{own.pk}/')
    assert detail.status_code==200 and 'secret-test' not in detail.content.decode()
    assert client.get('/api/client/operations/users/').status_code==404

@pytest.mark.django_db
def test_super_admin_does_not_offer_global_whatsapp_or_business_operations(client):
    user=User.objects.create_superuser('diag_root','r@example.com','test')
    client.force_login(user)
    for resource in ('deliveries','webhooks','contacts','conversations','bookings','services','products','templates','configurations'):
        assert client.get('/api/platform/operations/'+resource+'/').status_code==403
    assert client.get('/api/platform/operations/users/').status_code==200
