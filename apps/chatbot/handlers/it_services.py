"""Grounded IT business and product sales replies using verified PostgreSQL records."""
import re
from apps.services.models import Service, PriceType
from apps.business.models import (
    Product, ProductCapability, ProductIntegration, ProductPricingPlan,
    PricingStatus, FeatureAvailability
)
from ..intent_service import IntentType
from ..language import say


def get_products_summary(tenant=None):
    from apps.tenants.context import get_current_tenant
    if tenant is None:
        tenant = get_current_tenant()
    products = Product.objects.filter(is_active=True)
    if tenant:
        products = products.filter(tenant=tenant)
    if not products.exists():
        return ""
    lines = ["*Verified Products:*"]
    for prod in products:
        tagline = f" — {prod.tagline}" if prod.tagline else ""
        lines.append(f"• *{prod.name}*{tagline}")
        lines.append(f"  {prod.description}")
        lines.append(f"  Pricing: {prod.formatted_pricing}")
    return "\n".join(lines)


def business_reply(intent, entity, catalog, conversation, profile, customer_message=""):
    lang = conversation.customer.preferred_language if conversation else 'en'
    company = profile.shop_name if profile else 'Neoriz Solutions'
    lower_msg = customer_message.lower().strip() if customer_message else ""

    # 1. Identity & Bot Disclosure
    if intent == IntentType.IDENTITY:
        if re.search(r'\b(?:are\s+(?:you|u)\s+(?:a\s+)?(?:bot|human|ai|robot|person)|am\s+i\s+(?:talking|chatting)\s+to\s+(?:a\s+)?(?:human|bot|person))\b', lower_msg):
            return say('bot_identity', lang).format(shop=company)
        return say('identity', lang).format(shop=company)

    # 2. Greeting
    if intent == IntentType.GREETING:
        return f"*{company}*\n{say('greeting', lang)}"

    # 3. Overview of Neoriz Solutions (Agency services + Products)
    if intent == IntentType.SERVICE_LIST or re.search(r'\b(?:what\s+(?:do\s+you|does\s+neoriz)\s+do|about\s+neoriz|tell\s+me\s+about\s+neoriz)\b', lower_msg):
        prod_text = get_products_summary()
        overview = (
            f"*{company}* is a software development and digital technology agency based in Kochi Infopark, Kerala (https://neorizsolutions.com).\n\n"
            f"*1. Digital Agency Services:*\n"
            f"• *Website Development* — Clean, fast-loading business websites optimized for discovery.\n"
            f"• *Mobile App Development* — Intuitive iOS and Android applications.\n"
            f"• *UI/UX Designing* — User-centric interfaces focused on conversion.\n"
            f"• *Software Development* — Custom business software and workflow automation.\n"
            f"• *Ecommerce* — Fast, scalable online store platforms.\n"
            f"• *Website Revamp* — Modernizing existing websites for SEO and performance.\n\n"
        )
        if prod_text:
            overview += f"{prod_text}\n\n"
        overview += (
            "Would you like to explore an agency service, see a product demo, or discuss a project consultation?"
        )
        return overview

    # 4. Product vs Custom Software Comparison
    if intent == IntentType.PRODUCT_VS_SERVICE:
        target_prod = entity if isinstance(entity, Product) else Product.objects.filter(name__iexact='TABLO', is_active=True).first()
        prod_name = target_prod.name if target_prod else "TABLO"
        if prod_name == "TABLO":
            return (
                f"*TABLO vs Custom Software:*\n\n"
                f"• *TABLO* is our ready-to-deploy restaurant ordering product (browser QR self-ordering, digital pickup tokens, and kitchen slips) "
                f"designed to get dining operations running quickly without custom development time or expense.\n\n"
                f"• *Custom Software Development* is best when you need proprietary workflows, custom third-party integrations, "
                f"or unique multi-brand business logic beyond TABLO's standard architecture.\n\n"
                f"Would you like to see a demo of TABLO first, or discuss a custom software scope with our team?"
            )
        else:
            return (
                f"*WhatsApp Automation + CRM vs Custom Software:*\n\n"
                f"• *WhatsApp Automation + CRM* provides ready conversational qualification, official Meta Cloud API integration, "
                f"and staff handover for inbound customer enquiries.\n\n"
                f"• *Custom Software Development* is ideal if you require tailored bespoke integrations with internal legacy databases, "
                f"proprietary ERPs, or specialized data warehouses.\n\n"
                f"Would you like to explore a demo of WhatsApp Automation, or discuss custom development requirements?"
            )

    # 5. Restaurant Operational Problem Probe
    if intent == IntentType.RESTAURANT_PROBLEM:
        return say('restaurant_probe', lang)

    # 6. WhatsApp Lead Management Problem Probe
    if intent == IntentType.WHATSAPP_LEAD_PROBLEM:
        return (
            "Where do customer enquiries slip through most often—during the first response, lead qualification, or team follow-ups?"
        )

    # 7. Existing Customer Support
    if intent == IntentType.CUSTOMER_SUPPORT:
        target_name = entity.name if hasattr(entity, 'name') else "your system"
        sec_note = say('support_security_note', lang)
        return (
            f"I can connect you directly with our support team for *{target_name}*.\n\n"
            f"Please describe the technical issue or error you are experiencing. {sec_note}\n\n"
            f"A member of our technical team will review your message."
        )

    # 8. Product Pricing
    if intent == IntentType.PRODUCT_PRICING:
        if isinstance(entity, (list, tuple)) and len(entity) >= 2:
            p1, p2 = entity[0], entity[1]
            return (
                f"Pricing for *{p1.name}* and *{p2.name}* is tailored to each deployment:\n\n"
                f"• *{p1.name}*: Based on outlet count, counter setup, and order volume.\n"
                f"• *{p2.name}*: Based on monthly customer enquiry volume and team size (Meta conversation charges at actuals).\n\n"
                f"Would you like our team to prepare a combined quote?"
            )
        prod = entity if isinstance(entity, Product) else None
        if not prod:
            prod = Product.objects.filter(is_active=True).first()
        if not prod:
            return "Please contact our sales team to confirm product pricing."

        if prod.pricing_status == PricingStatus.APPROVED_PRICING and prod.pricing_details:
            return f"*{prod.name} Pricing:*\n{prod.pricing_details}\n\nWould you like to request a demo?"
        
        # Quote-based / unconfirmed pricing:
        if prod.name.upper() == 'TABLO':
            return (
                f"For *TABLO*, our team provides a tailored quote based on your number of restaurant outlets, "
                f"counter setups, and operational volume.\n\n"
                f"How many outlets or dining locations are you planning this for?"
            )
        else:
            return (
                f"For *WhatsApp Automation + CRM*, pricing is tailored based on your monthly enquiry volume, "
                f"team size, and integration requirements. Meta conversation charges are billed separately at actuals.\n\n"
                f"Approximately how many customer enquiries does your team handle each month?"
            )

    # 9. Product Capability
    if intent == IntentType.PRODUCT_CAPABILITY:
        if isinstance(entity, tuple) and len(entity) >= 2:
            prod, cap = entity[0], entity[1]
            if cap.status == FeatureAvailability.AVAILABLE:
                return (
                    f"Yes, *{prod.name}* includes *{cap.name}*.\n\n"
                    f"{cap.description}\n\n"
                    f"Would you like to see how this works in a demo?"
                )
            elif cap.status == FeatureAvailability.NOT_SUPPORTED:
                return (
                    f"*{cap.name}* is not currently supported in *{prod.name}*.\n\n"
                    f"{cap.description or 'Our product focuses on verified core workflows.'}\n\n"
                    f"Our IT agency team can also build custom software if this is a mandatory requirement. "
                    f"Would you like to discuss a custom project?"
                )
            else:  # UNCONFIRMED
                return (
                    f"Availability for *{cap.name}* has not been confirmed yet for this setup. "
                    f"Our solutions team can verify this based on your specific requirements.\n\n"
                    f"Would you like me to pass along this requirement or connect you with our team?"
                )

    # 10. Product Integration
    if intent == IntentType.PRODUCT_INTEGRATION:
        if isinstance(entity, tuple) and len(entity) >= 2:
            prod, int_obj = entity[0], entity[1]
            if int_obj.status == FeatureAvailability.AVAILABLE:
                return (
                    f"Yes, *{prod.name}* supports integration with *{int_obj.name}*.\n\n"
                    f"{int_obj.description}\n\n"
                    f"Would you like to schedule a demo to see the setup?"
                )
            else:  # UNCONFIRMED or NOT_SUPPORTED
                return (
                    f"Direct out-of-the-box integration with *{int_obj.name}* is currently unconfirmed and under evaluation for *{prod.name}*.\n\n"
                    f"However, Neoriz Solutions also provides custom software development to connect bespoke systems and third-party APIs. "
                    f"Would you like our engineering team to review this requirement for you?"
                )

    # 11. Product Overview / Enquiry
    if intent in (IntentType.PRODUCT_ENQUIRY, IntentType.PRODUCT_DEMO):
        if isinstance(entity, (list, tuple)) and len(entity) >= 2:
            p1, p2 = entity[0], entity[1]
            return (
                f"Neoriz Solutions offers both *{p1.name}* and *{p2.name}*:\n\n"
                f"1. *{p1.name}* — {p1.tagline or p1.description}\n"
                f"2. *{p2.name}* — {p2.tagline or p2.description}\n\n"
                f"We can tailor a bundled deployment or arrange separate walkthrough demos for each. "
                f"Which area would you like to explore first?"
            )
        prod = entity if isinstance(entity, Product) else None
        if not prod:
            prod = Product.objects.filter(is_active=True).first()
        if prod:
            caps = prod.capabilities.filter(is_active=True, status=FeatureAvailability.AVAILABLE)
            cap_bullets = "\n".join(f"• *{c.name}* — {c.description}" for c in caps[:4])
            reply = (
                f"*{prod.name}*\n"
                f"{prod.tagline or prod.description}\n\n"
                f"*Intended for:* {prod.intended_customers}\n\n"
                f"*Verified Capabilities:*\n{cap_bullets}\n\n"
                f"Pricing: {prod.formatted_pricing}\n\n"
                f"Would you like to schedule a personalized walkthrough demo?"
            )
            return reply

    # 12. Service Pricing (Agency Service)
    if intent == IntentType.SERVICE_PRICE:
        if isinstance(entity, Product):
            return business_reply(IntentType.PRODUCT_PRICING, entity, catalog, conversation, profile, customer_message)
        if isinstance(entity, Service):
            if entity.price_type == PriceType.INSPECTION_REQUIRED:
                reply = say('inspection_price', lang).format(service=entity.name)
            else:
                reply = f"*{entity.name}* — {entity.formatted_price}"
            if entity.description:
                reply += f"\n{entity.description}"
            return reply + "\n\n" + say('request_visit', lang)
        return f"{catalog}\n\n{say('service', lang)}"

    # 13. Service Areas / Location / Hours
    if intent == IntentType.SERVICE_AREAS:
        return profile.service_areas if profile else 'Please contact our team to confirm project arrangements.'
    if intent == IntentType.SHOP_LOCATION:
        if profile:
            return f"*{company}*\n{profile.address}\nContact: {profile.contact_phone}\nEmail: hello@neorizsolutions.com\nWebsite: https://neorizsolutions.com"
        return 'Please contact our team to confirm company contact details.'

    if intent in (IntentType.UNKNOWN, IntentType.AC_PROBLEM):
        return say('identity', lang).format(shop=company) + '\n\n' + say('greeting', lang)

    return None
