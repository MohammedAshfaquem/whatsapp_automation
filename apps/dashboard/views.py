import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils.http import url_has_allowed_host_and_scheme
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import ensure_csrf_cookie
from uuid import UUID

from apps.tenants.models import (
    Tenant, TenantMembership, TenantInvitation, TenantAuditLog,
    MembershipRole, SubscriptionStatus, StaffAccessRequest, StaffRequestStatus
)
from apps.tenants.context import user_can_manage_tenant
from apps.tenants.capabilities import require_capability, can_perform_action
from apps.services.models import Service
from apps.chatbot.models import Customer, Conversation, Message, ConversationStatus, ChannelChoice, MessageDirection
from apps.bookings.models import Booking, BookingStatus
from apps.bookings.booking_service import BookingService
from apps.business.models import BusinessProfile
from apps.whatsapp.models import WhatsAppDelivery
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.language import display_input
from apps.chatbot.ai_status import get_ai_status
from apps.chatbot.gemini_service import GeminiChatService
from apps.knowledge_base.synchronization import KnowledgeSynchronizer
from apps.tenants.ui_routes import entry_destination
from .forms import (
    LoginForm, ServiceForm, StaffUserCreationForm, CustomerCreationForm,
    TenantInviteForm, PlatformTenantCreateForm
)

logger = logging.getLogger(__name__)

def login_view(request):
    """
    Unified Login Portal for everyone: Platform Superadmins, Tenant Owners,
    Tenant Admins, and Staff.
    Supports email or username, enforces safe redirects, and routes to appropriate
    role contexts (Platform, Workspace, Multi-Tenant Select, or Access Pending).
    """
    if request.user.is_authenticated:
        if request.user.is_superuser:
            request.session.pop('active_tenant_id',None)
            request.session.pop('inspecting_tenant_id',None)
            return redirect('/app/platform/dashboard')
        active_memberships = request.user.tenant_memberships.filter(is_active=True, tenant__is_active=True)
        if active_memberships.exists():
            return redirect(entry_destination(request))
        if not request.user.is_staff and hasattr(request.user, 'customer_profile'):
            return redirect('dashboard')
        return redirect('access-pending')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            login_id = form.cleaned_data['username'].strip()
            password = form.cleaned_data['password']

            # Resolve username, internal synthetic identifier, or unique email address
            candidate_user = User.objects.filter(username__iexact=login_id).first()
            if not candidate_user:
                candidate_user = User.objects.filter(security_profile__internal_identifier__iexact=login_id).first()
            if not candidate_user:
                email_matches = User.objects.filter(email__iexact=login_id)
                if email_matches.count() == 1:
                    candidate_user = email_matches.first()
            auth_username = candidate_user.username if candidate_user else login_id

            user = authenticate(request, username=auth_username, password=password)
            if user is not None:
                auth_login(request, user)
                name = user.first_name or user.username
                messages.success(request, f"Welcome back, {name}!")

                # Evaluate requested redirect url
                next_url = request.GET.get('next')
                if next_url and not url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
                ):
                    next_url = None

                # 1. Superuser -> Platform Dashboard (or safe next)
                if user.is_superuser:
                    request.session.pop('active_tenant_id',None)
                    request.session.pop('inspecting_tenant_id',None)
                    return redirect(entry_destination(request,user,next_url,login=True))

                # 2. Check email verification gate
                from apps.tenants.models import UserSecurityProfile
                sec_profile = UserSecurityProfile.get_or_create_for_user(user)

                # 3. Check active tenant memberships
                memberships = list(user.tenant_memberships.filter(is_active=True, tenant__is_active=True).select_related('tenant'))
                if not memberships:
                    if not user.is_staff and hasattr(user, 'customer_profile'):
                        return redirect('dashboard')
                    return redirect('access-pending')

                # Multi-tenant user: if next not specified and more than 1 tenant, let them pick
                if len(memberships) > 1 and not request.session.get('active_tenant_id') and not next_url:
                    return redirect('tenant-select')

                if not request.session.get('active_tenant_id'):
                    request.session['active_tenant_id'] = memberships[0].tenant.id

                # If user is unverified (and not exempt staff/internal account), check onboarding
                if not sec_profile.email_verified and not sec_profile.skip_mailbox_gate:
                    tenant = memberships[0].tenant
                    if hasattr(tenant, 'onboarding_progress') and not tenant.onboarding_progress.is_completed:
                        return redirect('onboarding-wizard')
                    return redirect('verification-notice')

                return redirect(entry_destination(request,user,next_url,login=True))
            else:
                messages.error(request, "Invalid username or password. Please try again.")
    else:
        form = LoginForm()

    return render(request, 'dashboard/login.html', {'form': form})


def logout_view(request):
    """Logout authenticated user and clear session state."""
    auth_logout(request)
    request.session.flush()
    messages.info(request, "You have been successfully logged out.")
    return redirect('login')

