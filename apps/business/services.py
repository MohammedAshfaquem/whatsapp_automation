from .models import BusinessProfile

def get_business_summary() -> str:
    """Return formatted business summary text for AI context and prompts."""
    profile = BusinessProfile.get_active()
    if not profile:
        return "AC repair and servicing shop."

    return (
        f"Shop Name: {profile.shop_name}\n"
        f"Phone: {profile.contact_phone}\n"
        f"Address: {profile.address}\n"
        f"Working Hours: {profile.working_hours}\n"
        f"Holidays: {profile.holiday_information}\n"
        f"Service Areas: {profile.service_areas}\n"
        f"Supported AC Types: {profile.supported_ac_types}\n"
        f"Supported Brands: {profile.supported_ac_brands}\n"
        f"Warranty Policy: {profile.warranty_policies}\n"
        f"Accepted Payment Methods: {profile.accepted_payment_methods}\n"
        f"Service Policies: {profile.general_service_policies}"
    )
