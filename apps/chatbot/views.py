from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser

from .models import ChannelChoice
from .serializers import SimulatedChatRequestSerializer, SimulatedChatResponseSerializer

from drf_spectacular.utils import extend_schema, OpenApiExample

from .conversation_service import ConversationService
from .processing import ConversationBusyError

class SimulatedChatView(APIView):
    """
    Simulated chat endpoint allowing Postman, Swagger UI, and test scripts to interact with the bot
    without needing Meta WhatsApp credentials.
    """
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=['Chatbot Simulation'],
        summary='Send message in simulated chat session',
        description='Simulate a customer WhatsApp message. Interacts with active PostgreSQL services and business data.',
        request=SimulatedChatRequestSerializer,
        responses={200: SimulatedChatResponseSerializer},
        examples=[
            OpenApiExample(
                'Service Price Enquiry',
                value={
                    'phone_number': '+919876543210',
                    'message': 'What are your AC service prices?'
                },
                request_only=True
            ),
            OpenApiExample(
                'Specific Gas Service Enquiry',
                value={
                    'phone_number': '+919876543210',
                    'message': 'How much is AC gas filling?'
                },
                request_only=True
            ),
            OpenApiExample(
                'Working Hours Enquiry',
                value={
                    'phone_number': '+919876543210',
                    'message': 'What are your working hours?'
                },
                request_only=True
            ),
            OpenApiExample(
                'Coverage Areas Enquiry',
                value={
                    'phone_number': '+919876543210',
                    'message': 'Which areas do you serve?'
                },
                request_only=True
            ),
            OpenApiExample(
                'Booking Request',
                value={
                    'phone_number': '+919876543210',
                    'message': 'I want to book AC servicing'
                },
                request_only=True
            )
        ]
    )
    def post(self, request):
        serializer = SimulatedChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone_number = serializer.validated_data['phone_number']
        user_message = serializer.validated_data['message']

        try:
            result = ConversationService.process_message(
                phone_number=phone_number,
                message_text=user_message,
                channel=ChannelChoice.SIMULATED
            )
        except ConversationBusyError:
            return Response({'error': 'Your previous message is still being processed. Please try again shortly.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(result, status=status.HTTP_200_OK)
