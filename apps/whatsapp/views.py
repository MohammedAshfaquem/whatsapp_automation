import json
import logging
from django.http import HttpResponse, JsonResponse
from django.db import DatabaseError
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from .webhook_service import WebhookService

logger = logging.getLogger(__name__)

class WhatsAppWebhookView(APIView):
    """
    Official Meta WhatsApp Cloud API Webhook endpoint:
    - GET: Meta verification challenge when registering webhook.
    - POST: Receive inbound customer WhatsApp messages & delivery events.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Meta WhatsApp Cloud API'],
        summary='Meta Webhook Verification Challenge',
        description='Meta sends a GET request with hub.challenge, hub.mode, and hub.verify_token to verify webhook ownership.',
        parameters=[
            OpenApiParameter('hub.mode', str, description='Mode (subscribe)', required=True),
            OpenApiParameter('hub.verify_token', str, description='Verification secret token configured in Meta App', required=True),
            OpenApiParameter('hub.challenge', str, description='Random challenge string to echo back', required=True),
        ],
        responses={200: str, 403: str}
    )
    def get(self, request):
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        is_valid, response_str = WebhookService.verify_challenge(mode, token, challenge)
        if is_valid:
            return HttpResponse(response_str, content_type='text/plain', status=200)

        return HttpResponse(response_str, content_type='text/plain', status=403)

    @extend_schema(
        tags=['Meta WhatsApp Cloud API'],
        summary='Inbound WhatsApp Webhook Event',
        description='Receives inbound customer messages from Meta Cloud API. Validates HMAC SHA-256 signature if configured.',
        request={'application/json': dict},
        responses={200: dict, 403: dict},
        examples=[
            OpenApiExample(
                'Meta Inbound Text Message Payload',
                value={
                    "object": "whatsapp_business_account",
                    "entry": [{
                        "id": "1234567890",
                        "changes": [{
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15550254589",
                                    "phone_number_id": "100654321098765"
                                },
                                "contacts": [{
                                    "profile": {"name": "Customer User"},
                                    "wa_id": "919876543210"
                                }],
                                "messages": [{
                                    "from": "919876543210",
                                    "id": "wamid.HBgLMTIzNDU2Nzg5MA==",
                                    "timestamp": "1710000000",
                                    "text": {"body": "I want to repair my AC"},
                                    "type": "text"
                                }]
                            },
                            "field": "messages"
                        }]
                    }]
                },
                request_only=True
            )
        ]
    )
    def post(self, request):
        # 1. HMAC SHA-256 signature verification
        signature_header = request.headers.get("X-Hub-Signature-256")
        if not WebhookService.verify_signature(request.body, signature_header):
            return JsonResponse({'error': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)

        # 2. Parse and process payload
        payload = request.data
        if not isinstance(payload, dict):
            try:
                payload = json.loads(request.body.decode('utf-8'))
            except Exception:
                payload = {}

        try:
            result = WebhookService.process_incoming_payload(payload)
        except DatabaseError:
            logger.exception('Webhook database operation failed; provider should retry')
            result = {'status': 'RETRY_REQUIRED', 'failures': 1}
        response = JsonResponse(result, status=503 if result.get('failures') else 200)
        if result.get('failures'):
            response['Retry-After'] = '2'
        return response
