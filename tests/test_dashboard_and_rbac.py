import json
import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.contrib.messages import get_messages
from apps.services.models import Service, PriceType
from apps.chatbot.models import Customer, Conversation, Message, MessageDirection, SenderType
from apps.bookings.models import Booking, BookingStatus

@pytest.mark.django_db
class TestDashboardAuthAndRBAC:
    """Tests authentication, Role-Based Access Control, customer tagging and live chat in Frontend Dashboard."""

    def test_unauthenticated_user_redirected_to_login(self, client):
        response = client.get(reverse('dashboard'))
        assert response.status_code == 302
        assert '/login/' in response.url

    def test_login_flow_success_and_logout(self, client):
        user = User.objects.create_user(username='teststaff', password='staffpassword123', is_staff=True)
        login_res = client.post(reverse('login'), {
            'username': 'teststaff',
            'password': 'staffpassword123'
        }, follow=True)
        assert login_res.status_code == 200
        assert b"Welcome back, teststaff" in login_res.content

        # Logout
        logout_res = client.get(reverse('logout'), follow=True)
        assert logout_res.status_code == 200
        assert b"logged out" in logout_res.content

    def test_superadmin_can_view_and_create_staff_users(self, client):
        admin_user = User.objects.create_superuser(username='superadmin', password='adminpass123', email='admin@test.com')
        client.login(username='superadmin', password='adminpass123')

        # Visit dashboard
        res = client.get(reverse('dashboard'))
        assert res.status_code == 302
        assert res.url == '/app/platform/dashboard'
        bootstrap = client.get(reverse('api-bootstrap'))
        assert bootstrap.status_code == 200
        assert bootstrap.json()['is_super_admin'] is True
        assert bootstrap.json()['user']['id'] == admin_user.id

        # Superadmin creates a new staff user
        post_data = {
            'username': 'newtechnician',
            'password': 'techpassword123',
            'first_name': 'Alex',
            'last_name': 'Technician',
            'email': 'alex@example.com',
            'role': 'staff'
        }
        create_res = client.post(reverse('user-create'), post_data, follow=True)
        assert create_res.status_code == 200
        assert User.objects.filter(username='newtechnician').exists()
        created = User.objects.get(username='newtechnician')
        assert created.is_staff is True
        assert created.is_superuser is False

    def test_staff_user_cannot_create_other_users_rbac_enforcement(self, client):
        staff_user = User.objects.create_user(username='regularstaff', password='staffpassword123', is_staff=True)
        client.login(username='regularstaff', password='staffpassword123')

        # Visit dashboard - team tab should NOT be visible to regular staff
        res = client.get(reverse('dashboard'))
        assert res.status_code == 302
        assert res.url == '/app/dashboard'
        bootstrap = client.get(reverse('api-bootstrap'))
        assert bootstrap.status_code == 200
        assert bootstrap.json()['is_super_admin'] is False
        assert bootstrap.json()['user']['id'] == staff_user.id

        # Direct POST attempt to user-create must be denied
        create_res = client.post(reverse('user-create'), {
            'username': 'unauthorized_user',
            'password': 'password123',
            'role': 'staff'
        }, follow=True)
        assert not User.objects.filter(username='unauthorized_user').exists()
        assert any("Permission denied: Only superadministrators can create new staff accounts" in str(message)
                   for message in get_messages(create_res.wsgi_request))

    def test_staff_user_can_add_new_service_with_contact_number(self, client):
        staff_user = User.objects.create_user(username='staff2', password='staffpass123', is_staff=True)
        client.login(username='staff2', password='staffpass123')

        # Add new service via frontend form
        service_data = {
            'name': 'Anti-Bacterial Foam Cleaning',
            'category': 'Specialty Maintenance',
            'price_type': PriceType.FIXED,
            'price_amount': '899.00',
            'currency': 'INR',
            'estimated_duration': '60 mins',
            'contact_number': '+91 91234 56789',
            'description': 'Deep sanitization with foam spray',
            'is_active': 'on'
        }
        res = client.post(reverse('service-create'), service_data, follow=True)
        assert res.status_code == 200
        assert Service.objects.filter(name='Anti-Bacterial Foam Cleaning').exists()

        svc = Service.objects.get(name='Anti-Bacterial Foam Cleaning')
        assert svc.is_active is True
        assert svc.contact_number == '+91 91234 56789'

        # Toggle inactive
        toggle_res = client.post(reverse('service-toggle', args=[svc.id]), follow=True)
        assert toggle_res.status_code == 200
        svc.refresh_from_db()
        assert svc.is_active is False

    def test_staff_can_register_customer_and_tag_services(self, client):
        staff = User.objects.create_user(username='staff3', password='pass123', is_staff=True)
        client.login(username='staff3', password='pass123')

        svc1 = Service.objects.create(name='AC Filter Wash', price_amount=499, contact_number='+91 98765 00001')
        svc2 = Service.objects.create(name='PCB Board Repair', price_amount=1500, contact_number='+91 98765 00002')

        post_data = {
            'name': 'Chloe Wilson',
            'phone_number': '+919876543211',
            'email': 'chloe@example.com',
            'portal_password': 'customerpass123',
            'tagged_services': [svc1.id]
        }
        res = client.post(reverse('customer-create'), post_data, follow=True)
        assert res.status_code == 200

        customer = Customer.objects.get(phone_number='+919876543211')
        assert customer.name == 'Chloe Wilson'
        assert customer.user is not None
        assert customer.assigned_services.count() == 1
        assert customer.assigned_services.first() == svc1

        # Test updating tagged services
        tag_res = client.post(reverse('customer-tag', args=[customer.id]), {
            'service_ids': [svc1.id, svc2.id]
        }, follow=True)
        assert tag_res.status_code == 200
        assert customer.assigned_services.count() == 2

    def test_customer_portal_shows_only_tagged_services(self, client):
        # Create 2 services
        svc1 = Service.objects.create(name='Gas Leak Fix', price_amount=799, contact_number='+91 98765 11111')
        svc2 = Service.objects.create(name='Compressor Replacement', price_amount=4500, contact_number='+91 98765 22222')

        # Create customer user
        customer_user = User.objects.create_user(username='+919876543212', password='custpassword')
        customer = Customer.objects.create(user=customer_user, name='Marcus Reed', phone_number='+919876543212')
        customer.assigned_services.add(svc1)  # Only tag svc1

        # Log in as customer
        client.login(username='+919876543212', password='custpassword')
        res = client.get(reverse('dashboard'))
        assert res.status_code == 200
        assert b"Marcus Reed" in res.content
        assert b"Gas Leak Fix" in res.content
        assert b"+91 98765 11111" in res.content
        # Untagged service should NOT be shown
        assert b"Compressor Replacement" not in res.content

    def test_customer_chat_api_scoped_to_service_contact_number(self, client):
        svc = Service.objects.create(
            name='Jet Pump Deep Cleaning',
            price_amount=699,
            contact_number='+91 98765 33333',
            description='Complete indoor and outdoor unit jet wash'
        )
        customer_user = User.objects.create_user(username='+919876543213', password='custpassword')
        customer = Customer.objects.create(user=customer_user, name='Bessie Cooper', phone_number='+919876543213')
        customer.assigned_services.add(svc)

        client.login(username='+919876543213', password='custpassword')

        # Send chat message under this service
        chat_payload = {
            'message_text': 'What is the price of this service?',
            'service_id': svc.id
        }
        res = client.post(
            reverse('chat-send-api'),
            data=json.dumps(chat_payload),
            content_type='application/json'
        )
        assert res.status_code == 200
        data = res.json()
        assert 'reply' in data
        # Verification that the bot specifically quoted the price and helpline
        assert 'Jet Pump Deep Cleaning' in data['reply']
        assert '699' in data['reply']

    def test_staff_can_view_whatsapp_chats_and_manage_bookings(self, client):
        staff = User.objects.create_user(username='staff4', password='pass123', is_staff=True)
        client.login(username='staff4', password='pass123')

        customer = Customer.objects.create(name='Priya', phone_number='+919876543299')
        conv = Conversation.objects.create(customer=customer)
        Message.objects.create(
            conversation=conv,
            direction=MessageDirection.INBOUND,
            sender_type=SenderType.CUSTOMER,
            message_text="Need AC repair for water leak"
        )
        Message.objects.create(
            conversation=conv,
            direction=MessageDirection.OUTBOUND,
            sender_type=SenderType.BOT,
            message_text="We can help! Standard repair starts from Rs. 499."
        )

        # Test message transcript API
        api_res = client.get(reverse('conversation-messages', args=[conv.id]))
        assert api_res.status_code == 200
        json_data = api_res.json()
        assert len(json_data['messages']) == 2
        assert json_data['messages'][0]['text'] == "Need AC repair for water leak"
        assert json_data['customer_phone'] == "+919876543299"

        # Create booking and test confirm action
        booking = Booking.objects.create(
            customer=customer,
            service_address="Flat 202, Sunshine Apts",
            status=BookingStatus.PENDING
        )
        action_res = client.post(
            reverse('booking-action', args=[booking.id]),
            {'action': 'confirm'},
            follow=True
        )
        assert action_res.status_code == 200
        booking.refresh_from_db()
        assert booking.status == BookingStatus.CONFIRMED
