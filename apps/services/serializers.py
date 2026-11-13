from rest_framework import serializers
from .models import Service

class ServiceSerializer(serializers.ModelSerializer):
    formatted_price = serializers.ReadOnlyField()

    class Meta:
        model = Service
        fields = [
            'id',
            'name',
            'slug',
            'category',
            'description',
            'price_type',
            'price_amount',
            'max_price',
            'currency',
            'formatted_price',
            'estimated_duration',
            'is_active',
            'created_at',
            'updated_at'
        ]