@login_required(login_url='login')
@ensure_csrf_cookie
def dashboard_view(request):
    """
    Main Management Dashboard or Customer Portal based on role.
    """
    tenant = getattr(request, 'tenant', None)
    user_membership = getattr(request, 'membership', None)

    # 1. Customer Role Check: If user has a linked Customer profile and is not staff/admin
    is_customer = (
        hasattr(request.user, 'customer_profile') 
        and request.user.customer_profile is not None 
        and not (request.user.is_staff or request.user.is_superuser or user_membership)
    )

    if is_customer:
        customer = request.user.customer_profile
        cust_tenant = customer.tenant or tenant
        tagged_services = customer.assigned_services.filter(is_active=True)
        if not tagged_services.exists():
            tagged_services = Service.objects.filter(tenant=cust_tenant, is_active=True) if cust_tenant else Service.objects.filter(is_active=True)
        customer_bookings = Booking.objects.filter(customer=customer).order_by('-created_at')
        customer_conversations = Conversation.objects.filter(customer=customer).order_by('-last_message_at')
        current_conversation = customer_conversations.filter(channel=ChannelChoice.SIMULATED).exclude(status=ConversationStatus.CLOSED).first()
        history = {'messages': []}
        if current_conversation:
            history = {
                'conversation_id': current_conversation.id,
                'handover_required': current_conversation.status == ConversationStatus.HUMAN_HANDOVER,
                'booking_progress': BookingService.progress(current_conversation),
                'messages': [{'id': m.pk, 'text': display_input(m.message_text, customer.preferred_language) if m.direction == MessageDirection.INBOUND else m.message_text, 'direction': m.direction, 'timestamp': m.created_at.isoformat(),
                              'options': m.response_data.get('options') if m.direction == MessageDirection.OUTBOUND else []}
                             for m in reversed(list(current_conversation.messages.order_by('-created_at')[:40]))]
            }
        return render(request, 'dashboard/portal.html', {
            'customer': customer,
            'tagged_services': tagged_services,
            'bookings': customer_bookings,
            'conversations': customer_conversations,
            'total_services_count': Service.objects.filter(tenant=cust_tenant, is_active=True).count() if cust_tenant else Service.objects.filter(is_active=True).count(),
            'business': BusinessProfile.get_active(tenant=cust_tenant),
            'chat_history': history,
        })

    # Access check for management dashboard: must be superuser, staff, or have membership in a tenant
    if not (request.user.is_staff or request.user.is_superuser or getattr(request, 'user_tenants', [])):
        raise PermissionDenied('Access requires an active tenant membership or staff permissions.')

    return redirect(entry_destination(request))

    # 2. Staff / Superadmin / Tenant Workspace Dashboard
    if tenant:
        services_qs = Service.objects.filter(tenant=tenant)
        customers_qs = Customer.objects.filter(tenant=tenant)
        conversations_qs = Conversation.objects.filter(tenant=tenant)
        bookings_qs = Booking.objects.filter(tenant=tenant)
        deliveries_qs = WhatsAppDelivery.objects.filter(tenant=tenant)
    else:
        services_qs = Service.objects.all()
        customers_qs = Customer.objects.all()
        conversations_qs = Conversation.objects.all()
        bookings_qs = Booking.objects.all()
        deliveries_qs = WhatsAppDelivery.objects.all()

    services_count = services_qs.count()
    active_services_count = services_qs.filter(is_active=True).count()
    total_messages_count = Message.objects.filter(conversation__in=conversations_qs).count()
    chatbot_bookings_count = bookings_qs.count()
    pending_bookings_count = bookings_qs.filter(status=BookingStatus.PENDING).count()
    users_count = User.objects.count()

    # Chatted Customers (customers who engaged with the bot)
    chatted_customers_qs = (
        customers_qs
        .filter(conversations__messages__isnull=False)
        .distinct()
        .prefetch_related('conversations__messages', 'bookings', 'assigned_services')
        .order_by('-updated_at')
    )
    chatted_customers_count = chatted_customers_qs.count()

    # Classify each chatted customer into Lead Funnel Categories:
    # - "BOOKED": Completed at least one booking
    # - "HOT_LEAD": Chatted & explored services/prices, but hasn't booked yet!
    # - "HANDOVER": Requested human support
    inquiry_leads = []
    booked_leads_count = 0
    hot_leads_count = 0
    handover_leads_count = 0

    for cust in chatted_customers_qs:
        conv = cust.conversations.order_by('-last_message_at').first()
        msgs = Message.objects.filter(conversation__customer=cust).order_by('-created_at')
        total_msgs = msgs.count()
        last_msg = msgs.first()
        last_inbound = msgs.filter(direction=MessageDirection.INBOUND).first()

        has_booking = cust.bookings.exists()
        is_handover = conv.status == ConversationStatus.HUMAN_HANDOVER if conv else False

        if is_handover:
            category = 'HANDOVER'
            handover_leads_count += 1
            category_label = 'Waiting for team'
            badge_class = 'badge-yellow'
        elif has_booking:
            category = 'BOOKED'
            booked_leads_count += 1
            latest_b = cust.bookings.order_by('-created_at').first()
            category_label = f"Booked (#{latest_b.id} - {latest_b.get_status_display()})"
            badge_class = "badge-green"
        else:
            category = 'HOT_LEAD'
            hot_leads_count += 1
            category_label = "Hot Lead (Chatted, No Booking Yet)"
            badge_class = "badge-amber"

        clean_digits = "".join([c for c in cust.phone_number if c.isdigit()])
        if len(clean_digits) == 10:
            clean_phone = f"91{clean_digits}"
        else:
            clean_phone = clean_digits

        inquiry_leads.append({
            'customer': cust,
            'category': category,
            'category_label': category_label,
            'badge_class': badge_class,
            'total_messages': total_msgs,
            'last_message_text': last_inbound.message_text if last_inbound else (last_msg.message_text if last_msg else "No message text"),
            'last_active': conv.last_message_at if conv else cust.updated_at,
            'conv_id': conv.id if conv else None,
            'clean_phone': clean_phone,
            'service_name': conv.service.name if (conv and conv.service) else "General Inquiry",
        })

    # Data collections
    services = services_qs.order_by('-id')
    customers = customers_qs.prefetch_related('assigned_services', 'conversations').order_by('-updated_at')
    conversations = (
        conversations_qs
        .select_related('customer', 'service')
        .prefetch_related('messages')
        .order_by('-last_message_at')[:40]
    )
    bookings = (
        bookings_qs
        .select_related('customer', 'service')
        .order_by('-created_at')[:40]
    )
    
    # Team & RBAC
    can_manage_team = request.user.is_superuser or user_can_manage_tenant(request.user, tenant)
    team_memberships = TenantMembership.objects.filter(tenant=tenant).select_related('user') if tenant else None
    tenant_memberships = team_memberships
    pending_invitations = TenantInvitation.objects.filter(tenant=tenant, is_accepted=False).order_by('-created_at') if tenant else None
    invite_form = TenantInviteForm() if can_manage_team else None

    team_users = None
    user_form = None
    if request.user.is_superuser:
        team_users = User.objects.all().order_by('-date_joined')
        user_form = StaffUserCreationForm()

    # Platform Admin for Superusers
    all_tenants = Tenant.objects.all().order_by('name') if request.user.is_superuser else []
    all_tenants_count = len(all_tenants) if request.user.is_superuser else 0
    platform_tenant_form = PlatformTenantCreateForm() if request.user.is_superuser else None
    platform_audit_logs = (
        TenantAuditLog.objects.select_related('tenant', 'actor').order_by('-created_at')[:30]
        if request.user.is_superuser else []
    )

    service_form = ServiceForm()
    customer_form = CustomerCreationForm()

    context = {
        'tenant': tenant,
        'membership': user_membership,
        'can_manage_team': can_manage_team,
        'team_memberships': team_memberships,
        'pending_invitations': pending_invitations,
        'invite_form': invite_form,
        'all_tenants': all_tenants,
        'all_tenants_count': all_tenants_count,
        'platform_tenant_form': platform_tenant_form,
        'platform_audit_logs': platform_audit_logs,
        'ai_connection': get_ai_status(),
        'handover_queue': conversations_qs.filter(status=ConversationStatus.HUMAN_HANDOVER)
            .select_related('customer', 'assigned_staff').order_by('picked_up_at', 'last_message_at')[:40],
        'delivery_attention_count': deliveries_qs.filter(status__in=['FAILED', 'UNKNOWN', 'BLOCKED']).count(),
        'services_count': services_count,
        'active_services_count': active_services_count,
        'total_messages_count': total_messages_count,
        'chatted_customers_count': chatted_customers_count,
        'chatbot_bookings_count': chatbot_bookings_count,
        'bookings_count': chatbot_bookings_count,
        'customers_count': customers.count(),
        'booked_leads_count': booked_leads_count,
        'hot_leads_count': hot_leads_count,
        'handover_leads_count': handover_leads_count,
        'inquiry_leads': inquiry_leads,
        'pending_bookings_count': pending_bookings_count,
        'users_count': users_count,
        'services': services,
        'customers': customers,
        'conversations': conversations,
        'bookings': bookings,
        'upcoming_bookings': bookings_qs.select_related('customer', 'service').filter(
            status__in=[BookingStatus.PENDING, BookingStatus.CONFIRMED]).order_by('preferred_date', '-created_at')[:3],
        'team_users': team_users,
        'service_form': service_form,
        'customer_form': customer_form,
        'user_form': user_form,
        'is_superuser': request.user.is_superuser,
    }
    return render(request, 'dashboard/index.html', context)

