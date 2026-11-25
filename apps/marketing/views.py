import logging
from django.shortcuts import render
from apps.tenants.models import PlanTier, LegalDocument, LegalDocumentType
from apps.tenants.modules import MODULE_CATALOG, get_public_modules
from apps.dashboard.views import dashboard_view
from .forms import DemoRequestForm

logger = logging.getLogger(__name__)


def landing_page_view(request):
    """
    Public SaaS marketing landing page for Neoriz WhatsApp Automation.
    If the user is already authenticated and not explicitly viewing the public preview,
    routes directly to their workspace dashboard.
    """
    if request.user.is_authenticated and not request.GET.get('public'):
        return dashboard_view(request)

    plans = list(PlanTier.objects.filter(is_published=True).order_by('ordering'))
    modules = get_public_modules()

    return render(request, 'marketing/index.html', {
        'plans': plans,
        'modules': modules,
        'canonical_url': request.build_absolute_uri('/'),
    })


def features_view(request):
    """
    Comprehensive features & module catalog page.
    Distinguishes available modules from configuration-required and roadmap items.
    """
    modules = list(MODULE_CATALOG.values())
    categories = {}
    for mod in modules:
        cat = mod.get('category', 'Platform')
        categories.setdefault(cat, []).append(mod)

    return render(request, 'marketing/features.html', {
        'categories': categories,
        'modules': modules,
    })


def pricing_view(request):
    """
    Transparent plan comparison page.
    Default display mode is 'Contact Sales' with honest limits and zero-markup Meta explanation.
    """
    plans = list(PlanTier.objects.filter(is_published=True).order_by('ordering'))
    modules = [m for m in MODULE_CATALOG.values() if m['status'] in ('AVAILABLE', 'CONFIG_REQUIRED')]

    return render(request, 'marketing/pricing.html', {
        'plans': plans,
        'modules': modules,
    })


def book_demo_view(request):
    """
    Book a product demonstration or consultation / Request Platform Access.
    Stored in DemoRequest at the platform operator level for Super Admin review.
    Does not route inquiries implicitly into any client tenant CRM.
    """
    if request.method == 'POST':
        form = DemoRequestForm(request.POST)
        if form.is_valid():
            demo_req = form.save(commit=False)
            demo_req.ip_address = request.META.get('REMOTE_ADDR')
            demo_req.routed_to_tenant = None
            demo_req.save()
            return render(request, 'marketing/demo_success.html', {
                'demo_request': demo_req,
            })
    else:
        form = DemoRequestForm()

    return render(request, 'marketing/book_demo.html', {
        'form': form,
    })


def privacy_view(request):
    """Published Privacy Policy page."""
    doc = LegalDocument.get_active_document(LegalDocumentType.PRIVACY)
    return render(request, 'marketing/legal.html', {
        'document': doc,
        'doc_type_title': 'Privacy Policy',
    })


def terms_view(request):
    """Published Terms of Service page."""
    doc = LegalDocument.get_active_document(LegalDocumentType.TERMS)
    return render(request, 'marketing/legal.html', {
        'document': doc,
        'doc_type_title': 'Terms of Service',
    })
