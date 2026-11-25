from . import recovery_views
from django.views.generic import TemplateView
from django.urls import path
from . import signup_views
from . import onboarding_views
from . import platform_views

urlpatterns = [
    path('password-reset/', recovery_views.request_recovery, name='password-reset'),
    path('password-reset/done/', TemplateView.as_view(template_name='tenants/recovery_done.html'), name='password-reset-done'),
    path('password-reset/confirm/<uidb64>/<token>/', recovery_views.RecoveryConfirmView.as_view(), name='password-reset-confirm'),
    path('password-reset/complete/', recovery_views.RecoveryCompleteView.as_view(), name='password-reset-complete'),
    # Managed Provisioning & Activation
    path('request-access/', signup_views.request_access_view, name='request-access'),
    path('register/', signup_views.request_access_view, name='register'),
    path('registration/check-email/', signup_views.registration_check_email_view, name='registration-check-email'),
    path('activate/<str:token>/', signup_views.activate_account_view, name='activate-account'),
    path('signup/', signup_views.signup_view, name='signup'),
    path('verify-email/notice/', signup_views.verification_notice_view, name='verification-notice'),
    path('verify-email/<str:token>/', signup_views.verify_email_view, name='verify-email'),
    path('verify-recovery-email/<str:token>/', signup_views.verify_recovery_email_view, name='verify-recovery-email'),
    path('resend-verification/', signup_views.resend_verification_view, name='resend-verification'),
    path('access-pending/', signup_views.access_pending_view, name='access-pending'),
    path('workspaces/select/', signup_views.tenant_select_view, name='tenant-select'),
    path('workspaces/switch/<int:tenant_id>/', signup_views.tenant_switch_view, name='tenant-switch'),
    path('onboarding/', onboarding_views.onboarding_wizard_view, name='onboarding-wizard'),

    # Platform Superadministration (Platform-Only Context)
    path('platform/', platform_views.platform_dashboard_view, name='platform-dashboard'),
    path('platform/tenants/', platform_views.platform_tenants_view, name='platform-tenants'),
    path('platform/tenants/<int:tenant_id>/inspect/', platform_views.platform_inspect_tenant_view, name='platform-inspect-tenant'),
    path('platform/exit-inspection/', platform_views.platform_exit_inspection_view, name='platform-exit-inspection'),
    path('platform/access-matrix/', platform_views.platform_access_matrix_view, name='platform-access-matrix'),
    path('platform/tenants/<int:tenant_id>/overrides/', platform_views.platform_tenant_overrides_view, name='platform-tenant-overrides'),
    path('platform/audit/', platform_views.platform_audit_view, name='platform-audit'),
]
