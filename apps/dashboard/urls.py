from django.urls import path
from . import views

urlpatterns = [
    path('chatbot/connection/test/', views.ai_connection_test_api, name='ai-connection-test'),
    path('', views.dashboard_view, name='dashboard'),
    path('dashboard/', views.dashboard_view, name='dashboard-alias'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('services/create/', views.service_create_view, name='service-create'),
    path('services/<int:service_id>/toggle/', views.service_toggle_view, name='service-toggle'),
    path('customers/create/', views.customer_create_view, name='customer-create'),
    path('customers/<int:customer_id>/tag/', views.customer_tag_service_view, name='customer-tag'),
    path('bookings/<int:booking_id>/action/', views.booking_action_view, name='booking-action'),
    path('users/create/', views.user_create_view, name='user-create'),
    path('conversations/<int:conversation_id>/messages/', views.conversation_messages_api, name='conversation-messages'),
    path('conversations/<int:conversation_id>/action/', views.conversation_action_api, name='conversation-action'),
    path('chat/send/', views.chat_send_api, name='chat-send-api'),
]
