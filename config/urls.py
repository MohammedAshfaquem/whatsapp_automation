"""URL Configuration for ac_whatsapp_agent."""
from django.contrib import admin
from django.urls import path, include
from .health import health_check
from apps.tenants.spa_view import spa_app_view
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
    path('api/', include('apps.tenants.spa_urls')),
    path('api/services/', include('apps.services.urls')),
    path('api/chat/', include('apps.chatbot.urls')),
    path('api/bookings/', include('apps.bookings.urls')),
    path('api/whatsapp/', include('apps.whatsapp.urls')),

    # React SPA
    path('app/', spa_app_view, name='spa-app-root'),
    path('app/<path:path>', spa_app_view, name='spa-app'),

    # CRM Module
    path('crm/', include('apps.crm.urls')),

    # Tenant Auth & Onboarding
    path('', include('apps.tenants.urls')),

    # Frontend Management Dashboard & RBAC
    path('', include('apps.dashboard.urls')),

    # Public Marketing Website
    path('', include('apps.marketing.urls')),
]

admin.site.site_header = "Neoriz WhatsApp Automation Administration"
admin.site.site_title = "Neoriz WhatsApp Automation"
admin.site.index_title = "Platform & Tenant Workspace Management"
