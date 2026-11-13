import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponseNotAllowed
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.utils.http import url_has_allowed_host_and_scheme
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from uuid import UUID

from apps.services.models import Service, PriceType
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
from .forms import LoginForm, ServiceForm, StaffUserCreationForm, CustomerCreationForm

logger = logging.getLogger(__name__)

def login_view(request):
    """Staff, Superadmin & Customer login page."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)
            if user is not None:
                auth_login(request, user)
                name = user.first_name or user.username
                messages.success(request, f"Welcome back, {name}!")
                next_url = request.GET.get('next') or 'dashboard'
                if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                    next_url = 'dashboard'
                return redirect(next_url)
            else:
                messages.error(request, "Invalid username or password. Please try again.")
    else:
        form = LoginForm()

    return render(request, 'dashboard/login.html', {'form': form})

def logout_view(request):
    """Logout authenticated user."""
    auth_logout(request)
    messages.info(request, "You have been successfully logged out.")
    return redirect('login')

@login_required(login_url='login')
@ensure_csrf_cookie
def dashboard_view(request):
    """
    Main Management Dashboard or Customer Portal based on role.
    """
    # 1. Customer Role Check: If user has a linked Customer profile and is not staff/admin
    is_customer = (
        hasattr(request.user, 'customer_profile') 
        and request.user.customer_profile is not None 
        and not (request.user.is_staff or request.user.is_superuser)
    )

    if is_customer:
        customer = request.user.customer_profile
        tagged_services = customer.assigned_services.filter(is_active=True)
        if not tagged_services.exists():
            tagged_services = Service.objects.filter(is_active=True)
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
            'total_services_count': Service.objects.filter(is_active=True).count(),
            'business': BusinessProfile.get_active(),
            'chat_history': history,
        })

    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied('A customer profile or staff account is required.')
    # 2. Staff / Superadmin Management Dashboard
    services_count = Service.objects.count()
    active_services_count = Service.objects.filter(is_active=True).count()
    total_messages_count = Message.objects.count()
    chatbot_bookings_count = Booking.objects.count()
    pending_bookings_count = Booking.objects.filter(status=BookingStatus.PENDING).count()
    users_count = User.objects.count()

    # Chatted Customers (customers who engaged with the bot)
    chatted_customers_qs = (
        Customer.objects
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
        elif is_handover:
            category = 'HANDOVER'
            handover_leads_count += 1
            category_label = "Human Handover Needed"
            badge_class = "badge-yellow"
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
    services = Service.objects.all().order_by('-id')
    customers = Customer.objects.prefetch_related('assigned_services', 'conversations').all().order_by('-updated_at')
    conversations = (
        Conversation.objects
        .select_related('customer', 'service')
        .prefetch_related('messages')
        .all()
        .order_by('-last_message_at')[:40]
    )
    bookings = (
        Booking.objects
        .select_related('customer', 'service')
        .all()
        .order_by('-created_at')[:40]
    )
    
    # RBAC: Only superadmin can manage team users
    team_users = None
    user_form = None
    if request.user.is_superuser:
        team_users = User.objects.all().order_by('-date_joined')
        user_form = StaffUserCreationForm()

    service_form = ServiceForm()
    customer_form = CustomerCreationForm()

    context = {
        'ai_connection': get_ai_status(),
        'handover_queue': Conversation.objects.filter(status=ConversationStatus.HUMAN_HANDOVER)
            .select_related('customer', 'assigned_staff').order_by('picked_up_at', 'last_message_at')[:40],
        'delivery_attention_count': WhatsAppDelivery.objects.filter(status__in=['FAILED', 'UNKNOWN', 'BLOCKED']).count(),
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
        'upcoming_bookings': Booking.objects.select_related('customer', 'service').filter(
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
def customer_create_view(request):
    """Staff/Admin: Add a customer, optionally create portal login, and tag services."""
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Only staff and admins can register customers.")

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
                customer = Customer.objects.create(user=user, name=name, phone_number=phone_number)
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
@require_POST
def customer_tag_service_view(request, customer_id):
    """Staff/Admin: Update tagged services for an existing customer."""
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Only staff and admins can tag services to customers.")

    customer = get_object_or_404(Customer, id=customer_id)
    service_ids = request.POST.getlist('service_ids')
    services = Service.objects.filter(id__in=service_ids)
    customer.assigned_services.set(services)
    
    messages.success(request, f"Updated tagged services for {customer.name or customer.phone_number}: {len(services)} service(s) assigned.")
    return redirect('/dashboard/#customers')

@login_required(login_url='login')
@require_POST
def service_create_view(request):
    """Add new service from the dashboard (Available to staff and superadmin)."""
    if not request.user.is_staff:
        raise PermissionDenied('Only staff can manage services.')
    form = ServiceForm(request.POST)
    if form.is_valid():
        service = form.save()
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
@require_POST
def service_toggle_view(request, service_id):
    """Toggle active/inactive status of a service."""
    if not request.user.is_staff:
        raise PermissionDenied('Only staff can manage services.')
    service = get_object_or_404(Service, id=service_id)
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
@require_POST
def booking_action_view(request, booking_id):
    """Confirm, reject, or complete a booking."""
    if not request.user.is_staff:
        raise PermissionDenied('Only staff can manage bookings.')
    booking = get_object_or_404(Booking, id=booking_id)
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
    elif phone_number and request.user.is_staff:
        customer_phone = phone_number.strip()
    else:
        customer_phone = "+919999900001"  # Default test customer number for simulation

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
            external_message_id=f'portal:{request.user.pk}:{request_id}' if request_id else None
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
    messages_qs = conversation.messages.all().order_by('created_at')
    
    svc_info = f" • Service: {conversation.service.name}" if conversation.service else ""
    contact_info = f" ({conversation.service.contact_number})" if conversation.service and conversation.service.contact_number else ""
    
    data = {
        'conversation_id': conversation.id,
        'customer_name': conversation.customer.name or 'Customer',
        'customer_phone': conversation.customer.phone_number,
        'channel': conversation.get_channel_display(),
        'service': f"{conversation.service.name}{contact_info}" if conversation.service else "General AC Inquiries",
        'status': conversation.get_status_display(),
        'handover_required': conversation.status == ConversationStatus.HUMAN_HANDOVER,
        'booking_progress': BookingService.progress(conversation),
        'handoff_summary': conversation.handoff_summary if request.user.is_staff else '',
        'messages': [
            {
                'id': msg.id,
                'direction': msg.direction,
                'sender_type': msg.sender_type,
                'text': display_input(msg.message_text, conversation.customer.preferred_language) if msg.direction == MessageDirection.INBOUND else msg.message_text,
                'status': msg.processing_status,
                'timestamp': timezone.localtime(msg.created_at).strftime("%b %d, %Y %I:%M %p"),
            }
            for msg in messages_qs
        ]
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
@require_POST
@transaction.atomic
def conversation_action_api(request, conversation_id):
    if not request.user.is_staff:
        raise PermissionDenied('Only staff can manage support conversations.')
    conversation = get_object_or_404(Conversation.objects.select_for_update(), pk=conversation_id)
    action = request.POST.get('action')
    if (conversation.assigned_staff_id not in (None, request.user.pk)
            and not (request.user.is_superuser and action in ('release', 'resume'))):
        return JsonResponse({'error': 'Another staff member has picked up this chat. Ask them to release it first.'}, status=409)
    if action == 'claim':
        if conversation.status != ConversationStatus.HUMAN_HANDOVER:
            return JsonResponse({'error': 'Pause the assistant before picking up this conversation.'}, status=400)
        if not conversation.assigned_staff_id:
            conversation.assigned_staff = request.user
            conversation.picked_up_at = timezone.now()
            conversation.save(update_fields=['assigned_staff', 'picked_up_at', 'updated_at'])
        return JsonResponse({'message': 'Conversation picked up.'})
    if action == 'release':
        conversation.assigned_staff = None
        conversation.picked_up_at = None
        conversation.save(update_fields=['assigned_staff', 'picked_up_at', 'updated_at'])
        return JsonResponse({'message': 'Conversation released to the team queue.'})
    if action in ('resume', 'pause'):
        if action == 'pause':
            ConversationService._start_handover(conversation, 'Staff paused the assistant')
        else:
            conversation.status = ConversationStatus.BOT_ACTIVE
            conversation.assigned_staff = None
            conversation.picked_up_at = None
        conversation.unresolved_count = 0
        conversation.save(update_fields=['status', 'unresolved_count', 'assigned_staff', 'picked_up_at', 'updated_at'])
        return JsonResponse({'status': conversation.get_status_display()})
    if action == 'reply':
        from datetime import timedelta
        from django.db import transaction
        from apps.chatbot.models import SenderType, ProcessingStatus
        from apps.whatsapp.models import WhatsAppDelivery
        from apps.whatsapp.delivery import dispatch
        text = request.POST.get('text', '').strip()
        if not text or len(text) > 2000:
            return JsonResponse({'error': 'Enter a reply under 2000 characters.'}, status=400)
        last_inbound = conversation.messages.filter(direction=MessageDirection.INBOUND).order_by('-created_at').first()
        if conversation.channel == ChannelChoice.WHATSAPP and (not last_inbound or last_inbound.created_at < timezone.now() - timedelta(hours=24)):
            return JsonResponse({'error': 'The customer service window has closed. Use an approved template or wait for a customer message.'}, status=400)
        with transaction.atomic():
            message = Message.objects.create(conversation=conversation, direction=MessageDirection.OUTBOUND,
                sender_type=SenderType.HUMAN, message_text=text, processing_status=ProcessingStatus.PROCESSED)
            conversation.status = ConversationStatus.HUMAN_HANDOVER
            if not conversation.assigned_staff_id:
                conversation.assigned_staff = request.user
                conversation.picked_up_at = timezone.now()
            if not conversation.handoff_summary:
                conversation.handoff_summary = ConversationService.generate_handoff_summary(conversation, 'Staff replied')
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=['status', 'last_message_at', 'assigned_staff', 'picked_up_at', 'handoff_summary', 'updated_at'])
            if conversation.channel == ChannelChoice.WHATSAPP:
                delivery = WhatsAppDelivery.objects.create(dedup_key=f'staff:{message.pk}', recipient_phone=conversation.customer.phone_number, payload={'text': text})
                transaction.on_commit(lambda: dispatch(delivery.pk))
        return JsonResponse({'status': conversation.get_status_display(), 'message': 'Reply saved to the conversation.'})
    return JsonResponse({'error': 'Unknown action.'}, status=400)
