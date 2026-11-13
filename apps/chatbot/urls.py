from django.urls import path
from .views import SimulatedChatView

urlpatterns = [
    path('test/', SimulatedChatView.as_view(), name='chat-test'),
]