@login_required(login_url='login')
@require_POST
def switch_tenant_view(request):
    """Switch active tenant context for the user."""
    tenant_id = request.POST.get('tenant_id')
    if not tenant_id:
        return redirect('dashboard')
    try:
        tenant_id = int(tenant_id)
    except (ValueError, TypeError):
        messages.error(request, 'Invalid tenant.')
        return redirect('dashboard')
    
    tenant = get_object_or_404(Tenant, id=tenant_id)
    if not request.user.is_superuser:
        has_membership = TenantMembership.objects.filter(tenant=tenant, user=request.user).exists()
        if not has_membership:
            messages.error(request, 'You do not have access to that workspace.')
            return redirect('dashboard')
    
    request.session['active_tenant_id'] = tenant.id
    messages.success(request, f"Switched active workspace to {tenant.name}.")
    next_url = request.POST.get('next') or request.GET.get('next') or 'dashboard'
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = 'dashboard'
    return redirect(next_url)

@login_required(login_url='login')
@require_capability('team', action='create')
@require_POST
def tenant_invite_view(request):
    """Invite a new team member to the current tenant."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        messages.error(request, "No active workspace selected.")
        return redirect('dashboard')
    if not (request.user.is_superuser or user_can_manage_tenant(request.user, tenant)):
        raise PermissionDenied("Only tenant administrators or owners can invite team members.")

    if not tenant.can_add_staff():
        messages.error(request, f"Seat limit reached ({tenant.effective_max_staff} seats allocated). Please upgrade your plan to invite additional team members.")
        return redirect('/dashboard/#users')
    
    form = TenantInviteForm(request.POST)
    if form.is_valid():
        email = form.cleaned_data['email'].lower().strip()
        role = form.cleaned_data['role']
        
        existing_user = User.objects.filter(email=email).first()
        if existing_user and TenantMembership.objects.filter(tenant=tenant, user=existing_user).exists():
            messages.warning(request, f"{email} is already a member of {tenant.name}.")
            return redirect('/dashboard/#users')
        
        inv = TenantInvitation.objects.filter(tenant=tenant, email=email, is_accepted=False).first()
        if inv and not inv.is_expired:
            messages.info(request, f"An active invitation for {email} already exists.")
            return redirect('/dashboard/#users')
        
        staff_req = StaffAccessRequest.objects.create(
            tenant=tenant,
            requested_by=request.user,
            full_name=email.split('@')[0],
            email=email,
            role=role,
            notes="Submitted via Dashboard Users panel",
            status=StaffRequestStatus.PENDING
        )
        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=request.user,
            action='STAFF_REQUEST_SUBMITTED',
            summary=f"Staff access request for {email} ({role}) submitted by @{request.user.username}",
            details={'email': email, 'role': role, 'request_id': str(staff_req.id)}
        )
        messages.success(request, f"Staff access request for {email} ({role}) has been submitted to Super Admin for approval.")
    else:
        error_msgs = "; ".join([f"{k}: {', '.join(v)}" for k, v in form.errors.items()])
        messages.error(request, f"Could not submit staff request: {error_msgs}")
    
    return redirect('/dashboard/#users')

@login_required(login_url='login')
@require_POST
def platform_tenant_create_view(request):
    """Platform Superadmin: Create a new business tenant and its initial owner."""
    if not request.user.is_superuser:
        raise PermissionDenied("Only platform superadministrators can create new tenants.")
    
    form = PlatformTenantCreateForm(request.POST)
    if form.is_valid():
        name = form.cleaned_data['name'].strip()
        plan = form.cleaned_data['plan']
        owner_username = form.cleaned_data['owner_username'].strip()
        owner_email = form.cleaned_data['owner_email'].lower().strip()
        owner_password = form.cleaned_data['owner_password']
        
        base_slug = slugify(name)
        slug = base_slug
        counter = 1
        while Tenant.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        with transaction.atomic():
            tenant = Tenant.objects.create(name=name, slug=slug, plan=plan)
            owner_user = User.objects.filter(username=owner_username).first()
            if not owner_user:
                owner_user = User.objects.create_user(
                    username=owner_username,
                    email=owner_email,
                    password=owner_password,
                    is_staff=True,
                    is_superuser=False
                )
            TenantMembership.objects.create(tenant=tenant, user=owner_user, role=MembershipRole.OWNER)
            TenantAuditLog.objects.create(
                tenant=tenant,
                actor=request.user,
                action='TENANT_CREATED',
                summary=f"Tenant '{name}' provisioned with owner @{owner_username}",
                details={'name': name, 'slug': slug, 'plan': plan, 'owner': owner_username}
            )
        messages.success(request, f"Tenant '{tenant.name}' created with owner @{owner_username}.")
    else:
        error_msgs = "; ".join([f"{k}: {', '.join(v)}" for k, v in form.errors.items()])
        messages.error(request, f"Could not create tenant: {error_msgs}")
    
    return redirect('/dashboard/#platform')

@login_required(login_url='login')
@require_POST
def platform_tenant_toggle_view(request, tenant_id):
    """Platform Superadmin: Activate or suspend a tenant."""
    if not request.user.is_superuser:
        raise PermissionDenied("Only platform superadministrators can manage tenants.")
    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant.is_active = not tenant.is_active
    tenant.save(update_fields=['is_active', 'updated_at'])
    status_str = "activated" if tenant.is_active else "suspended"
    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action='TENANT_STATUS_CHANGED',
        summary=f"Tenant '{tenant.name}' marked {status_str}",
        details={'is_active': tenant.is_active, 'status': status_str}
    )
    messages.success(request, f"Tenant '{tenant.name}' has been {status_str}.")
    return redirect('/dashboard/#platform')


@login_required(login_url='login')
@require_capability('contacts', action='create')
@require_POST
def customer_create_view(request):
    """Staff/Admin: Add a customer, optionally create portal login, and tag services."""
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Only staff and admins can register customers.")

    tenant = getattr(request, 'tenant', None)
    form = CustomerCreationForm(request.POST)
    if form.is_valid():
        name = form.cleaned_data['name']
        phone_number = form.cleaned_data['phone_number']
        email = form.cleaned_data.get('email', '')
        portal_password = form.cleaned_data.get('portal_password', '')
        tagged_services = form.cleaned_data.get('tagged_services', [])

        try:
            with transaction.atomic():
                user = None
                if portal_password:
                    user = User.objects.create_user(username=phone_number, password=portal_password,
                        first_name=name, email=email, is_staff=False, is_superuser=False)
                customer = Customer.objects.create(tenant=tenant, user=user, name=name, phone_number=phone_number)
                if tagged_services:
                    customer.assigned_services.set(tagged_services)
        except IntegrityError:
            messages.error(request, 'That account or customer already exists. No login was changed.')
            return redirect('/dashboard/#customers')

        services_str = f"with {len(tagged_services)} tagged service(s)" if tagged_services else ""
        messages.success(request, f"Customer '{customer.name}' ({customer.phone_number}) registered successfully {services_str}.")
    else:
        error_msgs = "; ".join([f"{k}: {', '.join(v)}" for k, v in form.errors.items()])
        messages.error(request, f"Could not create customer: {error_msgs}")

    return redirect('/dashboard/#customers')

@login_required(login_url='login')
@require_capability('contacts', action='edit')
@require_POST
def customer_tag_service_view(request, customer_id):
    """Staff/Admin: Update tagged services for an existing customer."""
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Only staff and admins can tag services to customers.")

    customer = get_object_or_404(Customer, id=customer_id)
    if not request.user.is_superuser and getattr(request, 'tenant', None) and customer.tenant and customer.tenant != request.tenant:
        raise PermissionDenied("Customer belongs to another workspace.")

    service_ids = request.POST.getlist('service_ids')
    services = Service.objects.filter(id__in=service_ids)
    if customer.tenant:
        services = services.filter(tenant=customer.tenant)
    customer.assigned_services.set(services)
    
    messages.success(request, f"Updated tagged services for {customer.name or customer.phone_number}: {len(services)} service(s) assigned.")
    return redirect('/dashboard/#customers')

@login_required(login_url='login')
@require_capability('services', action='create')
@require_POST
def service_create_view(request):
    """Add new service from the dashboard (Available to staff and superadmin)."""
    if not request.user.is_staff:
        raise PermissionDenied('Only staff can manage services.')
    form = ServiceForm(request.POST)
    if form.is_valid():
        service = form.save(commit=False)
        tenant = getattr(request, 'tenant', None)
        if tenant:
            current_count = Service.objects.filter(tenant=tenant, is_active=True).count()
            if current_count >= tenant.effective_max_services:
                messages.error(request, f"Service limit reached ({tenant.effective_max_services} services). Please upgrade your plan to add more services.")
                return redirect('/dashboard/#services')
            service.tenant = tenant
        service.save()
        # Automatically sync new service to Vector Store & Knowledge Base
        try:
            KnowledgeSynchronizer.sync_service(service)
        except Exception as e:
            logger.warning("Vector sync warning when creating service: %s", e)
        messages.success(request, f"Service '{service.name}' created with contact {service.contact_number} and synced to AI Knowledge Base.")
    else:
        error_msgs = "; ".join([f"{k}: {', '.join(v)}" for k, v in form.errors.items()])
        messages.error(request, f"Error adding service: {error_msgs}")
    return redirect('/dashboard/#services')

@login_required(login_url='login')
@require_capability('services', action='edit')
@require_POST
def service_toggle_view(request, service_id):
    """Toggle active/inactive status of a service."""
    if not request.user.is_staff:
        raise PermissionDenied('Only staff can manage services.')
    service = get_object_or_404(Service, id=service_id)
    if not request.user.is_superuser and getattr(request, 'tenant', None) and service.tenant and service.tenant != request.tenant:
        raise PermissionDenied("Service belongs to another workspace.")
    service.is_active = not service.is_active
    service.save()
    try:
        KnowledgeSynchronizer.sync_service(service)
    except Exception as e:
        logger.warning("Vector sync warning when toggling service: %s", e)
    status_str = "activated" if service.is_active else "deactivated"
    messages.success(request, f"Service '{service.name}' has been {status_str}.")
    return redirect('/dashboard/#services')

@login_required(login_url='login')
@require_capability('bookings', action='edit')
@require_POST
def booking_action_view(request, booking_id):
    """Confirm, reject, or complete a booking."""
    if not request.user.is_staff:
        raise PermissionDenied('Only staff can manage bookings.')
    booking = get_object_or_404(Booking, id=booking_id)
    if not request.user.is_superuser and getattr(request, 'tenant', None) and booking.tenant and booking.tenant != request.tenant:
        raise PermissionDenied("Booking belongs to another workspace.")
    action = request.POST.get('action')
    if action == 'confirm':
        booking.status = BookingStatus.CONFIRMED
        messages.success(request, f"Booking #{booking.id} for {booking.customer.phone_number} is now CONFIRMED.")
    elif action == 'reject':
        booking.status = BookingStatus.REJECTED
        messages.warning(request, f"Booking #{booking.id} was marked as REJECTED.")
    elif action == 'complete':
        booking.status = BookingStatus.COMPLETED
        messages.success(request, f"Booking #{booking.id} marked as COMPLETED.")
    else:
        messages.error(request, f"Unknown action '{action}'.")
        return redirect('/dashboard/#bookings')
    
    from apps.bookings.notifications import change_booking_status
    # The status transition service queues a single customer notification.
    target_status = booking.status
    booking.refresh_from_db()
    try:
        change_booking_status(booking, target_status)
    except ValueError as error:
        messages.error(request, str(error))
    return redirect('/dashboard/#bookings')

@login_required(login_url='login')
@require_POST
def user_create_view(request):
    """
    RBAC: Add a new user/staff member.
    RESTRICTED TO SUPERADMIN ONLY.
    """
    if not request.user.is_superuser:
        messages.error(request, "Permission denied: Only superadministrators can create new staff accounts.")
        return redirect('dashboard')

    form = StaffUserCreationForm(request.POST)
    if form.is_valid():
        username = form.cleaned_data['username']
        first_name = form.cleaned_data.get('first_name', '')
        last_name = form.cleaned_data.get('last_name', '')
        email = form.cleaned_data.get('email', '')
        password = form.cleaned_data['password']
        role = form.cleaned_data['role']

        is_super = (role == 'admin')
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=True,
            is_superuser=is_super,
        )
        role_label = "Superadmin" if is_super else "Staff Member"
        messages.success(request, f"Successfully created {role_label} user: @{user.username}")
    else:
        error_msgs = "; ".join([f"{k}: {', '.join(v)}" for k, v in form.errors.items()])
        messages.error(request, f"Could not create user: {error_msgs}")

    return redirect('/dashboard/#users')

@login_required(login_url='login')
@require_POST
def chat_send_api(request):
    """
    Interactive Live WhatsApp Chat Simulator API.
    Enables customers and staff to chat with the AI Bot directly scoped to a service's contact number.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    message_text = data.get('message_text', '').strip()
    service_id = data.get('service_id')
    phone_number = data.get('phone_number')

    if not message_text:
        return JsonResponse({"error": "Message text is required."}, status=400)
    if len(message_text) > 2000:
        return JsonResponse({'error': 'Please keep messages under 2000 characters.'}, status=400)
    if not request.user.is_staff and not hasattr(request.user, 'customer_profile'):
        raise PermissionDenied('A customer profile is required.')

    # Resolve phone number
    if hasattr(request.user, 'customer_profile') and request.user.customer_profile:
        customer_phone = request.user.customer_profile.phone_number
        caller_tenant = request.user.customer_profile.tenant or getattr(request, 'tenant', None)
        if caller_tenant and hasattr(caller_tenant, 'subscription'):
            if caller_tenant.subscription.status in (SubscriptionStatus.SUSPENDED,):
                return JsonResponse({'error': 'Service temporarily unavailable.'}, status=403)
    elif phone_number and request.user.is_staff:
        customer_phone = phone_number.strip()
        caller_tenant = getattr(request, 'tenant', None)
        allowed, reason = can_perform_action(request.user, caller_tenant, 'inbox', 'send_message')
        if not allowed:
            return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)
    else:
        customer_phone = "+919999900001"  # Default test customer number for simulation
        caller_tenant = getattr(request, 'tenant', None)
        if request.user.is_staff:
            allowed, reason = can_perform_action(request.user, caller_tenant, 'inbox', 'send_message')
            if not allowed:
                return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    try:
        service_id_int = int(service_id) if service_id else None
    except (ValueError, TypeError):
        service_id_int = None

    conversation_id = data.get('conversation_id')
    if conversation_id:
        get_object_or_404(Conversation, pk=conversation_id, customer__phone_number=customer_phone, channel=ChannelChoice.SIMULATED)
    request_id = data.get('request_id')
    if request_id:
        try:
            request_id = str(UUID(str(request_id)))
        except ValueError:
            return JsonResponse({'error': 'Invalid request identifier.'}, status=400)
    from apps.chatbot.processing import ConversationBusyError
    try:
        result = ConversationService.process_message(
            phone_number=customer_phone,
            message_text=message_text,
            channel=ChannelChoice.SIMULATED,
            service_id=service_id_int,
            conversation_id=conversation_id,
            external_message_id=f'portal:{request.user.pk}:{request_id}' if request_id else None,
            tenant=caller_tenant
        )
    except ConversationBusyError:
        return JsonResponse({'error': 'Your previous message is still being processed. Please try again shortly.'}, status=503)

    return JsonResponse({
        "reply": result["reply"],
        "conversation_id": result["conversation_id"],
        "handover_required": result.get("handover_required", False),
        "booking_id": result.get("booking_id"),
        "interactive": result.get("interactive"),
        "options": result.get("options"),
        "booking_progress": result.get('booking_progress'),
        "bookings": result.get('bookings'),
    })

