import csv
import io
from datetime import timedelta
from decimal import Decimal
import pytest
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client

from apps.tenants.models import Tenant, TenantMembership, MembershipRole, TenantPlan
from apps.chatbot.models import (
    Customer,
    ContactLifecycleStatus,
    ContactSource,
    Conversation,
    ConversationStatus,
    ChannelChoice,
    Message,
    MessageDirection,
    SenderType,
    ProcessingStatus
)
from apps.crm.models import (
    Company,
    Pipeline,
    DealStage,
    Deal,
    DealStageHistory,
    Activity,
    ActivityType,
    ActivityStatus,
    ActivityPriority,
    ContactNote,
    ContactMergeAudit
)
from apps.crm.services import (
    normalize_phone_number,
    find_potential_duplicates,
    merge_contacts,
    change_deal_stage,
    get_customer_timeline,
    get_activities_for_tenant,
    get_crm_metrics,
    sanitize_csv_cell,
    export_contacts_to_csv,
    import_contacts_from_csv
)


@pytest.fixture
def tenant_alpha(db):
    t = Tenant.objects.create(name="Alpha Corp", slug="alpha-corp", plan=TenantPlan.PRO, is_active=True)
    Pipeline.get_or_create_default(t)
    return t


@pytest.fixture
def tenant_beta(db):
    t = Tenant.objects.create(name="Beta Retail", slug="beta-retail", plan=TenantPlan.STARTER, is_active=True)
    Pipeline.get_or_create_default(t)
    return t


@pytest.fixture
def alpha_admin(db, tenant_alpha):
    u = User.objects.create_user(username="alpha_admin", password="password123", email="admin@alpha.com", is_staff=True)
    TenantMembership.objects.create(tenant=tenant_alpha, user=u, role=MembershipRole.ADMIN, is_active=True)
    return u


@pytest.fixture
def beta_admin(db, tenant_beta):
    u = User.objects.create_user(username="beta_admin", password="password123", email="admin@beta.com", is_staff=True)
    TenantMembership.objects.create(tenant=tenant_beta, user=u, role=MembershipRole.ADMIN, is_active=True)
    return u


@pytest.mark.django_db
def test_crm_models_tenant_scoping(tenant_alpha, tenant_beta):
    """Test that default pipelines and stages are automatically provisioned and scoped per tenant."""
    pipe_a = Pipeline.get_or_create_default(tenant_alpha)
    pipe_b = Pipeline.get_or_create_default(tenant_beta)

    assert pipe_a.tenant == tenant_alpha
    assert pipe_b.tenant == tenant_beta
    assert pipe_a.id != pipe_b.id

    # Check default stages
    stages_a = list(pipe_a.stages.all().order_by('order'))
    assert len(stages_a) == 7
    assert stages_a[0].name == "New"
    assert stages_a[-1].is_lost is True
    assert stages_a[-2].is_won is True


@pytest.mark.django_db
def test_cross_tenant_validation_prevents_mismatches(tenant_alpha, tenant_beta, alpha_admin):
    """Ensure related objects from different tenants cannot be mixed."""
    comp_b = Company.objects.create(tenant=tenant_beta, name="Beta Organization")
    cust_b = Customer.objects.create(tenant=tenant_beta, phone_number="+919876543210", name="Beta User")
    cust_a = Customer.objects.create(tenant=tenant_alpha, phone_number="+919876543211", name="Alpha User")
    pipe_a = Pipeline.get_or_create_default(tenant_alpha)
    stage_a = pipe_a.stages.first()

    # 1. Customer on tenant A with company on tenant B
    cust_a.company = comp_b
    with pytest.raises(ValidationError):
        cust_a.clean()

    # 2. Deal on tenant A with contact on tenant B
    deal_invalid_contact = Deal(
        tenant=tenant_alpha,
        pipeline=pipe_a,
        stage=stage_a,
        contact=cust_b,
        title="Cross-Tenant Deal 1"
    )
    with pytest.raises(ValidationError):
        deal_invalid_contact.clean()

    # 3. Deal on tenant A with company on tenant B
    deal_invalid_comp = Deal(
        tenant=tenant_alpha,
        pipeline=pipe_a,
        stage=stage_a,
        contact=cust_a,
        company=comp_b,
        title="Cross-Tenant Deal 2"
    )
    with pytest.raises(ValidationError):
        deal_invalid_comp.clean()

    # 4. Activity on tenant A with contact on tenant B
    act_invalid = Activity(
        tenant=tenant_alpha,
        contact=cust_b,
        title="Cross-Tenant Task",
        due_date=timezone.now() + timedelta(days=1)
    )
    with pytest.raises(ValidationError):
        act_invalid.clean()


