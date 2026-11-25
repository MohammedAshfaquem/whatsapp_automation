import json
import hmac
import hashlib
from datetime import timedelta
import pytest
from django.utils import timezone
from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.tenants.models import Tenant, TenantMembership, TenantInvitation, TenantAuditLog, MembershipRole, TenantPlan
from apps.tenants.context import set_current_tenant, get_current_tenant, user_can_manage_tenant
from apps.services.models import Service, PriceType
from apps.services.services import get_active_services
from apps.business.models import BusinessProfile, Product
from apps.business.services import get_business_summary
from apps.chatbot.models import Customer, Conversation, Message, ChannelChoice, ConversationStatus, MessageDirection
from apps.bookings.models import Booking, BookingStatus
from apps.knowledge_base.models import FAQ, KnowledgeDocument
from apps.knowledge_base.retrieval import retrieve_relevant_knowledge
from apps.whatsapp.models import WhatsAppConfig, WhatsAppDelivery
from apps.whatsapp.webhook_service import (
    resolve_tenant_from_payload,
    verify_signature,
    verify_challenge
)
from apps.whatsapp.delivery import dispatch


@pytest.fixture
def tenant_a(db):
    t = Tenant.objects.create(name="Alpha Corp", slug="alpha-corp", plan=TenantPlan.PRO, is_active=True)
    BusinessProfile.objects.create(
        tenant=t,
        shop_name="Alpha Corp Solutions",
        contact_phone="+91 99999 11111",
        is_active=True
    )
    return t


@pytest.fixture
def tenant_b(db):
    t = Tenant.objects.create(name="Beta Retail", slug="beta-retail", plan=TenantPlan.STARTER, is_active=True)
    BusinessProfile.objects.create(
        tenant=t,
        shop_name="Beta Retail Store",
        contact_phone="+91 99999 22222",
        is_active=True
    )
    return t


@pytest.fixture
def user_alpha_owner(db, tenant_a):
    user = User.objects.create_user(username="alpha_owner", password="password123", email="owner@alpha.com", is_staff=True)
    TenantMembership.objects.create(tenant=tenant_a, user=user, role=MembershipRole.OWNER, is_active=True)
    return user


@pytest.fixture
def user_alpha_staff(db, tenant_a):
    user = User.objects.create_user(username="alpha_staff", password="password123", email="staff@alpha.com", is_staff=True)
    TenantMembership.objects.create(tenant=tenant_a, user=user, role=MembershipRole.STAFF, is_active=True)
    return user


@pytest.fixture
def user_superadmin(db):
    return User.objects.create_superuser(username="platformadmin", password="password123", email="admin@platform.com")


@pytest.mark.django_db
class TestTenantCreationAndMembership:
    def test_membership_roles_and_permissions(self, tenant_a, user_alpha_owner, user_alpha_staff, user_superadmin):
        assert user_can_manage_tenant(user_alpha_owner, tenant_a) is True
        assert user_can_manage_tenant(user_alpha_staff, tenant_a) is False
        assert user_can_manage_tenant(user_superadmin, tenant_a) is True

    def test_single_use_expiring_invitation(self, tenant_a, user_alpha_owner):
        # 1. Create valid invitation
        inv = TenantInvitation.create_invitation(
            tenant=tenant_a,
            email="newhire@alpha.com",
            role=MembershipRole.STAFF,
            invited_by=user_alpha_owner,
            valid_days=3
        )
        assert inv.is_expired is False
        assert inv.is_accepted is False

        # 2. Accept invitation
        new_user = User.objects.create_user(username="newhire", password="password123", email="newhire@alpha.com")
        membership = inv.accept(new_user)
        assert membership is not None
        assert membership.role == MembershipRole.STAFF
        assert membership.tenant == tenant_a
        assert inv.is_accepted is True

        # 3. Cannot accept again
        with pytest.raises(ValueError, match="already been accepted"):
            inv.accept(new_user)

        # 4. Expired invitation cannot be accepted
        expired_inv = TenantInvitation.create_invitation(
            tenant=tenant_a,
            email="expired@alpha.com",
            role=MembershipRole.ADMIN,
            invited_by=user_alpha_owner,
            valid_days=-1
        )
        assert expired_inv.is_expired is True
        with pytest.raises(ValueError, match="has expired"):
            expired_inv.accept(new_user)


