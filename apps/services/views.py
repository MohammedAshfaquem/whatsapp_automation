from rest_framework import generics
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
from .models import Service
from .serializers import ServiceSerializer

@extend_schema(tags=['AC Services'], summary='List all active AC services')
class ServiceListView(generics.ListAPIView):
    """List all active AC services with pricing information."""
    queryset = Service.objects.filter(is_active=True).order_by('id')
    serializer_class = ServiceSerializer
    permission_classes = [AllowAny]

@extend_schema(tags=['AC Services'], summary='Retrieve single AC service details')
class ServiceDetailView(generics.RetrieveAPIView):
    """Retrieve details for a single active AC service."""
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [AllowAny]
