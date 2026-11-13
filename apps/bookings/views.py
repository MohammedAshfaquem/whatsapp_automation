from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from drf_spectacular.utils import extend_schema
from .models import Booking, BookingStatus
from .serializers import BookingSerializer, BookingActionSerializer
from .notifications import change_booking_status

@extend_schema(tags=['Bookings'])
class BookingListCreateView(generics.ListCreateAPIView):
    """
    List all bookings (paginated, for authorized shop owner / staff).
    """
    queryset = Booking.objects.all().select_related('customer', 'service').order_by('-created_at')
    serializer_class = BookingSerializer
    permission_classes = [IsAdminUser]

@extend_schema(tags=['Bookings'])
class BookingDetailView(generics.RetrieveUpdateAPIView):
    """
    Retrieve and update a single booking (staff only).
    """
    queryset = Booking.objects.all().select_related('customer', 'service')
    serializer_class = BookingSerializer
    permission_classes = [IsAdminUser]

@extend_schema(
    tags=['Bookings'],
    summary='Confirm pending booking',
    request=BookingActionSerializer,
    responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}, 'status': {'type': 'string'}, 'owner_notes': {'type': 'string'}}}}
)
class BookingConfirmView(APIView):
    """
    Authorize shop owner to confirm a pending booking.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            booking = Booking.objects.get(pk=pk)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = BookingActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            booking = change_booking_status(booking, BookingStatus.CONFIRMED, serializer.validated_data.get('owner_notes'))
        except ValueError as error:
            return Response({'error': str(error)}, status=400)

        return Response({
            "message": f"Booking #{booking.id} successfully confirmed.",
            "status": booking.status,
            "owner_notes": booking.owner_notes
        }, status=status.HTTP_200_OK)

@extend_schema(
    tags=['Bookings'],
    summary='Reject pending booking',
    request=BookingActionSerializer,
    responses={200: {'type': 'object', 'properties': {'message': {'type': 'string'}, 'status': {'type': 'string'}, 'owner_notes': {'type': 'string'}}}}
)
class BookingRejectView(APIView):
    """
    Authorize shop owner to reject a booking request.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            booking = Booking.objects.get(pk=pk)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = BookingActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            booking = change_booking_status(booking, BookingStatus.REJECTED, serializer.validated_data.get('owner_notes'))
        except ValueError as error:
            return Response({'error': str(error)}, status=400)

        return Response({
            "message": f"Booking #{booking.id} rejected.",
            "status": booking.status,
            "owner_notes": booking.owner_notes
        }, status=status.HTTP_200_OK)
