"""
Authoritative Module Catalog for Neoriz WhatsApp Automation.
Defines all functional modules, implementation statuses, configuration requirements,
and associated entitlements for plans and tenant settings.
"""

from typing import Dict, Any, List


class ModuleStatus:
    AVAILABLE = 'AVAILABLE'
    CONFIG_REQUIRED = 'CONFIG_REQUIRED'
    PLANNED = 'PLANNED'


MODULE_CATALOG: Dict[str, Dict[str, Any]] = {
    'marketing': {
        'key':'marketing','name':'WhatsApp Templates and Broadcasts','category':'Sales & Communication',
        'status':ModuleStatus.AVAILABLE,'is_public':True,
        'description':'Consent-aware campaigns using officially approved Meta templates.',
        'required_config':'Verified Meta connection and approved templates','entitlement_key':None,
        'doc_summary':'Manage templates, audiences and campaign delivery.'
    },
    'shared_inbox': {
        'key': 'shared_inbox',
        'name': 'Multi-Agent Shared Inbox',
        'category': 'Sales & Communication',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': 'Centralized multi-agent inbox to manage chats from your verified WhatsApp number with ownership and status tabs (Mine, Team, Unassigned, Waiting, Closed).',
        'required_config': 'Active Meta WhatsApp Cloud API connection',
        'entitlement_key': 'max_staff',
        'doc_summary': 'Allows multiple sales and support reps to view, claim, transfer, and resolve WhatsApp conversations concurrently.'
    },
    'ai_assistant': {
        'key': 'ai_assistant',
        'name': 'AI Assistant and Knowledge',
        'category': 'Automation & AI',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': '24/7 intelligent answering grounded in your business catalog and FAQs. Strictly tenant-isolated with support for English, Malayalam, Manglish, and Hindi.',
        'required_config': 'Business knowledge documents or FAQs indexed; Gemini API Key',
        'entitlement_key': 'ai_assistant_enabled',
        'doc_summary': 'Provides grounded AI replies respecting human takeover and business facts.'
    },
    'contacts_companies': {
        'key': 'contacts_companies',
        'name': 'Contacts and Companies',
        'category': 'Sales & CRM',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': 'Normalized customer phone numbers, company directory, lifecycle statuses, custom tags, and duplicate detection with merge audit trails.',
        'required_config': None,
        'entitlement_key': 'max_contacts',
        'doc_summary': 'Maintains contact details, company affiliations, and chronological interaction timelines.'
    },
    'deals_pipelines': {
        'key': 'deals_pipelines',
        'name': 'Deals and Pipelines',
        'category': 'Sales & CRM',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': 'Interactive visual Kanban board and list views across custom stages, probability weighting, and won/lost reason tracking in INR.',
        'required_config': None,
        'entitlement_key': 'crm_enabled',
        'doc_summary': 'Enables sales representatives to advance deals across qualified, proposal, and won/lost stages.'
    },
    'tasks_followups': {
        'key': 'tasks_followups',
        'name': 'Tasks and Follow-ups',
        'category': 'Sales & CRM',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': 'Actionable tasks and follow-up activities tied to contacts and deals with filterable views (Mine, Today, Upcoming, Overdue, Completed).',
        'required_config': None,
        'entitlement_key': 'crm_enabled',
        'doc_summary': 'Tracks overdue tasks, priority flags, and completion states directly inside customer timelines.'
    },
    'assignment_collaboration': {
        'key': 'assignment_collaboration',
        'name': 'Assignment and Team Collaboration',
        'category': 'Sales & CRM',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': 'Manual and automated round-robin/least-workload assignment, internal staff notes separate from customer chats, and work reassignment before member removal.',
        'required_config': None,
        'entitlement_key': 'max_staff',
        'doc_summary': 'Enforces seat allocations where Owner and Administrators count toward seats.'
    },
    'qualification_scoring': {
        'key': 'qualification_scoring',
        'name': 'Qualification and Scoring',
        'category': 'Sales & CRM',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': 'Tenant-configurable qualification questions by product/service and explainable rule-based lead priority scoring with visible contributions.',
        'required_config': None,
        'entitlement_key': 'crm_enabled',
        'doc_summary': 'Captures progressive prospect details and computes explainable priority scores.'
    },
    'scheduling_quotations': {
        'key': 'scheduling_quotations',
        'name': 'Scheduling and Quotations',
        'category': 'Sales & CRM',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': 'Application-managed consultation availability with conflict prevention, plus deal-linked versioned quotations with line items and PDF downloads.',
        'required_config': None,
        'entitlement_key': 'crm_enabled',
        'doc_summary': 'Generates versioned quotes and coordinates consultation bookings.'
    },
    'automation': {
        'key': 'automation',
        'name': 'Automation',
        'category': 'Automation & AI',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': 'Bounded tenant-scoped workflow automation engine with event triggers (new enquiry, stage changed, deal won), configurable actions, dry-run preview, and execution history.',
        'required_config': None,
        'entitlement_key': 'crm_enabled',
        'doc_summary': 'Executes safe automated actions with loop prevention and audit logging.'
    },
    'support': {
        'key': 'support',
        'name': 'Support',
        'category': 'Customer Support',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': 'Customer support tickets linked to contacts and conversations with priority, status, internal notes, response targets, and post-sale onboarding checklists.',
        'required_config': None,
        'entitlement_key': 'crm_enabled',
        'doc_summary': 'Manages post-sale onboarding and customer support workflows.'
    },
    'reporting': {
        'key': 'reporting',
        'name': 'Reporting',
        'category': 'Workspace',
        'status': ModuleStatus.AVAILABLE,
        'is_public': True,
        'description': 'Workspace operational summary metrics for conversations, open deals, stage volumes, response times, and monthly quota usage.',
        'required_config': None,
        'entitlement_key': None,
        'doc_summary': 'Provides visibility into team workload, deal conversions, and messaging quota.'
    },
    'integrations': {
        'key': 'integrations',
        'name': 'Integrations',
        'category': 'Platform & Tools',
        'status': ModuleStatus.CONFIG_REQUIRED,
        'is_public': True,
        'description': 'Integration foundation with HMAC-signed outbound webhooks, delivery attempt logs with bounded retries, and connector interfaces for external CRMs and calendars.',
        'required_config': 'External endpoint URL and signing secret configured',
        'entitlement_key': None,
        'doc_summary': 'Streams platform events to external systems securely with SSRF protection.'
    },
    'team_management': {
        'key': 'team_management',
        'name': 'Team Management',
        'category': 'Sales & CRM',
        'status': ModuleStatus.AVAILABLE,
        'is_public': False,
        'description': 'Staff seating and team access controls.',
        'required_config': None,
        'entitlement_key': 'max_staff',
        'doc_summary': 'Staff access management.'
    },
    'demo_scheduling': {
        'key': 'demo_scheduling',
        'name': 'Consultation & Demo Scheduling',
        'category': 'Sales & CRM',
        'status': ModuleStatus.AVAILABLE,
        'is_public': False,
        'description': 'Booking requests and consultation scheduling.',
        'required_config': None,
        'entitlement_key': 'crm_enabled',
        'doc_summary': 'Demo scheduling.'
    },
    'reports': {
        'key': 'reports',
        'name': 'Analytics & Reports',
        'category': 'Platform & Tools',
        'status': ModuleStatus.AVAILABLE,
        'is_public': False,
        'description': 'Workspace operational analytics.',
        'required_config': None,
        'entitlement_key': None,
        'doc_summary': 'Reports.'
    },
}


def get_available_modules() -> List[Dict[str, Any]]:
    return [m for m in MODULE_CATALOG.values() if m['status'] == ModuleStatus.AVAILABLE]


def get_public_modules() -> List[Dict[str, Any]]:
    return [m for m in MODULE_CATALOG.values() if m['is_public']]


def get_module_by_key(key: str) -> Dict[str, Any]:
    return MODULE_CATALOG.get(key)
