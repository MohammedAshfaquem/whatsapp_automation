import hmac
import hashlib
import json
import pytest
from unittest.mock import patch
from apps.whatsapp.models import WhatsAppConfig, WhatsAppWebhookLog
from apps.whatsapp.webhook_service import WebhookService
from apps.whatsapp.whatsapp_client import WhatsAppClient
from apps.chatbot.models import Message, Conversation, Customer, ConversationStatus
from apps.services.models import Service, PriceType
from apps.business.models import BusinessProfile

@pytest.fixture(autouse=True)
def setup_whatsapp_test_data(db):
    WhatsAppConfig.objects.all().delete()
    WhatsAppWebhookLog.objects.all().delete()
    BusinessProfile.objects.all().delete()
    Service.objects.all().delete()

    BusinessProfile.objects.create(
        shop_name="CoolAir Tech",
        contact_phone="+91 98765 43210",
        address="Delhi",
        is_active=True
    )

    Service.objects.create(
        name="AC general servicing",
        price_type=PriceType.STARTING_FROM,
        price_amount=500.00,
        is_active=True
    )

    WhatsAppConfig.objects.create(
        is_enabled=True,
        phone_number_id="123456789012345",
        business_account_id="987654321098765",
        verify_token="my_secret_verify_token_123",
        access_token="EAABdummyaccesstoken",
        app_secret="test_meta_app_secret_abc123"
    )

@pytest.mark.django_db
class TestWhatsAppWebhookVerification:
    def test_webhook_challenge_success(self, client):
        url = "/api/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=my_secret_verify_token_123&hub.challenge=1158201444"
        response = client.get(url)
        assert response.status_code == 200
        assert response.content.decode('utf-8') == "1158201444"

    def test_webhook_challenge_invalid_token(self, client):
        url = "/api/whatsapp/webhook/?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=1158201444"
        response = client.get(url)
        assert response.status_code == 403
        assert "Verification failed" in response.content.decode('utf-8')

@pytest.mark.django_db
class TestWhatsAppSignatureVerification:
    def test_valid_hmac_signature(self):
        payload = b'{"test": "data"}'
        secret = "test_meta_app_secret_abc123"
        computed_hash = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        sig_header = f"sha256={computed_hash}"

        assert WebhookService.verify_signature(payload, sig_header) is True

    def test_invalid_hmac_signature(self):
        payload = b'{"test": "data"}'
        sig_header = "sha256=invalid_hash_value_1234567890"
        assert WebhookService.verify_signature(payload, sig_header) is False

@pytest.mark.django_db
class TestWhatsAppInboundMessageProcessing:
    @patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_interactive_options')
    def test_receive_inbound_text_message(self, mock_send, client):
        mock_send.return_value = (True, "wamid.outbound.123")

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "1234567890",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "phone_number_id": "123456789012345"
                        },
                        "messages": [{
                            "from": "919876543210",
                            "id": "wamid.HBgLMTIzNDU2Nzg5MA==",
                            "timestamp": "1710000000",
                            "text": {"body": "What services do you provide?"},
                            "type": "text"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }

        body_bytes = json.dumps(payload).encode('utf-8')
        secret = "test_meta_app_secret_abc123"
        sig = "sha256=" + hmac.new(secret.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()

        response = client.post(
            "/api/whatsapp/webhook/",
            data=payload,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=sig
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "EVENT_PROCESSED"
        assert data["processed"] == 1

        # Outbound WhatsApp interactive message was triggered
        assert mock_send.called
        call_args = mock_send.call_args[1]
        assert call_args["recipient_phone"] == "+919876543210"
        assert "Which service are you interested in?" in call_args["body_text"]
        assert len(call_args["options"]) > 0

        # Logged in WhatsAppWebhookLog
        log_entry = WhatsAppWebhookLog.objects.filter(whatsapp_message_id="wamid.HBgLMTIzNDU2Nzg5MA==").first()
        assert log_entry is not None
        assert log_entry.is_processed is True

    @patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_interactive_options')
    def test_receive_inbound_interactive_button_reply(self, mock_send, client):
        mock_send.return_value = (True, "wamid.outbound.btn456")

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "1234567890",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "phone_number_id": "123456789012345"
                        },
                        "messages": [{
                            "from": "919876543210",
                            "id": "wamid.interactive.btn.1",
                            "timestamp": "1710000000",
                            "type": "interactive",
                            "interactive": {
                                "type": "button_reply",
                                "button_reply": {
                                    "id": "check_price_1",
                                    "title": "Check Price"
                                }
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }

        body_bytes = json.dumps(payload).encode('utf-8')
        secret = "test_meta_app_secret_abc123"
        sig = "sha256=" + hmac.new(secret.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()

        response = client.post(
            "/api/whatsapp/webhook/",
            data=payload,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=sig
        )

        assert response.status_code == 200
        assert mock_send.called
        call_args = mock_send.call_args[1]
        assert "₹" in call_args["body_text"]

    @patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_text_message')
    def test_inbound_message_deduplication(self, mock_send, client):
        mock_send.return_value = (True, "wamid.outbound.123")
        wamid = "wamid.dedup.12345"

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "1",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "messages": [{
                            "from": "919876543210",
                            "id": wamid,
                            "timestamp": "1710000000",
                            "text": {"body": "Hello"},
                            "type": "text"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }

        body_bytes = json.dumps(payload).encode('utf-8')
        secret = "test_meta_app_secret_abc123"
        sig = "sha256=" + hmac.new(secret.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()

        # First request
        res1 = client.post("/api/whatsapp/webhook/", data=payload, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)
        assert res1.status_code == 200

        # Second identical request (duplicate webhook delivery from Meta)
        res2 = client.post("/api/whatsapp/webhook/", data=payload, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)
        assert res2.status_code == 200

        # Inbound message saved only once
        assert Message.objects.filter(external_message_id=wamid).count() == 1

@pytest.mark.django_db
class TestWhatsAppClientSimulationMode:
    def test_client_safe_simulation_when_disabled(self):
        # Disable WhatsApp
        WhatsAppConfig.objects.all().update(is_enabled=False)

        ok, msg_id = WhatsAppClient.send_text_message(
            recipient_phone="+919876543210",
            message_text="Test simulation"
        )
        assert ok is True
        assert "simulated" in msg_id
