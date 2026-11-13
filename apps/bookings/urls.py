from django.urls import path
from .views import (
    BookingListCreateView,
    BookingDetailView,
    BookingConfirmView,
    BookingRejectView,
)

urlpatterns = [
    path('', BookingListCreateView.as_view(), name='booking-list-create'),
    path('<int:pk>/', BookingDetailView.as_view(), name='booking-detail'),
    path('<int:pk>/confirm/', BookingConfirmView.as_view(), name='booking-confirm'),
    path('<int:pk>/reject/', BookingRejectView.as_view(), name='booking-reject'),
]