@pytest.mark.django_db
def test_phone_normalization():
    """Verify phone numbers are normalized reliably into international E.164 formats."""
    assert normalize_phone_number("9876543210") == "+919876543210"
    assert normalize_phone_number(" 09876543210 ") == "+919876543210"
    assert normalize_phone_number("+91 98765-43210") == "+919876543210"
    assert normalize_phone_number("+1 (555) 123-4567") == "+15551234567"
    assert normalize_phone_number("invalid-phone") == "invalid-phone"


@pytest.mark.django_db
def test_duplicate_detection_and_merge(tenant_alpha, tenant_beta, alpha_admin):
    """Test finding duplicates by phone/email and performing audited transactional consolidation."""
    # Create primary and secondary duplicate in tenant A
    primary = Customer.objects.create(
        tenant=tenant_alpha,
        phone_number="+919876543210",
        name="John Doe",
        email="john@doe.com",
        tags=["lead"]
    )
    duplicate = Customer.objects.create(
        tenant=tenant_alpha,
        phone_number="+919876543219",
        name="J. Doe",
        email="john@doe.com",
        tags=["vip"]
    )

    # Secondary in tenant B with matching email must NOT be found as duplicate for tenant A
    Customer.objects.create(
        tenant=tenant_beta,
        phone_number="+919876543210",
        name="Beta John",
        email="john@doe.com"
    )

    dups = find_potential_duplicates(tenant_alpha, email="john@doe.com", exclude_contact_id=primary.id)
    assert len(dups) == 1
    assert dups[0].id == duplicate.id

    # Create associated deal and activity for duplicate
    pipe = Pipeline.get_or_create_default(tenant_alpha)
    deal = Deal.objects.create(
        tenant=tenant_alpha,
        contact=duplicate,
        pipeline=pipe,
        stage=pipe.stages.first(),
        title="Old Deal"
    )
    act = Activity.objects.create(
        tenant=tenant_alpha,
        contact=duplicate,
        title="Old Follow-up",
        due_date=timezone.now() + timedelta(days=2)
    )
    note = ContactNote.objects.create(
        tenant=tenant_alpha,
        contact=duplicate,
        author=alpha_admin,
        content="Important background info"
    )

    # Perform transactional merge
    dup_id = duplicate.id
    merged = merge_contacts(tenant_alpha, primary, duplicate, performed_by=alpha_admin)
    assert merged.id == primary.id
    assert "vip" in merged.tags

    # Verify associations were transferred
    deal.refresh_from_db()
    act.refresh_from_db()
    note.refresh_from_db()
    assert deal.contact_id == primary.id
    assert act.contact_id == primary.id
    assert note.contact_id == primary.id

    # Verify duplicate record is removed and audit log is created
    assert not Customer.objects.filter(id=dup_id).exists()
    audit = ContactMergeAudit.objects.filter(tenant=tenant_alpha, primary_contact=primary).first()
    assert audit is not None
    assert audit.details['duplicate_id'] == dup_id
    assert audit.merged_phone == "+919876543219"
    assert audit.performed_by == alpha_admin


