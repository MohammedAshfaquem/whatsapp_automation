import json
import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from apps.tenants.context import user_can_manage_tenant
from apps.tenants.capabilities import require_capability
from apps.chatbot.models import Customer, Conversation, ConversationStatus, ChannelChoice, Message, MessageDirection, SenderType, ProcessingStatus
from apps.whatsapp.models import WhatsAppDelivery
from apps.whatsapp.delivery import dispatch
from apps.whatsapp.whatsapp_client import WhatsAppClient
from .models import (
    Company,
    Pipeline,
    DealStage,
    Deal,
    DealStageHistory,
    Activity,
    ActivityType,
    ActivityStatus,
    ActivityPriority,
    ContactNote
)
from .forms import (
    ContactForm,
    CompanyForm,
    DealForm,
    ActivityForm,
    ContactNoteForm,
    ContactImportForm
)
from .services import (
    get_crm_metrics,
    get_customer_timeline,
    get_activities_for_tenant,
    change_deal_stage,
    export_contacts_to_csv,
    import_contacts_from_csv,
    find_potential_duplicates,
    merge_contacts,
    normalize_phone_number
)

logger = logging.getLogger(__name__)


def get_active_tenant(request):
    """Resolve active tenant or raise PermissionDenied."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        raise PermissionDenied("An active workspace is required to access the CRM module.")
    return tenant


# ========================================================
# 1. CRM OVERVIEW & ANALYTICS
# ========================================================
@login_required(login_url='login')
@require_capability('contacts', 'view')
def crm_overview_view(request):
    tenant = get_active_tenant(request)
    metrics = get_crm_metrics(tenant)
    recent_activities = Activity.objects.filter(tenant=tenant).select_related('contact', 'assigned_to').order_by('due_date')[:8]
    recent_deals = Deal.objects.filter(tenant=tenant).select_related('contact', 'stage', 'owner').order_by('-updated_at')[:8]

    context = {
        'tenant': tenant,
        'metrics': metrics,
        'recent_activities': recent_activities,
        'recent_deals': recent_deals,
        'can_manage': request.user.is_superuser or user_can_manage_tenant(request.user, tenant),
    }
    return render(request, 'crm/overview.html', context)


# ========================================================
# 2. CONTACTS (CUSTOMERS)
# ========================================================
@login_required(login_url='login')
@require_capability('contacts', 'view')
def contact_list_view(request):
    tenant = get_active_tenant(request)
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    owner_filter = request.GET.get('owner', '').strip()

    qs = Customer.objects.filter(tenant=tenant).select_related('company', 'owner').order_by('-updated_at')

    if search_query:
        qs = qs.filter(
            Q(name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(company__name__icontains=search_query)
        )
    if status_filter:
        qs = qs.filter(lifecycle_status=status_filter)
    if owner_filter:
        qs = qs.filter(owner__username=owner_filter)

    paginator = Paginator(qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    tenant_members = tenant.memberships.filter(is_active=True).select_related('user')

    context = {
        'tenant': tenant,
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'owner_filter': owner_filter,
        'tenant_members': tenant_members,
        'total_contacts': paginator.count,
        'can_manage': request.user.is_superuser or user_can_manage_tenant(request.user, tenant),
    }
    return render(request, 'crm/contact_list.html', context)


@login_required(login_url='login')
@require_capability('contacts', 'create')
def contact_create_view(request):
    tenant = get_active_tenant(request)
    if tenant and not tenant.can_add_contact():
        messages.error(request, f"Contact limit reached ({tenant.effective_max_contacts} contacts) for your current plan. Please upgrade to add more contacts.")
        return redirect('crm-contact-list')

    if request.method == 'POST':
        form = ContactForm(request.POST, tenant=tenant)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.tenant = tenant
            contact.phone_number = normalize_phone_number(contact.phone_number)
            contact.tags = form.cleaned_data.get('tags_string', [])
            contact.save()
            messages.success(request, f"Contact '{contact.name or contact.phone_number}' created successfully.")
            return redirect('crm-contact-detail', contact_id=contact.id)
    else:
        form = ContactForm(tenant=tenant)

    return render(request, 'crm/contact_form.html', {'tenant': tenant, 'form': form, 'is_new': True})


@login_required(login_url='login')
@require_capability('contacts', 'edit')
def contact_edit_view(request, contact_id):
    tenant = get_active_tenant(request)
    contact = get_object_or_404(Customer, id=contact_id, tenant=tenant)

    if request.method == 'POST':
        form = ContactForm(request.POST, instance=contact, tenant=tenant)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.phone_number = normalize_phone_number(contact.phone_number)
            contact.tags = form.cleaned_data.get('tags_string', [])
            contact.save()
            messages.success(request, f"Contact '{contact.name or contact.phone_number}' updated.")
            return redirect('crm-contact-detail', contact_id=contact.id)
    else:
        form = ContactForm(instance=contact, tenant=tenant)

    return render(request, 'crm/contact_form.html', {'tenant': tenant, 'form': form, 'contact': contact, 'is_new': False})


@login_required(login_url='login')
@require_capability('contacts', 'view')
def contact_detail_view(request, contact_id):
    tenant = get_active_tenant(request)
    contact = get_object_or_404(
        Customer.objects.select_related('company', 'owner').prefetch_related('deals__stage', 'activities'),
        id=contact_id,
        tenant=tenant
    )

    page_num = int(request.GET.get('page', 1))
    timeline_data = get_customer_timeline(contact, page=page_num, page_size=25)
    note_form = ContactNoteForm()
    activity_form = ActivityForm(tenant=tenant, initial={'contact': contact})
    deal_form = DealForm(tenant=tenant, initial={'contact': contact, 'company': contact.company})

    # Check for potential duplicates
    duplicates = find_potential_duplicates(tenant, phone=contact.phone_number, email=contact.email, exclude_contact_id=contact.id)

    # 24h WhatsApp Service Window Check
    last_inbound = Message.objects.filter(
        conversation__customer=contact,
        direction=MessageDirection.INBOUND
    ).order_by('-created_at').first()
    is_window_open = bool(last_inbound and (timezone.now() - last_inbound.created_at).total_seconds() <= 86400)

    context = {
        'tenant': tenant,
        'contact': contact,
        'timeline': timeline_data,
        'note_form': note_form,
        'activity_form': activity_form,
        'deal_form': deal_form,
        'duplicates': duplicates,
        'is_window_open': is_window_open,
        'last_inbound_time': last_inbound.created_at if last_inbound else None,
        'can_manage': request.user.is_superuser or user_can_manage_tenant(request.user, tenant),
    }
    return render(request, 'crm/contact_detail.html', context)


@login_required(login_url='login')
@require_POST
@require_capability('contacts', 'edit')
def contact_note_create_view(request, contact_id):
    tenant = get_active_tenant(request)
    contact = get_object_or_404(Customer, id=contact_id, tenant=tenant)
    form = ContactNoteForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.tenant = tenant
        note.contact = contact
        note.author = request.user
        note.save()
        messages.success(request, "Internal note saved.")
    else:
        messages.error(request, "Note content cannot be empty.")
    return redirect('crm-contact-detail', contact_id=contact.id)


@login_required(login_url='login')
@require_POST
@require_capability('contacts', 'view')
def contact_send_message_view(request, contact_id):
    """Legacy composer is read-only; all sends use the protected workspace."""
    tenant = get_active_tenant(request)
    get_object_or_404(Customer, id=contact_id, tenant=tenant)
    messages.info(request, 'Use the WhatsApp Workspace to claim a chat and send messages safely.')
    return redirect('/app/inbox')


@login_required(login_url='login')
@require_POST
@require_capability('contacts', 'edit')
def contact_merge_view(request, contact_id):
    tenant = get_active_tenant(request)
    if not (request.user.is_superuser or user_can_manage_tenant(request.user, tenant)):
        raise PermissionDenied("Only administrators can merge contact records.")

    primary_contact = get_object_or_404(Customer, id=contact_id, tenant=tenant)
    duplicate_id = request.POST.get('duplicate_id')
    duplicate_contact = get_object_or_404(Customer, id=duplicate_id, tenant=tenant)

    try:
        merged = merge_contacts(tenant, primary_contact, duplicate_contact, performed_by=request.user)
        messages.success(request, f"Successfully merged contact {duplicate_contact.phone_number} into {merged.name or merged.phone_number}.")
    except Exception as e:
        messages.error(request, f"Error merging contacts: {e}")

    return redirect('crm-contact-detail', contact_id=primary_contact.id)


@login_required(login_url='login')
@require_capability('contacts', 'export')
def contact_export_view(request):
    tenant = get_active_tenant(request)
    if not (request.user.is_superuser or user_can_manage_tenant(request.user, tenant)):
        raise PermissionDenied("Only administrators can export contact data.")

    csv_data = export_contacts_to_csv(tenant)
    filename = f"contacts_{tenant.slug}_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
    response = HttpResponse(csv_data, content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required(login_url='login')
@require_capability('contacts', 'import')
def contact_import_view(request):
    tenant = get_active_tenant(request)
    if not (request.user.is_superuser or user_can_manage_tenant(request.user, tenant)):
        raise PermissionDenied("Only administrators can import contact data.")

    import_result = None
    if request.method == 'POST':
        form = ContactImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            duplicate_action = form.cleaned_data['duplicate_action']
            is_preview = 'preview' in request.POST
            try:
                content = csv_file.read().decode('utf-8-sig')
                import_result = import_contacts_from_csv(
                    tenant=tenant,
                    file_content=content,
                    preview_only=is_preview,
                    duplicate_action=duplicate_action
                )
                if not is_preview and import_result.get('success'):
                    messages.success(
                        request,
                        f"Import complete! {import_result['imported_count']} contacts created, {import_result['updated_count']} updated, {import_result['skipped_count']} skipped."
                    )
                    return redirect('crm-contact-list')
            except Exception as e:
                messages.error(request, f"Could not read CSV file: {e}")
    else:
        form = ContactImportForm()

    return render(request, 'crm/contact_import.html', {'tenant': tenant, 'form': form, 'result': import_result})


# ========================================================
# 3. COMPANIES (ORGANIZATIONS)
# ========================================================
@login_required(login_url='login')
@require_capability('companies', 'view')
def company_list_view(request):
    tenant = get_active_tenant(request)
    search_query = request.GET.get('q', '').strip()
    qs = Company.objects.filter(tenant=tenant).prefetch_related('contacts', 'deals').order_by('name')

    if search_query:
        qs = qs.filter(Q(name__icontains=search_query) | Q(domain__icontains=search_query) | Q(industry__icontains=search_query))

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'crm/company_list.html', {
        'tenant': tenant,
        'page_obj': page_obj,
        'search_query': search_query,
        'total_companies': paginator.count,
    })


@login_required(login_url='login')
@require_capability('companies', 'create')
def company_create_view(request):
    tenant = get_active_tenant(request)
    if request.method == 'POST':
        form = CompanyForm(request.POST, tenant=tenant)
        if form.is_valid():
            company = form.save(commit=False)
            company.tenant = tenant
            company.save()
            messages.success(request, f"Company '{company.name}' created.")
            return redirect('crm-company-detail', company_id=company.id)
    else:
        form = CompanyForm(tenant=tenant)
    return render(request, 'crm/company_form.html', {'tenant': tenant, 'form': form, 'is_new': True})


@login_required(login_url='login')
@require_capability('companies', 'view')
def company_detail_view(request, company_id):
    tenant = get_active_tenant(request)
    company = get_object_or_404(
        Company.objects.prefetch_related('contacts', 'deals__stage', 'activities'),
        id=company_id,
        tenant=tenant
    )
    return render(request, 'crm/company_detail.html', {'tenant': tenant, 'company': company})


# ========================================================
# 4. SALES PIPELINES & DEALS
# ========================================================
@login_required(login_url='login')
@require_capability('deals', 'view')
def deal_board_view(request):
    tenant = get_active_tenant(request)
    pipeline_id = request.GET.get('pipeline_id')

    pipelines = Pipeline.objects.filter(tenant=tenant, is_active=True)
    if pipeline_id:
        active_pipeline = get_object_or_404(Pipeline, id=pipeline_id, tenant=tenant)
    else:
        active_pipeline = Pipeline.get_or_create_default(tenant)

    stages = list(active_pipeline.stages.all().order_by('order'))
    deals = Deal.objects.filter(tenant=tenant, pipeline=active_pipeline).select_related('contact', 'company', 'owner', 'stage').order_by('-updated_at')

    # Group deals by stage
    board_data = []
    for stage in stages:
        stage_deals = [d for d in deals if d.stage_id == stage.id]
        total_val = sum((d.amount or Decimal('0.00')) for d in stage_deals)
        board_data.append({
            'stage': stage,
            'deals': stage_deals,
            'count': len(stage_deals),
            'total_value': total_val,
        })

    context = {
        'tenant': tenant,
        'pipelines': pipelines,
        'active_pipeline': active_pipeline,
        'board_data': board_data,
        'all_stages': stages,
        'can_manage': request.user.is_superuser or user_can_manage_tenant(request.user, tenant),
    }
    return render(request, 'crm/deal_board.html', context)


@login_required(login_url='login')
@require_capability('deals', 'view')
def deal_list_view(request):
    tenant = get_active_tenant(request)
    deals = Deal.objects.filter(tenant=tenant).select_related('contact', 'company', 'owner', 'stage', 'pipeline').order_by('-updated_at')

    paginator = Paginator(deals, 30)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'crm/deal_list.html', {
        'tenant': tenant,
        'page_obj': page_obj,
        'total_deals': paginator.count,
    })


@login_required(login_url='login')
@require_capability('deals', 'create')
def deal_create_view(request):
    tenant = get_active_tenant(request)
    initial_contact_id = request.GET.get('contact_id')
    initial_data = {}
    if initial_contact_id:
        contact = get_object_or_404(Customer, id=initial_contact_id, tenant=tenant)
        initial_data['contact'] = contact
        if contact.company:
            initial_data['company'] = contact.company
        initial_data['title'] = f"Opportunity - {contact.name or contact.phone_number}"

    # Default to default pipeline & first stage
    default_pipe = Pipeline.get_or_create_default(tenant)
    initial_data['pipeline'] = default_pipe
    first_stage = default_pipe.stages.first()
    if first_stage:
        initial_data['stage'] = first_stage

    if request.method == 'POST':
        form = DealForm(request.POST, tenant=tenant)
        if form.is_valid():
            deal = form.save(commit=False)
            deal.tenant = tenant
            deal.save()
            DealStageHistory.objects.create(
                deal=deal,
                from_stage=None,
                to_stage=deal.stage,
                changed_by=request.user,
                notes="Deal created"
            )
            messages.success(request, f"Deal '{deal.title}' created.")
            return redirect('crm-deal-detail', deal_id=deal.id)
    else:
        form = DealForm(tenant=tenant, initial=initial_data)

    return render(request, 'crm/deal_form.html', {'tenant': tenant, 'form': form, 'is_new': True})


@login_required(login_url='login')
@require_capability('deals', 'view')
def deal_detail_view(request, deal_id):
    tenant = get_active_tenant(request)
    deal = get_object_or_404(
        Deal.objects.select_related('contact', 'company', 'owner', 'pipeline', 'stage', 'product', 'service')
        .prefetch_related('stage_history__from_stage', 'stage_history__to_stage', 'activities'),
        id=deal_id,
        tenant=tenant
    )
    available_stages = deal.pipeline.stages.all().order_by('order')
    activity_form = ActivityForm(tenant=tenant, initial={'deal': deal, 'contact': deal.contact, 'company': deal.company})

    return render(request, 'crm/deal_detail.html', {
        'tenant': tenant,
        'deal': deal,
        'available_stages': available_stages,
        'activity_form': activity_form,
    })


@login_required(login_url='login')
@require_POST
@require_capability('deals', 'change_stage')
def deal_move_stage_api(request, deal_id):
    tenant = get_active_tenant(request)
    new_stage_id = request.POST.get('stage_id')
    lost_reason = request.POST.get('lost_reason', '')
    notes = request.POST.get('notes', '')

    deal = get_object_or_404(Deal, id=deal_id, tenant=tenant)
    try:
        updated_deal = change_deal_stage(
            deal_id=deal.id,
            new_stage_id=int(new_stage_id),
            user=request.user,
            notes=notes,
            lost_reason=lost_reason
        )
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return JsonResponse({
                'success': True,
                'deal_id': updated_deal.id,
                'stage_name': updated_deal.stage.name,
                'is_won': updated_deal.stage.is_won,
                'is_lost': updated_deal.stage.is_lost,
            })
        messages.success(request, f"Moved '{deal.title}' to {updated_deal.stage.name}.")
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
        messages.error(request, f"Error moving deal stage: {e}")

    return redirect('crm-deal-detail', deal_id=deal.id)


# ========================================================
# 5. TASKS & ACTIVITIES
# ========================================================
@login_required(login_url='login')
@require_capability('tasks', 'view')
def activity_list_view(request):
    tenant = get_active_tenant(request)
    view_filter = request.GET.get('filter', 'my_tasks')

    activities = get_activities_for_tenant(tenant, user=request.user, filter_view=view_filter)
    paginator = Paginator(activities, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'crm/activity_list.html', {
        'tenant': tenant,
        'page_obj': page_obj,
        'view_filter': view_filter,
        'total_activities': paginator.count,
    })


@login_required(login_url='login')
@require_POST
@require_capability('tasks', 'create')
def activity_create_view(request):
    tenant = get_active_tenant(request)
    form = ActivityForm(request.POST, tenant=tenant)
    if form.is_valid():
        act = form.save(commit=False)
        act.tenant = tenant
        act.created_by = request.user
        act.save()
        messages.success(request, f"Activity '{act.title}' added.")
    else:
        error_msgs = "; ".join([f"{k}: {', '.join(v)}" for k, v in form.errors.items()])
        messages.error(request, f"Could not create task: {error_msgs}")

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'crm-activity-list'
    return redirect(next_url)


@login_required(login_url='login')
@require_POST
@require_capability('tasks', 'complete')
def activity_toggle_api(request, activity_id):
    tenant = get_active_tenant(request)
    activity = get_object_or_404(Activity, id=activity_id, tenant=tenant)

    if activity.status == ActivityStatus.COMPLETED:
        activity.status = ActivityStatus.PENDING
        activity.completed_at = None
        activity.completed_by = None
    else:
        activity.mark_completed(user=request.user)
    activity.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'status': activity.status})

    messages.success(request, f"Updated task status to {activity.get_status_display()}.")
    return redirect(request.META.get('HTTP_REFERER') or 'crm-activity-list')


# ========================================================
# 6. CRM SETTINGS (PIPELINES & STAGES)
# ========================================================
@login_required(login_url='login')
@require_capability('deals', 'edit')
def crm_settings_view(request):
    tenant = get_active_tenant(request)
    if not (request.user.is_superuser or user_can_manage_tenant(request.user, tenant)):
        raise PermissionDenied("Only administrators can manage CRM pipeline settings.")

    pipelines = Pipeline.objects.filter(tenant=tenant).prefetch_related('stages')
    return render(request, 'crm/settings.html', {
        'tenant': tenant,
        'pipelines': pipelines,
    })
