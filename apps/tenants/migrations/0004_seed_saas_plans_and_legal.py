from django.db import migrations
from django.utils import timezone


def seed_plans_legal_and_subscriptions(apps, schema_editor):
    PlanTier = apps.get_model('tenants', 'PlanTier')
    Tenant = apps.get_model('tenants', 'Tenant')
    TenantSubscription = apps.get_model('tenants', 'TenantSubscription')
    LegalDocument = apps.get_model('tenants', 'LegalDocument')
    OnboardingProgress = apps.get_model('tenants', 'OnboardingProgress')

    # 1. Seed Plan Tiers (Contact Sales default, honest feature allocations)
    basic_plan, _ = PlanTier.objects.get_or_create(
        code='basic',
        defaults={
            'name': 'Basic',
            'badge': 'Startups',
            'description': 'Essential WhatsApp shared inbox and contact management for small teams.',
            'price_display_mode': 'CONTACT_SALES',
            'currency': 'INR',
            'is_published': True,
            'is_featured': False,
            'ordering': 1,
            'max_staff': 2,
            'max_contacts': 1000,
            'max_services': 5,
            'max_documents': 5,
            'monthly_message_allowance': 1000,
            'ai_assistant_enabled': False,
            'crm_enabled': True,
            'enabled_modules': [
                'shared_inbox', 'team_management', 'contacts_companies',
                'reports', 'demo_scheduling'
            ]
        }
    )

    growth_plan, _ = PlanTier.objects.get_or_create(
        code='growth',
        defaults={
            'name': 'Growth',
            'badge': 'Most Popular',
            'description': 'Full sales CRM pipelines, lead qualification, and Gemini AI assistant.',
            'price_display_mode': 'CONTACT_SALES',
            'currency': 'INR',
            'is_published': True,
            'is_featured': True,
            'ordering': 2,
            'max_staff': 5,
            'max_contacts': 5000,
            'max_services': 15,
            'max_documents': 20,
            'monthly_message_allowance': 5000,
            'ai_assistant_enabled': True,
            'crm_enabled': True,
            'enabled_modules': [
                'shared_inbox', 'team_management', 'contacts_companies',
                'deals_pipelines', 'tasks_followups', 'ai_assistant',
                'qualification_scoring', 'demo_scheduling', 'reports'
            ]
        }
    )

    pro_plan, _ = PlanTier.objects.get_or_create(
        code='pro',
        defaults={
            'name': 'Pro',
            'badge': 'Scaling Teams',
            'description': 'High-capacity sales workspace with custom pipelines, templates, and API access.',
            'price_display_mode': 'CONTACT_SALES',
            'currency': 'INR',
            'is_published': True,
            'is_featured': False,
            'ordering': 3,
            'max_staff': 15,
            'max_contacts': 25000,
            'max_services': 50,
            'max_documents': 100,
            'monthly_message_allowance': 25000,
            'ai_assistant_enabled': True,
            'crm_enabled': True,
            'enabled_modules': [
                'shared_inbox', 'team_management', 'contacts_companies',
                'deals_pipelines', 'tasks_followups', 'ai_assistant',
                'qualification_scoring', 'demo_scheduling', 'reports',
                'whatsapp_templates', 'apis_webhooks', 'whatsapp_forms',
                'campaigns_broadcasts'
            ]
        }
    )

    enterprise_plan, _ = PlanTier.objects.get_or_create(
        code='enterprise',
        defaults={
            'name': 'Enterprise',
            'badge': 'Custom',
            'description': 'Tailored team seats, dedicated database grounding, and custom SLAs.',
            'price_display_mode': 'CUSTOM_QUOTE',
            'currency': 'INR',
            'is_published': True,
            'is_featured': False,
            'ordering': 4,
            'max_staff': 50,
            'max_contacts': 100000,
            'max_services': 100,
            'max_documents': 500,
            'monthly_message_allowance': 100000,
            'ai_assistant_enabled': True,
            'crm_enabled': True,
            'enabled_modules': [
                'shared_inbox', 'team_management', 'contacts_companies',
                'deals_pipelines', 'tasks_followups', 'ai_assistant',
                'qualification_scoring', 'demo_scheduling', 'reports',
                'whatsapp_templates', 'apis_webhooks', 'whatsapp_forms',
                'campaigns_broadcasts'
            ]
        }
    )

    # 2. Seed Published Legal Documents (Terms of Service & Privacy Policy)
    terms_content = """# Neoriz WhatsApp Automation - Terms of Service
**Version 1.0 | Effective Date: November 22, 2026**

### 1. Acceptance of Terms
By creating an account or accessing the Neoriz WhatsApp Automation platform provided by Neoriz Solutions, you agree to comply with and be bound by these Terms of Service.

### 2. Multi-Tenant SaaS Workspace & Roles
- **Account Responsibilities**: Each tenant workspace is managed by designated Owner and Administrator roles. You are responsible for safeguarding your credentials.
- **Seat Allocation**: Seat limits apply to all team members including Owners and Administrators.
- **Data Isolation**: Your customer conversations, contacts, deals, and configurations are strictly isolated to your tenant workspace.

### 3. Meta WhatsApp Business API & Messaging Charges
- **Platform Subscription**: Platform fees cover access to the software workspace, multi-agent inbox, CRM, and AI grounding.
- **Third-Party Messaging Fees**: Messaging fees incurred through Meta's official WhatsApp Business Cloud API are determined by Meta's conversation categories and regional pricing schedule.
- **Compliance**: You agree to adhere to Meta's Commerce and Messaging Policies. Unsolicited spam, bulk harassment, or unauthorized promotional messaging is strictly prohibited.

### 4. Service Availability & Activation
- New self-signup workspaces undergo an administrative review and activation process before outbound live messaging is enabled.
- Neoriz Solutions reserves the right to suspend any workspace that violates messaging compliance rules or attempts cross-tenant tampering.
"""

    privacy_content = """# Neoriz WhatsApp Automation - Privacy Policy
**Version 1.0 | Effective Date: November 22, 2026**

### 1. Information We Collect
- **Account Data**: Name, work email address, business name, and contact details collected during registration.
- **Workspace Data**: Customer contacts, conversational text, sales deals, and notes stored on behalf of your business.
- **Usage Metrics**: Activity logs, login timestamps, and system delivery logs used for security auditing.

### 2. How Information is Used
- To provide multi-agent shared inbox, CRM pipelines, and AI conversational assistance.
- To route incoming and outgoing WhatsApp messages via Meta's official Cloud API.
- We do not sell, rent, or monetize your workspace data, customer lists, or conversation history.

### 3. Data Isolation and Protection
- Multi-tenant architecture ensures strict tenant data boundaries.
- Cross-tenant data retrieval is prevented at the database and application levels.
- API credentials, Meta secrets, and passwords are encrypted and never exposed in public endpoints or client views.

### 4. Contact & Inquiries
For privacy questions or data requests, contact Neoriz Solutions at privacy@neorizsolutions.com.
"""

    LegalDocument.objects.get_or_create(
        doc_type='TERMS',
        version='1.0',
        defaults={
            'title': 'Neoriz WhatsApp Automation Terms of Service',
            'content': terms_content,
            'effective_date': timezone.now().date(),
            'status': 'DRAFT',
        }
    )

    LegalDocument.objects.get_or_create(
        doc_type='PRIVACY',
        version='1.0',
        defaults={
            'title': 'Neoriz WhatsApp Automation Privacy Policy',
            'content': privacy_content,
            'effective_date': timezone.now().date(),
            'status': 'DRAFT',
        }
    )

    # 3. Associate existing tenants with an active subscription & completed onboarding
    for tenant in Tenant.objects.all():
        # Assign subscription if missing
        if not hasattr(tenant, 'subscription'):
            plan = enterprise_plan if tenant.slug == 'neoriz-solutions' else growth_plan
            TenantSubscription.objects.create(
                tenant=tenant,
                requested_plan=plan,
                effective_plan=plan,
                status='ACTIVE',
                start_date=timezone.now().date(),
                notes='Initial migration active subscription'
            )
        # Mark onboarding completed for existing tenants
        if not hasattr(tenant, 'onboarding_progress'):
            OnboardingProgress.objects.create(
                tenant=tenant,
                current_step='completed',
                completed_steps=['profile', 'plan', 'whatsapp', 'knowledge', 'team', 'workspace', 'test', 'readiness'],
                is_completed=True,
                completed_at=timezone.now()
            )


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0003_plantier_alter_tenantauditlog_action_demorequest_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_plans_legal_and_subscriptions, reverse_seed),
    ]