@pytest.mark.django_db
def test_deal_stage_transition_and_history(tenant_alpha, alpha_admin):
    """Test moving deal through sales stages with history recording, won, and lost semantics."""
    pipe = Pipeline.get_or_create_default(tenant_alpha)
    stages = list(pipe.stages.all().order_by('order'))
    st_initial = stages[0]
    st_qualified = stages[1]
    st_won = next(s for s in stages if s.is_won)
    st_lost = next(s for s in stages if s.is_lost)

    contact = Customer.objects.create(tenant=tenant_alpha, phone_number="+919876543210", name="Lead A")
    deal = Deal.objects.create(
        tenant=tenant_alpha,
        pipeline=pipe,
        stage=st_initial,
        contact=contact,
        title="Custom ERP Setup",
        amount=Decimal("120000.00"),
        currency="INR"
    )

    # 1. Advance to Qualified
    updated = change_deal_stage(deal.id, st_qualified.id, user=alpha_admin, notes="Requirements verified")
    assert updated.stage_id == st_qualified.id
    assert updated.probability == st_qualified.probability
    assert DealStageHistory.objects.filter(deal=deal, to_stage=st_qualified).count() == 1

    # 2. Advance to Closed Lost
    updated = change_deal_stage(deal.id, st_lost.id, user=alpha_admin, lost_reason="Budget reduced")
    assert updated.stage_id == st_lost.id
    assert updated.lost_at is not None
    assert updated.lost_reason == "Budget reduced"

    # 3. Advance to Closed Won
    updated = change_deal_stage(deal.id, st_won.id, user=alpha_admin, notes="Client signed contract")
    assert updated.stage_id == st_won.id
    assert updated.won_at is not None
    assert updated.lost_reason == ""


@pytest.mark.django_db
def test_activity_due_dates_and_overdue(tenant_alpha, alpha_admin):
    """Test overdue activity calculations and completion state."""
    contact = Customer.objects.create(tenant=tenant_alpha, phone_number="+919876543210", name="Lead B")

    # Past task (overdue)
    past_act = Activity.objects.create(
        tenant=tenant_alpha,
        contact=contact,
        title="Call client yesterday",
        due_date=timezone.now() - timedelta(hours=5),
        status=ActivityStatus.PENDING,
        assigned_to=alpha_admin
    )
    assert past_act.is_overdue is True

    # Future task
    future_act = Activity.objects.create(
        tenant=tenant_alpha,
        contact=contact,
        title="Demo next week",
        due_date=timezone.now() + timedelta(days=5),
        status=ActivityStatus.PENDING,
        assigned_to=alpha_admin
    )
    assert future_act.is_overdue is False

    # Mark completed
    past_act.mark_completed(alpha_admin)
    past_act.save()
    assert past_act.status == ActivityStatus.COMPLETED
    assert past_act.completed_at is not None
    assert past_act.completed_by == alpha_admin
    assert past_act.is_overdue is False

    # Activity filtering service
    my_tasks = get_activities_for_tenant(tenant_alpha, user=alpha_admin, filter_view='my_tasks')
    assert future_act in my_tasks
    assert past_act not in my_tasks

    completed_tasks = get_activities_for_tenant(tenant_alpha, user=alpha_admin, filter_view='completed')
    assert past_act in completed_tasks


@pytest.mark.django_db
def test_unified_customer_timeline(tenant_alpha, alpha_admin):
    """Test timeline aggregation across messages, notes, activities, and deals."""
    contact = Customer.objects.create(tenant=tenant_alpha, phone_number="+919876543210", name="Prospect C")
    conv = Conversation.objects.create(tenant=tenant_alpha, customer=contact, channel=ChannelChoice.WHATSAPP)
    
    # Message
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        sender_type=SenderType.CUSTOMER,
        message_text="Hello, what is TABLO pricing?",
        processing_status=ProcessingStatus.PROCESSED
    )
    # Note
    ContactNote.objects.create(tenant=tenant_alpha, contact=contact, author=alpha_admin, content="Needs quotation for 3 outlets")
    # Deal
    pipe = Pipeline.get_or_create_default(tenant_alpha)
    deal = Deal.objects.create(tenant=tenant_alpha, contact=contact, pipeline=pipe, stage=pipe.stages.first(), title="TABLO Multi-outlet")
    # Activity
    Activity.objects.create(tenant=tenant_alpha, contact=contact, title="Prepare proposal", due_date=timezone.now() + timedelta(days=1))

    timeline = get_customer_timeline(contact, page=1, page_size=10)
    assert timeline['total_count'] >= 4
    event_types = [item['event_type'] for item in timeline['items']]
    assert 'message' in event_types
    assert 'note' in event_types
    assert 'deal' in event_types
    assert 'activity' in event_types


