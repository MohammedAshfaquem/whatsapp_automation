from rest_framework import serializers
from .models import Booking
from apps.services.serializers import ServiceSerializer

class BookingSerializer(serializers.ModelSerializer):
    service_details = ServiceSerializer(source='service', read_only=True)
    customer_phone = serializers.CharField(source='customer.phone_number', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    def update(self, instance, validated_data):
        from django.db import transaction
        from .notifications import change_booking_status
        with transaction.atomic():
            target = validated_data.pop('status', instance.status)
            try:
                instance = change_booking_status(instance, target, validated_data.get('owner_notes'))
            except ValueError as error:
                raise serializers.ValidationError({'status': str(error)})
            return super().update(instance, validated_data)

    class Meta:
        model = Booking
        fields = [
            'id',
            'customer',
            'customer_phone',
            'customer_name',
            'recipient_name',
            'conversation',
            'service',
            'service_details',
            'ac_type',
            'ac_brand',
            'problem_description',
            'service_address',
            'preferred_date',
            'preferred_time_slot',
            'status',
            'owner_notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class BookingActionSerializer(serializers.Serializer):
    owner_notes = serializers.CharField(required=False, allow_blank=True)
