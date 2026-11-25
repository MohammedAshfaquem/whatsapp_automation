from .models import BusinessProfile
from .domain import is_it_business
from apps.tenants.context import get_current_tenant

def get_business_summary(tenant=None) -> str:
    """Return formatted business summary text for AI context and prompts scoped to tenant."""
    if tenant is None:
        tenant = get_current_tenant()
    profile = BusinessProfile.get_active(tenant=tenant)
    if not profile:
        company = tenant.name if tenant else "Neoriz Solutions"
        return f"{company} services. Our service team will confirm business details."

    return '\n'.join([
        f'Company: {profile.shop_name}', f'Contact: {profile.contact_phone}',
        f'Location: {profile.address}', f'Working hours: {profile.working_hours}',
        f'Availability: {profile.holiday_information}', f'Service coverage: {profile.service_areas}',
        f'Support terms: {profile.warranty_policies}',
        f'Payment methods: {profile.accepted_payment_methods}',
        f'Project policies: {profile.general_service_policies}',
    ])