@pytest.mark.django_db
def test_csv_export_injection_protection(tenant_alpha):
    """Test that CSV cell values starting with =, +, -, @ are escaped to prevent formula injection."""
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert sanitize_csv_cell("-123") == "'-123"
    assert sanitize_csv_cell("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_csv_cell("Normal Text") == "Normal Text"

    Customer.objects.create(
        tenant=tenant_alpha,
        name="=HYPERLINK(\"http://malicious.site\",\"Click Me\")",
        phone_number="+919999988888",
        email="test@example.com",
        notes="@DDEExec"
    )

    csv_data = export_contacts_to_csv(tenant_alpha)
    assert "'=HYPERLINK" in csv_data
    assert "'@DDEExec" in csv_data


@pytest.mark.django_db
def test_csv_import_validation_and_preview(tenant_alpha):
    """Test previewing and executing CSV contact imports with row errors and duplicate policies."""
    csv_content = """name,phone_number,email,company,lifecycle_status,source,tags
Alice Smith,+919876543201,alice@example.com,Acme Labs,LEAD,WEBSITE,"prospect, web"
Bob Jones,invalid-phone,bob@example.com,Bob Co,SQL,REFERRAL,vip
Charlie Brown,+919876543203,,Charlie Inc,CUSTOMER,MANUAL,client
"""
    # 1. Preview Only
    preview_res = import_contacts_from_csv(tenant_alpha, csv_content, preview_only=True)
    assert preview_res['total_rows'] == 3
    assert preview_res['valid_rows_count'] == 2
    assert preview_res['invalid_rows_count'] == 1
    assert preview_res['errors'][0]['row'] == 3  # Bob Jones invalid phone
    # Nothing committed
    assert Customer.objects.filter(tenant=tenant_alpha).count() == 0

    # 2. Execute Import with Skip
    exec_res = import_contacts_from_csv(tenant_alpha, csv_content, preview_only=False, duplicate_action='skip')
    assert exec_res['imported_count'] == 2
    assert Customer.objects.filter(tenant=tenant_alpha, phone_number="+919876543201").exists()
    assert Company.objects.filter(tenant=tenant_alpha, name="Acme Labs").exists()


@pytest.mark.django_db
def test_crm_views_and_tenant_isolation(client, tenant_alpha, tenant_beta, alpha_admin, beta_admin):
    """Test full view authorization, navigation, and cross-tenant data isolation."""
    # Create contact in tenant A
    cust_a = Customer.objects.create(tenant=tenant_alpha, phone_number="+919876543210", name="Alpha Secret Lead")
    pipe_a = Pipeline.get_or_create_default(tenant_alpha)
    deal_a = Deal.objects.create(tenant=tenant_alpha, contact=cust_a, pipeline=pipe_a, stage=pipe_a.stages.first(), title="Alpha Big Deal")

    # 1. Unauthenticated request redirects to login
    resp = client.get("/crm/")
    assert resp.status_code == 302
    assert "login" in resp.url

    # 2. Login as Alpha Admin
    client.force_login(alpha_admin)
    # Set session tenant
    session = client.session
    session['active_tenant_id'] = tenant_alpha.id
    session.save()

    resp = client.get("/crm/")
    assert resp.status_code == 302 and resp.url == "/app/work-queue"

    resp = client.get("/crm/contacts/")
    assert resp.status_code == 302 and resp.url == "/app/contacts"
    data=client.get("/api/crm/contacts/")
    assert data.status_code==200 and "Alpha Secret Lead" in data.content.decode()

    # 3. Switch login to Beta Admin
    client.force_login(beta_admin)
    session = client.session
    session['active_tenant_id'] = tenant_beta.id
    session.save()

    # Beta admin must NOT see Alpha's lead or deal
    resp = client.get("/crm/contacts/")
    assert resp.status_code == 302 and resp.url == "/app/contacts"
    data=client.get("/api/crm/contacts/")
    assert data.status_code==200 and "Alpha Secret Lead" not in data.content.decode()

    # Beta admin attempting to view Alpha contact detail gets 404
    resp = client.get(f"/crm/contacts/{cust_a.id}/")
    assert resp.status_code == 404

    # Beta admin attempting to move Alpha deal gets 404
    resp = client.post(f"/crm/deals/{deal_a.id}/move/", {'stage_id': pipe_a.stages.last().id})
    assert resp.status_code == 404
