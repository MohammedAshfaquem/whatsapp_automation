from rest_framework import serializers
from .models import Customer, Conversation, Message

class SimulatedChatRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=30)
    message = serializers.CharField(max_length=2000)

class SimulatedChatResponseSerializer(serializers.Serializer):
    conversation_id = serializers.IntegerField()
    reply = serializers.CharField()
    handover_required = serializers.BooleanField(default=False)
    booking_id = serializers.IntegerField(allow_null=True, required=False)
    interactive = serializers.DictField(allow_null=True, required=False)
    options = serializers.ListField(allow_null=True, required=False)

class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'direction', 'sender_type', 'message_text', 'created_at']

class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    customer_phone = serializers.CharField(source='customer.phone_number', read_only=True)

    class Meta:
        model = Conversation
        fields = ['id', 'customer', 'customer_phone', 'channel', 'status', 'last_message_at', 'messages']
