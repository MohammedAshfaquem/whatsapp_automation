from .models import Service

def get_active_services():
    """Retrieve active services directly from PostgreSQL."""
    return Service.objects.filter(is_active=True).order_by('id')

def get_services_formatted_text() -> str:
    """
    Format active services into a numbered, readable list for customer replies.
    Direct PostgreSQL lookup ensures real-time pricing accuracy.
    """
    services = get_active_services()
    if not services.exists():
        return "No services are currently listed. Please contact the shop directly."

    lines = []
    for idx, service in enumerate(services, start=1):
        lines.append(f"{idx}. {service.name} — {service.formatted_price}")
    
    return "\n".join(lines)
