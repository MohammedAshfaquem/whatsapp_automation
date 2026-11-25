from .models import Service
from apps.tenants.context import get_current_tenant

def get_active_services(tenant=None):
    """Retrieve active services directly from PostgreSQL scoped to tenant."""
    if tenant is None:
        tenant = get_current_tenant()
    qs = Service.objects.filter(is_active=True)
    if tenant:
        qs = qs.filter(tenant=tenant)
    return qs.order_by('id')

def get_services_formatted_text(tenant=None) -> str:
    """
    Format active services into a numbered, readable list for customer replies.
    Direct PostgreSQL lookup ensures real-time pricing accuracy.
    """
    services = get_active_services(tenant=tenant)
    if not services.exists():
        return "No services are currently listed. Please contact the team directly."

    lines = []
    for idx, service in enumerate(services, start=1):
        lines.append(f"{idx}. {service.name} — {service.formatted_price}")
    
    return "\n".join(lines)