@pytest.mark.django_db
class TestMultiTenantDataIsolation:
    def test_service_and_customer_tenant_scoping(self, tenant_a, tenant_b):
        # Both tenants create a service with the same slug/name without database collision
        svc_a = Service.objects.create(
            tenant=tenant_a,
            name="Consulting",
            slug="consulting",
            price_type=PriceType.FIXED,
            price_amount=5000,
            is_active=True
        )
        svc_b = Service.objects.create(
            tenant=tenant_b,
            name="Consulting",
            slug="consulting",
            price_type=PriceType.FIXED,
            price_amount=3000,
            is_active=True
        )

        active_a = get_active_services(tenant=tenant_a)
        active_b = get_active_services(tenant=tenant_b)

        assert active_a.count() == 1
        assert active_a.first().price_amount == 5000
        assert active_b.count() == 1
        assert active_b.first().price_amount == 3000

        # Both tenants have a customer with the same phone number
        cust_a = Customer.objects.create(tenant=tenant_a, phone_number="+919876543210", name="Customer In Alpha")
        cust_b = Customer.objects.create(tenant=tenant_b, phone_number="+919876543210", name="Customer In Beta")

        assert Customer.objects.filter(tenant=tenant_a).count() == 1
        assert Customer.objects.filter(tenant=tenant_b).count() == 1
        assert Customer.objects.get(tenant=tenant_a, phone_number="+919876543210").name == "Customer In Alpha"
        assert Customer.objects.get(tenant=tenant_b, phone_number="+919876543210").name == "Customer In Beta"

    def test_business_profile_and_products_isolation(self, tenant_a, tenant_b):
        prod_a = Product.objects.create(
            tenant=tenant_a,
            name="TABLO",
            slug="tablo",
            tagline="TABLO for Alpha",
            is_active=True
        )
        prod_b = Product.objects.create(
            tenant=tenant_b,
            name="TABLO",
            slug="tablo",
            tagline="TABLO for Beta",
            is_active=True
        )

        assert Product.objects.filter(tenant=tenant_a, slug="tablo").first().tagline == "TABLO for Alpha"
        assert Product.objects.filter(tenant=tenant_b, slug="tablo").first().tagline == "TABLO for Beta"

        summary_a = get_business_summary(tenant=tenant_a)
        assert "Alpha Corp Solutions" in summary_a

        summary_b = get_business_summary(tenant=tenant_b)
        assert "Beta Retail Store" in summary_b

    def test_bookings_and_conversations_isolation(self, tenant_a, tenant_b):
        cust_a = Customer.objects.create(tenant=tenant_a, phone_number="+919999911111", name="Alpha Client")
        cust_b = Customer.objects.create(tenant=tenant_b, phone_number="+919999922222", name="Beta Client")

        conv_a = Conversation.objects.create(tenant=tenant_a, customer=cust_a, channel=ChannelChoice.WHATSAPP)
        conv_b = Conversation.objects.create(tenant=tenant_b, customer=cust_b, channel=ChannelChoice.WHATSAPP)

        book_a = Booking.objects.create(tenant=tenant_a, customer=cust_a, conversation=conv_a, status=BookingStatus.PENDING)
        book_b = Booking.objects.create(tenant=tenant_b, customer=cust_b, conversation=conv_b, status=BookingStatus.PENDING)

        assert Booking.objects.filter(tenant=tenant_a).count() == 1
        assert Booking.objects.filter(tenant=tenant_a).first() == book_a
        assert Booking.objects.filter(tenant=tenant_b).count() == 1
        assert Booking.objects.filter(tenant=tenant_b).first() == book_b