@login_required(login_url='login')
@require_GET
def conversation_messages_api(request, conversation_id):
    """
    Returns JSON message transcript for a customer conversation.
    Enables viewing the conversation timeline in an interactive modal.
    """
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if not request.user.is_staff and conversation.customer.user_id != request.user.id:
        raise PermissionDenied('This conversation belongs to another customer.')
    if not request.user.is_superuser and getattr(request, 'tenant', None) and conversation.tenant and conversation.tenant != request.tenant:
        raise PermissionDenied('This conversation belongs to another workspace.')
    if request.user.is_staff:
        allowed, reason = can_perform_action(request.user, conversation.tenant or getattr(request, 'tenant', None), 'inbox', 'view')
        if not allowed:
            raise PermissionDenied(f"Access Denied: {reason}")
    if request.GET.get('mark_read') == '1' and conversation.unread_count != 0:
        conversation.unread_count = 0
        conversation.save(update_fields=['unread_count', 'updated_at'])

    messages_qs = conversation.messages.all().order_by('created_at')
    msg_query = request.GET.get('q', '').strip()
    if msg_query:
        messages_qs = messages_qs.filter(message_text__icontains=msg_query)
    
    # 24-hour customer service window status
    from datetime import timedelta
    last_inbound = conversation.messages.filter(direction=MessageDirection.INBOUND).order_by('-created_at').first()
    if conversation.channel == ChannelChoice.WHATSAPP:
        if last_inbound and last_inbound.created_at >= timezone.now() - timedelta(hours=24):
            is_window_open = True
            window_expires_at = (last_inbound.created_at + timedelta(hours=24)).isoformat()
        else:
            is_window_open = False
            window_expires_at = None
    else:
        is_window_open = True
        window_expires_at = None

    from apps.chatbot.models import SenderType
    from apps.whatsapp.models import WhatsAppDelivery
    from django.db.models import Q
    msg_ids = [m.id for m in messages_qs if m.direction == MessageDirection.OUTBOUND]
    deliveries_map = {}
    if msg_ids:
        delivery_records = WhatsAppDelivery.objects.filter(
            tenant=conversation.tenant
        ).filter(Q(dedup_key__in=[f'staff:{mid}' for mid in msg_ids]) |
                 Q(payload__conversation_id=conversation.pk, payload__message_id__in=msg_ids, payload__sender_type='CAMPAIGN'))
        for d in delivery_records:
            deliveries_map[d.dedup_key] = d
            if d.payload.get('sender_type') == 'CAMPAIGN' and d.payload.get('message_id') in msg_ids:
                deliveries_map[f"staff:{d.payload['message_id']}"] = d

    svc_info = f" • Service: {conversation.service.name}" if conversation.service else ""
    contact_info = f" ({conversation.service.contact_number})" if conversation.service and conversation.service.contact_number else ""

    messages_list = []
    for msg in messages_qs:
        d = deliveries_map.get(f'staff:{msg.id}')
        author_name = "AI Assistant"
        if msg.sender_type == SenderType.HUMAN:
            resp_data = msg.response_data if isinstance(msg.response_data, dict) else {}
            author_name = resp_data.get('author_name') or resp_data.get('author_username') or (
                conversation.assigned_staff.get_full_name() or conversation.assigned_staff.username if conversation.assigned_staff else "Staff"
            )
        elif msg.sender_type == SenderType.CUSTOMER:
            author_name = conversation.customer.name or 'Customer'

        delivery_status = d.status if d else ('READ' if msg.direction == MessageDirection.INBOUND else ('SENT' if msg.sender_type == SenderType.BOT else None))
        delivery_error = d.last_error if d else None
        delivery_id = d.id if d else None

        messages_list.append({
            'id': msg.id,
            'direction': msg.direction,
            'sender_type': msg.sender_type,
            'author_name': author_name,
            'text': display_input(msg.message_text, conversation.customer.preferred_language) if msg.direction == MessageDirection.INBOUND else msg.message_text,
            'status': msg.processing_status,
            'delivery_status': delivery_status,
            'delivery_error': delivery_error,
            'delivery_id': delivery_id,
            'media_type': msg.media_type,
            'media_name': msg.media_name,
            'media_mime': msg.media_mime,
            'media_size': msg.media_size,
            'media_url': f'/api/inbox/media/{msg.id}/' if msg.media_key else '',
            'timestamp': timezone.localtime(msg.created_at).strftime("%b %d, %Y %I:%M %p"),
        })

    data = {
        'conversation_id': conversation.id,
        'customer_id': conversation.customer_id,
        'customer_name': conversation.customer.name or 'Customer',
        'customer_phone': conversation.customer.phone_number,
        'channel': conversation.get_channel_display(),
        'channel_code': conversation.channel,
        'service': f"{conversation.service.name}{contact_info}" if conversation.service else "General Inquiries",
        'status': conversation.get_status_display(),
        'conversation_status': conversation.status,
        'is_window_open': is_window_open,
        'window_expires_at': window_expires_at,
        'handover_required': conversation.status == ConversationStatus.HUMAN_HANDOVER,
        'booking_progress': BookingService.progress(conversation),
        'handoff_summary': conversation.handoff_summary if request.user.is_staff else '',
        'messages': messages_list,
    }
    if request.user.is_staff:
        data['assigned_staff'] = ({'id': conversation.assigned_staff_id,
            'name': conversation.assigned_staff.get_full_name() or conversation.assigned_staff.username}
            if conversation.assigned_staff_id else None)
        data['picked_up_at'] = conversation.picked_up_at.isoformat() if conversation.picked_up_at else None
        data['can_manage'] = conversation.assigned_staff_id in (None, request.user.pk)
    return JsonResponse(data)


