"""URL Configuration for ac_whatsapp_agent."""
from django.contrib import admin
from django.urls import path, include
from .health import health_check
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path('health/', health_check, name='health'),
    path('admin/', admin.site.urls),

    # Swagger / OpenAPI Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui-alias'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # API endpoints
    path('api/services/', include('apps.services.urls')),
    path('api/chat/', include('apps.chatbot.urls')),
    path('api/bookings/', include('apps.bookings.urls')),
    path('api/whatsapp/', include('apps.whatsapp.urls')),

    # Frontend Management Dashboard & RBAC
    path('', include('apps.dashboard.urls')),
]

admin.site.site_header = "AC Service Shop Administration"
admin.site.site_title = "AC Service Admin Portal"
admin.site.index_title = "Welcome to AC Service Automation Portal"
