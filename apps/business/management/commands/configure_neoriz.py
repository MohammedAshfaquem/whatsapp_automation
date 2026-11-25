"""Install the public Neoriz Solutions catalog while retaining historical records."""
from datetime import date
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.business.domain import is_it_business
from apps.business.models import (
    BusinessProfile, Product, ProductCapability, ProductIntegration, ProductPricingPlan,
    PricingStatus, FeatureAvailability
)
from apps.knowledge_base.models import FAQ, KnowledgeDocument
from apps.services.models import PriceType, Service


CATALOG = {
    'Website Development': 'Business websites built with clean code, fast loading and content organized for customers and search discovery.',
    'Mobile App Development': 'Fast, intuitive mobile applications for iOS and Android.',
    'UI/UX Designing': 'Clear, conversion-focused interfaces aligned with how customers think and act.',
    'Software Development': 'Custom software to automate workflows, connect teams and support business growth.',
    'Ecommerce': 'Ecommerce experiences designed for fast loading, product discovery and conversion.',
    'Website Revamp': 'Modernize existing websites with updated design, SEO, performance and clearer conversion paths.',
}


class Command(BaseCommand):
    help = 'Configure Neoriz Solutions using the services and products published at https://neorizsolutions.com. No prices are invented.'

    @transaction.atomic
    def handle(self, *args, **options):
        if not is_it_business():
            raise CommandError('Set BUSINESS_INDUSTRY=it before configuring Neoriz Solutions.')
        BusinessProfile.objects.exclude(shop_name='Neoriz Solutions').update(is_active=False)
        profile = BusinessProfile.objects.filter(shop_name='Neoriz Solutions').first()
        if not profile:
            BusinessProfile.objects.create(
                shop_name='Neoriz Solutions',
                contact_phone='+917736361739',
                address='Kochi / Infopark, Kerala, India',
                working_hours='Please contact our team to confirm consultation availability.',
                holiday_information='',
                service_areas='Contact our team to confirm delivery arrangements for your project.',
                supported_ac_types='',
                supported_ac_brands='',
                warranty_policies='Support and maintenance terms are agreed for each project.',
                accepted_payment_methods='Our team will confirm payment methods and terms with your proposal.',
                general_service_policies=(
                    'Website: https://neorizsolutions.com. Email: hello@neorizsolutions.com. '
                    'Pricing and delivery timelines require review of the project scope. '
                    'Consultation requests are pending until confirmed by our team.'
                ),
                is_active=True,
            )
        else:
            profile.is_active = True
            profile.save(update_fields=['is_active'])

        Service.objects.exclude(name__in=CATALOG).update(is_active=False)
        for name, description in CATALOG.items():
            # Retain explicitly configured IT prices when rerunning the command.
            Service.objects.get_or_create(name=name, defaults={
                'description': description, 'category': 'IT & Digital Services',
                'price_type': PriceType.INSPECTION_REQUIRED, 'price_amount': None,
                'max_price': None, 'contact_number': '+917736361739', 'estimated_duration': '',
            })
            Service.objects.filter(name=name).update(is_active=True)

        # -------------------------------------------------------------------------
        # Products configuration: TABLO and WhatsApp Automation + CRM
        # Retain explicitly configured product details/pricing when rerunning.
        # -------------------------------------------------------------------------
        today = date.today()

        # 1. TABLO Restaurant Software
        tablo, tablo_created = Product.objects.get_or_create(
            name='TABLO',
            defaults={
                'slug': 'tablo',
                'tagline': 'Self-Ordering & Counter-Collection Software for Restaurants & Cafés',
                'description': (
                    'Digital self-ordering and counter-collection software designed for quick-service restaurants, '
                    'express cafés, food courts, and modern dining operations to streamline ordering and reduce checkout queues.'
                ),
                'intended_customers': (
                    'Quick-service restaurants (QSRs), express cafés, food courts, kiosks, and counter-service dining venues.'
                ),
                'limitations': (
                    'Focuses on browser-based QR ordering, digital pickup tokens, and kitchen communication. '
                    'Full ERP inventory, dedicated KDS hardware, and legacy POS sync require individual verification.'
                ),
                'deployment_onboarding': (
                    'Cloud-hosted web application. Setup includes custom digital menu QR codes and pickup counter scanner setup. '
                    'Onboarding arranged with the Neoriz Solutions solutions team.'
                ),
                'support_info': (
                    'Technical support and onboarding guidance provided by Neoriz Solutions team for restaurant partners.'
                ),
                'demo_process': (
                    'Interactive walkthrough demonstrating customer QR ordering, payment checkout, token issuance, and counter redemption.'
                ),
                'pricing_status': PricingStatus.QUOTE_REQUIRED,
                'pricing_details': (
                    'Pricing is tailored based on number of restaurant outlets, counter terminals, and operational requirements. '
                    'Our sales team confirms the quote after understanding your setup.'
                ),
                'source_references': 'https://neorizsolutions.com, verified product documentation',
                'last_verified_at': today,
                'aliases': 'tablo, restaurant software, restaurant app, qr ordering, food court ordering, self ordering',
                'is_active': True,
            }
        )
        if not tablo_created and not tablo.is_active:
            tablo.is_active = True
            tablo.save(update_fields=['is_active'])

        tablo_caps = [
            ('QR-Based Self-Ordering', 'Ordering', FeatureAvailability.AVAILABLE,
             'Customers scan a Menu QR code using their smartphone to browse, customize items, and pay online in mobile browser without downloading an app.'),
            ('Digital Order Tokens', 'Ordering', FeatureAvailability.AVAILABLE,
             'Unique digital Order QR tokens issued after payment confirmation, scanned at pickup counter to validate order and prevent duplicate collections.'),
            ('Counter Pickup Validation & Kitchen Slips', 'Operations', FeatureAvailability.AVAILABLE,
             'Counter pickup scanning automatically validates orders and triggers itemized receipts and kitchen slips.'),
            ('Flexible Modes', 'Ordering', FeatureAvailability.AVAILABLE,
             'Supports both counter-pickup self-service workflows and table-aware autonomous ordering.'),
            ('Checkout Inventory Holds', 'Operations', FeatureAvailability.AVAILABLE,
             'Temporary inventory holds during checkout to prevent overselling of high-demand items.'),
            ('Queue Reduction', 'Operations', FeatureAvailability.AVAILABLE,
             'Eliminates cashier bottlenecks and reduces manual order re-keying or handwritten ticket errors.'),
            ('POS & Legacy Billing Integration', 'Integrations', FeatureAvailability.UNCONFIRMED,
             'Direct sync with existing POS systems (e.g. Petpooja, Posist) is unconfirmed and evaluated on request by our engineering team.'),
            ('Dedicated Hardware Kitchen Display (KDS)', 'Kitchen', FeatureAvailability.UNCONFIRMED,
             'Dedicated touchscreen hardware KDS stations require confirmation; standard setup triggers kitchen slips automatically.'),
            ('Comprehensive Multi-Warehouse Inventory', 'Inventory', FeatureAvailability.UNCONFIRMED,
             'Deep ingredient-level recipe tracking and multi-warehouse inventory beyond checkout holds requires confirmation.'),
            ('Custom Restaurant Reporting & Analytics', 'Analytics', FeatureAvailability.UNCONFIRMED,
             'Custom accounting exports and advanced restaurant analytics dashboards require team confirmation.'),
        ]
        for c_name, c_cat, c_status, c_desc in tablo_caps:
            ProductCapability.objects.get_or_create(
                product=tablo, name=c_name,
                defaults={'category': c_cat, 'status': c_status, 'description': c_desc, 'is_active': True}
            )

        tablo_ints = [
            ('Online Payment Gateways', FeatureAvailability.AVAILABLE, 'Mobile browser payment processing supporting UPI, cards, and net banking.'),
            ('Legacy POS Systems', FeatureAvailability.UNCONFIRMED, 'Custom integration available as an IT agency service; out-of-the-box sync unconfirmed.'),
            ('Food Aggregators (Swiggy / Zomato)', FeatureAvailability.UNCONFIRMED, 'Direct aggregator menu and order sync is unconfirmed and under evaluation.'),
        ]
        for i_name, i_status, i_desc in tablo_ints:
            ProductIntegration.objects.get_or_create(
                product=tablo, name=i_name,
                defaults={'status': i_status, 'description': i_desc, 'is_active': True}
            )

        ProductPricingPlan.objects.get_or_create(
            product=tablo, name='Restaurant Solution Quote',
            defaults={
                'billing_frequency': 'Custom',
                'is_quote_based': True,
                'description': 'Tailored quotation based on number of outlets, operational complexity, and counter setups.',
                'is_active': True,
            }
        )

        # 2. WhatsApp Automation + CRM
        crm, crm_created = Product.objects.get_or_create(
            name='WhatsApp Automation + CRM',
            defaults={
                'slug': 'whatsapp-automation-crm',
                'tagline': 'Automated WhatsApp Lead Management & Customer Engagement',
                'description': (
                    'Automated WhatsApp communication and CRM solution to capture inbound customer enquiries, '
                    'qualify business leads, and connect conversations to operational workflows.'
                ),
                'intended_customers': (
                    'Businesses, service providers, IT agencies, and sales teams managing high volumes of customer enquiries on WhatsApp.'
                ),
                'limitations': (
                    'Subject to Meta WhatsApp Business Platform policies and messaging tier limits. '
                    'Does not support unmetered spam broadcasting; template pre-approvals apply.'
                ),
                'deployment_onboarding': (
                    'Meta Business Manager setup, official WhatsApp Cloud API onboarding, phone number verification, '
                    'and custom automation flows configured by Neoriz Solutions.'
                ),
                'support_info': (
                    'Technical implementation, webhook monitoring, and ongoing support provided by Neoriz Solutions engineers.'
                ),
                'demo_process': (
                    'Live demonstration of customer message handling, automated qualification, appointment scheduling, and staff handover.'
                ),
                'pricing_status': PricingStatus.QUOTE_REQUIRED,
                'pricing_details': (
                    'Pricing depends on enquiry volume, team size, and integration requirements. '
                    'Meta conversation fees are billed at actuals. The team confirms the proposal after requirements review.'
                ),
                'source_references': 'https://neorizsolutions.com, verified platform implementations',
                'last_verified_at': today,
                'aliases': 'whatsapp automation, whatsapp crm, whatsapp bot, crm, lead automation, whatsapp follow up',
                'is_active': True,
            }
        )
        if not crm_created and not crm.is_active:
            crm.is_active = True
            crm.save(update_fields=['is_active'])

        crm_caps = [
            ('Official WhatsApp Business Cloud API Integration', 'Messaging', FeatureAvailability.AVAILABLE,
             'Direct integration with Meta official WhatsApp Business Cloud API with webhook verification and durable delivery.'),
            ('Website & App Enquiry Capture', 'Lead Capture', FeatureAvailability.AVAILABLE,
             'Direct capture and handoff of enquiries from web applications, mobile apps, and digital channels to WhatsApp.'),
            ('Conversational Lead Qualification', 'CRM', FeatureAvailability.AVAILABLE,
             'Context-aware progressive qualification collecting customer goals, requirements, and contact details.'),
            ('Human Staff Handover', 'Operations', FeatureAvailability.AVAILABLE,
             'Automatic reply pause and concise contextual handoff summaries for human staff when requested or needed.'),
            ('Automated Follow-ups & Reminders', 'Automation', FeatureAvailability.UNCONFIRMED,
             'Automated multi-day drip campaigns and proactive reminders require use case review and Meta template approval.'),
            ('Shared Multi-Agent Team Inbox', 'CRM', FeatureAvailability.UNCONFIRMED,
             'Collaborative multi-agent inbox with concurrent ticket assignments requires confirmation based on team tier.'),
            ('Automated Lead Pipeline & Stages', 'CRM', FeatureAvailability.UNCONFIRMED,
             'Visual kanban lead pipeline stages require confirmation of preferred CRM backend or custom software build.'),
            ('Broadcast Marketing Campaigns', 'Messaging', FeatureAvailability.UNCONFIRMED,
             'Bulk outbound broadcasts are subject to Meta template compliance and require confirmation by sales team.'),
        ]
        for c_name, c_cat, c_status, c_desc in crm_caps:
            ProductCapability.objects.get_or_create(
                product=crm, name=c_name,
                defaults={'category': c_cat, 'status': c_status, 'description': c_desc, 'is_active': True}
            )

        crm_ints = [
            ('Meta WhatsApp Business Cloud API', FeatureAvailability.AVAILABLE, 'Official Cloud API connection with webhook support.'),
            ('Third-Party CRM Systems (HubSpot, Zoho, Salesforce)', FeatureAvailability.UNCONFIRMED,
             'Available as custom integration via Neoriz Solutions Software Development service; native out-of-the-box connector is unconfirmed.'),
        ]
        for i_name, i_status, i_desc in crm_ints:
            ProductIntegration.objects.get_or_create(
                product=crm, name=i_name,
                defaults={'status': i_status, 'description': i_desc, 'is_active': True}
            )

        ProductPricingPlan.objects.get_or_create(
            product=crm, name='CRM Solution Quote',
            defaults={
                'billing_frequency': 'Custom',
                'is_quote_based': True,
                'description': 'Custom quotation based on enquiry volume, team seats, and desired automation workflows. Meta fees at actuals.',
                'is_active': True,
            }
        )

        old_domain = re.compile(r'\bAC\b|air condition|refrigerant|freon|gas filling', re.I)
        for item in FAQ.objects.filter(is_active=True):
            if old_domain.search(item.question + ' ' + item.answer):
                item.is_active = False
                item.save(update_fields=['is_active'])
        for item in KnowledgeDocument.objects.filter(is_active=True):
            if old_domain.search(item.title + ' ' + item.content):
                item.is_active = False
                item.save(update_fields=['is_active'])
        self.stdout.write('Neoriz Solutions profile, 6 IT agency services, and 2 verified products configured.')