@login_required(login_url='login')
@require_POST
def ai_connection_test_api(request):
    if not request.user.is_staff:
        raise PermissionDenied('Only staff can test the AI connection.')
    GeminiChatService.generate_reply('Reply with OK only. This is a connection test.',
                                     system_instruction='Reply with OK only.')
    return JsonResponse(get_ai_status())


@login_required(login_url='login')
@require_capability('inbox', action='send_message')
@require_POST
@transaction.atomic
def conversation_action_api(request, conversation_id):
    if not request.user.is_staff:
        raise PermissionDenied('Only staff can manage support conversations.')
    origin = get_object_or_404(Conversation.objects.only('customer_id'), pk=conversation_id)
    Customer.objects.select_for_update().get(pk=origin.customer_id)
    conversation = get_object_or_404(Conversation.objects.select_for_update(), pk=conversation_id)
    if not request.user.is_superuser and getattr(request, 'tenant', None) and conversation.tenant and conversation.tenant != request.tenant:
        raise PermissionDenied('This conversation belongs to another workspace.')
    action = request.POST.get('action')
    if (conversation.assigned_staff_id not in (None, request.user.pk)
            and not (request.user.is_superuser and action in ('release', 'resume'))):
        return JsonResponse({'error': 'Another staff member has picked up this chat. Ask them to release it first.'}, status=409)
    if action == 'claim':
        if conversation.status != ConversationStatus.HUMAN_HANDOVER:
            return JsonResponse({'error': 'Pause the bot before claiming this conversation.'}, status=400)
        conversation.assigned_staff = request.user
        if conversation.picked_up_at is None:
            conversation.picked_up_at = timezone.now()
        conversation.save(update_fields=['status', 'handoff_summary', 'assigned_staff', 'picked_up_at', 'updated_at'])
        if conversation.customer and not conversation.customer.owner:
            conversation.customer.owner = request.user
            conversation.customer.save(update_fields=['owner'])

        from apps.whatsapp.delivery_context import cancel_pending_bot_deliveries
        cancel_pending_bot_deliveries(conversation, action)

        return JsonResponse({
            'message': 'Conversation claimed.',
            'status': conversation.status,
            'status_display': conversation.get_status_display(),
            'assigned_staff': request.user.username,
            'handover_required': True,
            'customer_id': conversation.customer_id,
            'handoff_summary': conversation.handoff_summary or '',
        })
    if action == 'switch_to_human':
        conversation.status = ConversationStatus.HUMAN_HANDOVER
        if not conversation.assigned_staff_id:
            conversation.assigned_staff = request.user
        if conversation.picked_up_at is None:
            conversation.picked_up_at = timezone.now()
        if not conversation.handoff_summary:
            conversation.handoff_summary = f'Staff @{request.user.username} switched to human mode'
        conversation.save(update_fields=['status', 'handoff_summary', 'assigned_staff', 'picked_up_at', 'updated_at'])
        if conversation.customer and not conversation.customer.owner:
            conversation.customer.owner = request.user
            conversation.customer.save(update_fields=['owner'])

        from apps.whatsapp.delivery_context import cancel_pending_bot_deliveries
        cancel_pending_bot_deliveries(conversation, action)

        return JsonResponse({
            'message': 'Switched to Human Mode. Bot replies are paused.',
            'status': conversation.status,
            'status_display': conversation.get_status_display(),
            'assigned_staff': conversation.assigned_staff.username if conversation.assigned_staff else None,
            'handover_required': True,
            'customer_id': conversation.customer_id,
            'handoff_summary': conversation.handoff_summary or '',
        })
    if action == 'release':
        conversation.assigned_staff = None
        conversation.picked_up_at = None
        conversation.save(update_fields=['assigned_staff', 'picked_up_at', 'updated_at'])
        return JsonResponse({
            'message': 'Conversation released to the team queue.',
            'status': conversation.status,
            'status_display': conversation.get_status_display(),
            'assigned_staff': None,
            'handover_required': conversation.status == ConversationStatus.HUMAN_HANDOVER,
        })
    if action in ('resume', 'pause', 'resume_bot'):
        if action == 'pause':
            ConversationService._start_handover(conversation, f'Staff @{request.user.username} paused the assistant')
            if not conversation.assigned_staff_id:
                conversation.assigned_staff = request.user
                conversation.picked_up_at = timezone.now()
        else:
            conversation.status = ConversationStatus.BOT_ACTIVE
            conversation.assigned_staff = None
            conversation.picked_up_at = None
        conversation.unresolved_count = 0
        conversation.save(update_fields=['status', 'unresolved_count', 'assigned_staff', 'picked_up_at', 'updated_at'])
        if action == 'pause':
            from apps.whatsapp.delivery_context import cancel_pending_bot_deliveries
            cancel_pending_bot_deliveries(conversation, action)
        return JsonResponse({
            'status': conversation.status,
            'status_display': conversation.get_status_display(),
            'assigned_staff': conversation.assigned_staff.username if conversation.assigned_staff else None,
            'handover_required': conversation.status == ConversationStatus.HUMAN_HANDOVER,
        })
    if action == 'reply':
        from datetime import timedelta
        from django.db import transaction
        from apps.chatbot.models import SenderType, ProcessingStatus
        from apps.whatsapp.models import WhatsAppDelivery
        from apps.whatsapp.delivery import dispatch
        if conversation.status == ConversationStatus.BOT_ACTIVE:
            return JsonResponse({'error': 'Conversation is in Bot Mode. Switch to Human mode before sending manual replies.'}, status=400)
        text = request.POST.get('text', '').strip()
        if not text or len(text) > 2000:
            return JsonResponse({'error': 'Enter a reply under 2000 characters.'}, status=400)
        last_inbound = conversation.messages.filter(direction=MessageDirection.INBOUND).order_by('-created_at').first()
        if conversation.channel == ChannelChoice.WHATSAPP and (not last_inbound or last_inbound.created_at < timezone.now() - timedelta(hours=24)):
            return JsonResponse({'error': 'The customer service window has closed. Use an approved template or wait for a customer message.'}, status=400)
        with transaction.atomic():
            from apps.crm.assignment_service import track_first_human_response
            message = Message.objects.create(
                conversation=conversation,
                direction=MessageDirection.OUTBOUND,
                sender_type=SenderType.HUMAN,
                message_text=text,
                processing_status=ProcessingStatus.PROCESSED,
                response_data={
                    'author_username': request.user.username,
                    'author_name': request.user.get_full_name() or request.user.username,
                }
            )
            track_first_human_response(conversation, request.user)
            now_ts = timezone.now()
            conv_updates = ['unread_count', 'updated_at']
            conversation.unread_count = 0
            if conversation.first_human_response_at is None:
                conversation.first_human_response_at = now_ts
                conv_updates.append('first_human_response_at')
            conversation.save(update_fields=conv_updates)
            if not conversation.handoff_summary:
                conversation.handoff_summary = ConversationService.generate_handoff_summary(conversation, 'Staff replied')
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=['status', 'last_message_at', 'assigned_staff', 'picked_up_at', 'handoff_summary', 'updated_at'])
            if conversation.channel == ChannelChoice.WHATSAPP:
                delivery = WhatsAppDelivery.objects.create(
                    tenant=conversation.tenant,
                    dedup_key=f'staff:{message.pk}',
                    recipient_phone=conversation.customer.phone_number,
                    payload={'text': text, 'conversation_id': conversation.pk, 'message_id': message.pk, 'sender_type': 'HUMAN'}
                )
                transaction.on_commit(lambda: dispatch(delivery.pk))
        return JsonResponse({'status': conversation.get_status_display(), 'message': 'Reply saved to the conversation.'})
    return JsonResponse({'error': 'Unknown action.'}, status=400)
