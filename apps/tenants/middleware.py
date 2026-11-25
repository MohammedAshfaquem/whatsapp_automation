from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.http import JsonResponse
from .models import PlatformServiceConfig, Tenant, TenantMembership, UserSecurityProfile
from .context import set_current_tenant, clear_current_tenant
from .platform_auth import can_platform_access, is_platform_operator


class TenantMiddleware(MiddlewareMixin):
    """
    Resolves the active Tenant and TenantMembership for authenticated requests.
    Supports multi-tenant users with safe session-based tenant switching.
    Enforces separation between platform superadmin context and tenant inspection.
    Enforces email verification access gating and maintenance mode.
    """

    def process_request(self, request):
        request.tenant = None
        request.membership = None
        request.user_tenants = []
        request.is_inspecting = False

        path = request.path or '/'
        user = getattr(request, 'user', None)
        is_operator = bool(user and user.is_authenticated and is_platform_operator(user))

        if not is_operator:
            exempt_prefixes = (
                '/health/',
                '/login/',
                '/logout/',
                '/static/',
                '/admin/',
                '/api/session/bootstrap/',
                '/api/platform/',
                '/whatsapp/webhook/',
                '/webhook/',
            )
            if not any(path.startswith(prefix) for prefix in exempt_prefixes):
                try:
                    svc_cfg = PlatformServiceConfig.objects.filter(pk=1).only(
                        'maintenance_mode', 'maintenance_message'
                    ).first()
                except Exception:
                    svc_cfg = None
                if svc_cfg and svc_cfg.maintenance_mode:
                    msg = (svc_cfg.maintenance_message or '').strip() or (
                        'Scheduled maintenance is in progress. Please try again shortly.'
                    )
                    if path.startswith('/api/') or path.startswith('/conversations/'):
                        return JsonResponse({'error': msg, 'maintenance_mode': True}, status=503)
                    if path.startswith('/app/'):
                        from django.http import HttpResponse
                        from django.utils.html import escape
                        return HttpResponse(
                            f"<!doctype html><html><body style='font-family:sans-serif;padding:3rem;max-width:36rem;margin:auto'><h1>Maintenance in Progress</h1><p>{escape(msg)}</p></body></html>",
                            status=503,
                            content_type='text/html; charset=utf-8',
                        )

        if not user or not user.is_authenticated:
            clear_current_tenant()
            return

        # 1. Platform Operator: Platform Administration vs Explicit Inspection Context
        if is_operator:
            request.user_tenants = list(Tenant.objects.filter(is_active=True).order_by('name'))
            # Explicit inspection only: operators never drop into client workspaces implicitly
            inspecting_id = request.session.get('inspecting_tenant_id') or request.session.get('active_tenant_id')
            if inspecting_id and can_platform_access(user, 'inspect', write=True)[0]:
                inspected_tenant = Tenant.objects.filter(id=inspecting_id, is_active=True).first()
                if inspected_tenant:
                    request.tenant = inspected_tenant
                    request.is_inspecting = True
                    set_current_tenant(request.tenant)
                    return
            # If not inspecting, Platform Operators operate strictly in Super Admin Console (tenant is None)
            request.tenant = None
            request.is_inspecting = False
            clear_current_tenant()
            return

        # 2. Standard user: find all active memberships
        memberships = list(
            TenantMembership.objects.filter(
                user=request.user,
                is_active=True,
                tenant__is_active=True
            ).select_related('tenant')
        )
        request.user_tenants = [m.tenant for m in memberships]

        if not request.user_tenants:
            clear_current_tenant()
            return

        # 3. Check requested/switched tenant in session
        selected_tenant_id = request.session.get('active_tenant_id')
        active_tenant = None
        if selected_tenant_id:
            for t in request.user_tenants:
                if t.id == selected_tenant_id:
                    active_tenant = t
                    break

        # 4. Fallback to first membership tenant
        if not active_tenant:
            active_tenant = request.user_tenants[0]
            request.session['active_tenant_id'] = active_tenant.id

        request.tenant = active_tenant
        for m in memberships:
            if m.tenant_id == active_tenant.id:
                request.membership = m
                break

        set_current_tenant(request.tenant)

        # 5. Email Verification Access Gating
        sec_profile = UserSecurityProfile.get_or_create_for_user(request.user)
        if not sec_profile.email_verified and not sec_profile.skip_mailbox_gate:
            exempt_prefixes = [
                '/request-access',
                '/register',
                '/registration/',
                '/password-reset/',
                '/app/onboarding',
                '/app/account',
                '/app/subscription',
                '/app/usage',
                '/app/help-support',
                '/api/auth/',
                '/api/onboarding/',
                '/api/support/',
                '/activate',
                '/verify-email',
                '/verify-recovery-email',
                '/resend-verification',
                '/onboarding',
                '/logout',
                '/login',
                '/access-pending',
                '/static',
                '/media',
                '/terms',
                '/privacy',
            ]
            path = request.path_info
            if not any(path.startswith(prefix) for prefix in exempt_prefixes):
                if path.startswith('/api/'):
                    return JsonResponse({'error': 'Email verification required'}, status=403)
                return redirect('verification-notice')

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None
        path = request.path_info
        if path.startswith(('/api/platform/', '/app/platform/', '/platform/')) and not is_platform_operator(user):
            return JsonResponse({'error': 'Platform administrator access required.'}, status=403)
        client_api = path.startswith('/api/') and not path.startswith(('/api/auth/', '/api/platform/'))
        client_page = path.startswith('/app/') and not path.startswith('/app/platform/') and path != '/app/account'
        if is_platform_operator(user) and not getattr(request, 'tenant', None) and (client_api or client_page):
            if client_page:
                return redirect('/app/platform/dashboard')
            return JsonResponse({'error': 'Select a client workspace using explicit inspection before accessing client data.'}, status=403)
        tenant = getattr(request, 'tenant', None)
        setup_exempt = (
            '/api/auth/', '/api/settings/', '/api/onboarding/', '/api/platform/', '/api/support/',
            '/api/whatsapp/webhook/', '/api/webhooks/', '/app/settings', '/app/onboarding',
            '/app/subscription', '/app/usage', '/app/help-support',
            '/password-reset/', '/admin/password_change/', '/app/account', '/app/platform/', '/platform/', '/activate', '/login', '/logout',
            '/verify-email', '/verify-recovery-email', '/resend-verification', '/static/', '/media/', '/terms', '/privacy',
        )
        if tenant and tenant.requires_meta_setup and not path.startswith(setup_exempt):
            from .meta_setup import meta_setup_state
            state = meta_setup_state(tenant)
            if not state['ready']:
                if path.startswith('/api/'):
                    return JsonResponse({'error': state['reason'], 'code': 'META_SETUP_REQUIRED', 'setup_url': '/app/settings?tab=whatsapp', **state}, status=403)
                return redirect('/app/settings?tab=whatsapp')
        if request.method in ('GET', 'HEAD'):
            from .ui_routes import CLIENT_ALIASES, PLATFORM_ALIASES, entry_destination
            name = getattr(getattr(request, 'resolver_match', None), 'url_name', '')
            if name in PLATFORM_ALIASES:
                return redirect(PLATFORM_ALIASES[name])
            if name in CLIENT_ALIASES:
                # Preserve the dedicated consumer portal for non-workspace customers.
                consumer = name == 'dashboard' and not user.is_staff and not user.is_superuser and not tenant and hasattr(user, 'customer_profile')
                if not consumer:
                    # A retired detail URL remains tenant-scoped before redirecting.
                    if name in ('crm-contact-detail', 'crm-contact-edit'):
                        from apps.chatbot.models import Customer
                        from django.shortcuts import get_object_or_404
                        get_object_or_404(Customer, pk=view_kwargs.get('contact_id'), tenant=tenant)
                    elif name == 'crm-company-detail':
                        from apps.crm.models import Company
                        from django.shortcuts import get_object_or_404
                        get_object_or_404(Company, pk=view_kwargs.get('company_id'), tenant=tenant)
                    elif name == 'crm-deal-detail':
                        from apps.crm.models import Deal
                        from django.shortcuts import get_object_or_404
                        get_object_or_404(Deal, pk=view_kwargs.get('deal_id'), tenant=tenant)
                    target = CLIENT_ALIASES[name]
                    if name in ('crm-contact-detail', 'crm-contact-edit'):
                        target += '?contact_id=' + str(view_kwargs.get('contact_id'))
                    if user.is_superuser and not getattr(request, 'is_inspecting', False):
                        target = entry_destination(request)
                    return redirect(target)
        return None

    def process_response(self, request, response):
        clear_current_tenant()
        return response

    def process_exception(self, request, exception):
        clear_current_tenant()
