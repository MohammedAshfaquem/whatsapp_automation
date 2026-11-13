from django.core.management.base import BaseCommand
from django.utils.text import slugify
from apps.services.models import Service, PriceType
from apps.business.models import BusinessProfile
from apps.knowledge_base.models import FAQ, KnowledgeDocument, DocumentCategory

class Command(BaseCommand):
    help = "Seed database with initial AC services, business profile, and FAQs."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding Business Profile..."))
        profile, created = BusinessProfile.objects.get_or_create(
            shop_name="CoolAir AC Services & Mechanicals",
            defaults={
                "contact_phone": "+91 98765 43210",
                "address": "123 Industrial Area, Main Road, New Delhi, India",
                "google_maps_url": "https://maps.google.com/?q=CoolAir+AC+Services",
                "working_hours": "Monday to Saturday: 9:00 AM - 8:00 PM\nSunday: 10:00 AM - 4:00 PM",
                "holiday_information": "Closed on National Holidays and Diwali",
                "service_areas": "South Delhi, Central Delhi, Noida Sector 1-62, Indirapuram, Gurgaon DLF Phase 1-5",
                "supported_ac_types": "Split AC, Window AC, Inverter AC, Cassette AC, Tower AC",
                "supported_ac_brands": "Daikin, Voltas, LG, Samsung, Blue Star, Carrier, Hitachi, Lloyd, Panasonic, Godrej",
                "warranty_policies": "30-day warranty on service and repair workmanship. 90-day warranty on genuine spare parts replaced by our team.",
                "accepted_payment_methods": "Cash, UPI (Google Pay, PhonePe, Paytm), Credit & Debit Cards, Net Banking",
                "general_service_policies": "Visiting/inspection charge of ₹200 applies if service is declined after doorstep inspection.",
                "is_active": True,
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS("[OK] Created active BusinessProfile"))
        else:
            self.stdout.write("  BusinessProfile already exists.")

        self.stdout.write(self.style.NOTICE("\nSeeding AC Services..."))
        sample_services = [
            {
                "name": "AC general servicing",
                "category": "Maintenance",
                "price_type": PriceType.STARTING_FROM,
                "price_amount": 500.00,
                "max_price": None,
                "estimated_duration": "45-60 mins",
                "description": "Comprehensive filter cleaning, indoor cooling coil jet wash, outdoor condenser coil cleaning, and drain tray flush."
            },
            {
                "name": "AC gas filling",
                "category": "Refill & Maintenance",
                "price_type": PriceType.STARTING_FROM,
                "price_amount": 1500.00,
                "max_price": None,
                "estimated_duration": "1-2 hours",
                "description": "Complete nitrogen leak test, vacuuming, and pure refrigerant gas top-up/refill (R32, R410A, R22)."
            },
            {
                "name": "AC installation",
                "category": "Installation",
                "price_type": PriceType.STARTING_FROM,
                "price_amount": 1000.00,
                "max_price": None,
                "estimated_duration": "2-3 hours",
                "description": "Professional indoor and outdoor unit wall mounting, copper piping connection, electrical wiring, and performance testing."
            },
            {
                "name": "AC repair",
                "category": "Repair",
                "price_type": PriceType.INSPECTION_REQUIRED,
                "price_amount": None,
                "max_price": None,
                "estimated_duration": "1-3 hours",
                "description": "Diagnostics for not cooling, water leakage, strange noise, PCB breakdown, compressor issues. Exact quote provided upon physical inspection."
            },
            {
                "name": "AC uninstallation",
                "category": "Installation",
                "price_type": PriceType.STARTING_FROM,
                "price_amount": 800.00,
                "max_price": None,
                "estimated_duration": "1 hour",
                "description": "Safe refrigerant pump-down, safe disconnection of indoor and outdoor units and brackets."
            },
        ]

        for s_data in sample_services:
            slug = slugify(s_data['name'])
            service, s_created = Service.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": s_data["name"],
                    "category": s_data["category"],
                    "price_type": s_data["price_type"],
                    "price_amount": s_data["price_amount"],
                    "max_price": s_data["max_price"],
                    "estimated_duration": s_data["estimated_duration"],
                    "description": s_data["description"],
                    "is_active": True,
                }
            )
            action = "Created" if s_created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"[OK] {action} service: {service.name} — {service.formatted_price}"))

        self.stdout.write(self.style.NOTICE("\nSeeding FAQs..."))
        sample_faqs = [
            ("Do you provide split AC repair?", "Yes, we provide complete repair, servicing, and part replacement for split ACs of all major brands.", "Services"),
            ("Do you provide window AC servicing?", "Yes, we service and repair window ACs at your doorstep or workshop.", "Services"),
            ("What are your working hours?", "We are open Monday to Saturday from 9:00 AM to 8:00 PM, and Sunday from 10:00 AM to 4:00 PM.", "Timings"),
            ("Which areas do you serve?", "We serve South Delhi, Central Delhi, Noida Sector 1-62, Indirapuram, and Gurgaon DLF Phase 1-5.", "Coverage"),
            ("Do you provide home visits?", "Yes, our certified technicians provide doorstep home visits for inspection, repair, and servicing.", "Services"),
            ("How can I book a service?", "You can easily book directly through this WhatsApp chat! Just tell us your AC type, problem, and preferred time.", "Booking"),
        ]

        for q, a, cat in sample_faqs:
            faq, f_created = FAQ.objects.update_or_create(
                question=q,
                defaults={
                    "answer": a,
                    "category": cat,
                    "is_active": True
                }
            )
            action = "Created" if f_created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"[OK] {action} FAQ: {q}"))

        self.stdout.write(self.style.NOTICE("\nSeeding Knowledge Documents..."))
        docs = [
            (
                "Standard Warranty Policy",
                "warranty-policy",
                DocumentCategory.WARRANTY,
                "We provide a 30-day warranty on all service and workmanship. Replaced spare parts carry a 90-day manufacturer warranty. Warranty covers defects in parts or repair work done by CoolAir technicians."
            ),
            (
                "Inspection and Visiting Policy",
                "visiting-policy",
                DocumentCategory.POLICY,
                "Our technician will visit your location to inspect the AC. If service or repair is approved, visiting charges are waived. If the customer declines the service quote after inspection, a standard nominal visiting fee of ₹200 applies."
            )
        ]

        for title, slug, cat, content in docs:
            doc, d_created = KnowledgeDocument.objects.update_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "category": cat,
                    "content": content,
                    "is_active": True
                }
            )
            action = "Created" if d_created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"[OK] {action} Knowledge Doc: {title}"))

        self.stdout.write(self.style.SUCCESS("\nAll seed data successfully populated!"))