@pytest.mark.django_db
class TestWhatsAppWebhookMultiTenant:
    def test_resolve_tenant_and_verify_signature(self, tenant_a, tenant_b):
        # Configure WhatsApp for both tenants
        cfg_a = WhatsAppConfig.objects.create(
            tenant=tenant_a,
            phone_number_id="111111111",
            business_account_id="waba_a",
            app_secret="secret_key_alpha",
            verify_token="token_alpha",
            access_token="access_alpha"
        )
        cfg_b = WhatsAppConfig.objects.create(
            tenant=tenant_b,
            phone_number_id="222222222",
            business_account_id="waba_b",
            app_secret="secret_key_beta",
            verify_token="token_beta",
            access_token="access_beta"
        )

        payload_a = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {
                            "phone_number_id": "111111111"
                        }
                    }
                }]
            }]
        }
        resolved_tenant = resolve_tenant_from_payload(payload_a)
        assert resolved_tenant == tenant_a

        # Signature verification: must match tenant A's app secret
        raw_body = json.dumps(payload_a).encode('utf-8')
        sig_a = "sha256=" + hmac.new(b"secret_key_alpha", raw_body, hashlib.sha256).hexdigest()
        sig_b = "sha256=" + hmac.new(b"secret_key_beta", raw_body, hashlib.sha256).hexdigest()

        assert verify_signature(raw_body, sig_a, tenant=tenant_a) is True
        assert verify_signature(raw_body, sig_b, tenant=tenant_a) is False

    def test_suspended_tenant_rejected_at_webhook(self, tenant_a):
        tenant_a.is_active = False
        tenant_a.save()

        cfg_a = WhatsAppConfig.objects.create(
            tenant=tenant_a,
            phone_number_id="111111111",
            app_secret="secret_key_alpha",
            verify_token="token_alpha"
        )

        client = Client()
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "111111111"}}}]}]
        }
        raw_body = json.dumps(payload).encode('utf-8')
        sig = "sha256=" + hmac.new(b"secret_key_alpha", raw_body, hashlib.sha256).hexdigest()

        res = client.post(
            reverse('whatsapp-webhook'),
            data=raw_body,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=sig
        )
        # Suspended tenant must be rejected with 403 Forbidden
        assert res.status_code == 403

    def test_suspended_tenant_blocks_delivery_dispatch(self, tenant_a):
        tenant_a.is_active = False
        tenant_a.save()

        delivery = WhatsAppDelivery.objects.create(
            tenant=tenant_a,
            dedup_key="test_blocked_1",
            recipient_phone="+919999900000",
            payload={"text": "Hello"}
        )

        success = dispatch(delivery.pk)
        assert success is False
        delivery.refresh_from_db()
        assert delivery.status == "BLOCKED"
        assert "Tenant suspended" in delivery.last_error


@pytest.mark.django_db
class TestDashboardViewsAndAccess:
    def test_tenant_switching_and_isolation(self, client, tenant_a, tenant_b, user_alpha_owner, user_superadmin):
        # 1. Login as Alpha owner
        client.force_login(user_alpha_owner)
        res = client.get(reverse('dashboard'))
        assert res.status_code == 302
        assert res.url == '/app/dashboard'
        bootstrap = client.get(reverse('api-bootstrap'))
        assert bootstrap.status_code == 200
        assert bootstrap.json()['tenant']['id'] == tenant_a.id

        # Alpha owner cannot switch to Beta
        res = client.post(reverse('switch-tenant'), {'tenant_id': tenant_b.id})
        assert res.status_code == 302
        res = client.get(reverse('dashboard'))
        # Active workspace remains Alpha
        assert res.status_code == 302
        assert res.url == '/app/dashboard'
        assert client.get(reverse('api-bootstrap')).json()['tenant']['id'] == tenant_a.id

        # 2. Login as Superadmin
        client.force_login(user_superadmin)
        res = client.post(reverse('switch-tenant'), {'tenant_id': tenant_b.id})
        assert res.status_code == 302
        res = client.get(reverse('dashboard'))
        assert res.status_code == 302
        assert res.url == '/app/dashboard'
        assert client.get(reverse('api-bootstrap')).json()['tenant']['id'] == tenant_b.id

    def test_platform_admin_tenant_management(self, client, user_superadmin, user_alpha_owner):
        # Staff cannot toggle tenant status
        client.force_login(user_alpha_owner)
        res = client.post(reverse('platform-tenant-toggle', kwargs={'tenant_id': user_alpha_owner.tenant_memberships.first().tenant.id}))
        assert res.status_code == 403

        # Superadmin can toggle tenant status
        client.force_login(user_superadmin)
        tenant = user_alpha_owner.tenant_memberships.first().tenant
        assert tenant.is_active is True
        res = client.post(reverse('platform-tenant-toggle', kwargs={'tenant_id': tenant.id}))
        assert res.status_code == 302
        tenant.refresh_from_db()
        assert tenant.is_active is False

