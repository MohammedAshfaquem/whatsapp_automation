import re
from difflib import get_close_matches
from enum import Enum
from typing import Optional, Tuple
from apps.services.models import Service
from apps.knowledge_base.models import FAQ

class IntentType(str, Enum):
    GREETING = "GREETING"
    SERVICE_LIST = "SERVICE_LIST"
    SERVICE_SELECT = "SERVICE_SELECT"
    SERVICE_PRICE = "SERVICE_PRICE"
    DISCOUNT_ENQUIRY = "DISCOUNT_ENQUIRY"
    WORKING_HOURS = "WORKING_HOURS"
    SERVICE_AREAS = "SERVICE_AREAS"
    SHOP_LOCATION = "SHOP_LOCATION"
    PAYMENT_METHODS = "PAYMENT_METHODS"
    WARRANTY_POLICY = "WARRANTY_POLICY"
    FAQ_MATCH = "FAQ_MATCH"
    BOOKING_START = "BOOKING_START"
    BOOKING_STATUS = "BOOKING_STATUS"
    AC_PROBLEM = "AC_PROBLEM"
    IDENTITY = "IDENTITY"
    HANDOVER = "HANDOVER"
    UNKNOWN = "UNKNOWN"
    # IT Agency & Product Intents
    PRODUCT_ENQUIRY = "PRODUCT_ENQUIRY"
    PRODUCT_CAPABILITY = "PRODUCT_CAPABILITY"
    PRODUCT_PRICING = "PRODUCT_PRICING"
    PRODUCT_DEMO = "PRODUCT_DEMO"
    PRODUCT_INTEGRATION = "PRODUCT_INTEGRATION"
    CUSTOMER_SUPPORT = "CUSTOMER_SUPPORT"
    PRODUCT_VS_SERVICE = "PRODUCT_VS_SERVICE"
    RESTAURANT_PROBLEM = "RESTAURANT_PROBLEM"
    WHATSAPP_LEAD_PROBLEM = "WHATSAPP_LEAD_PROBLEM"


class IntentService:
    """
    Deterministic intent recognition and keyword matching service for customer queries.
    Provides fast, grounded, and accurate response classification before LLM fallback.
    """

    @staticmethod
    def is_clarification(message):
        """Obvious conversational questions stay out of fallback booking fields."""
        return bool(re.search(
            r"^\s*(?:what|why|who|where|how)\b|^\s*(?:can|could|would|will)\s+(?:you|u)\s+"
            r"(?:explain|clarify|tell|help|repeat)\b|\b(?:dont|don't|do not)\s+understand\b|"
            r"\bnot understanding\b|\bi(?:\s+am|'m)\s+confused\b", message, re.I))

    @staticmethod
    def is_simple_greeting(message):
        text = re.sub(r'[^\w\s]', '', message.lower()).strip()
        return bool(re.fullmatch(
            r'(hi+|hello+|hey+|hai|helo|namaste|namaskaram|നമസ്കാരം|ഹലോ|नमस्ते|good\s*(morning|afternoon|evening))'
            r'(?:\s+(?:there|bro|brother|buddy|mate|friend|sir))?', text))

    HANDOVER_PATTERNS = [
        r'\b(talk\s*to\s*(?:an?\s*)?(?:human|agent|person|owner|support|team)|human\s*support|connect\s*(?:me\s*)?to\s*(?:an?\s*)?(?:human|person|agent|team|staff|executive|owner)|speak\s*with\s*(?:an?\s*)?(?:agent|human|owner|team))\b'
    ]

    GREETING_PATTERNS = [
        r'\b(hi|hello|hey|namaste|good\s*(morning|afternoon|evening)|hola|i\s*am|i\'m|my\s*name\s*is|myself)\b'
    ]

    BOOKING_STATUS_PATTERNS = [
        r'\b(booking\s*status|appointment\s*status|check\s*(my\s*)?(booking|appointment)|when\s*is\s*(the\s*)?technician\s*(coming|arriving|visit)|status\s*of\s*(my\s*)?(booking|service|appointment)|is\s*(my\s*)?(booking|appointment)\s*confirmed)\b'
    ]

    @classmethod
    def is_booking_list_enquiry(cls, message):
        normalized = ' '.join(re.findall(r'\w+', message.lower()))
        if re.fullmatch(r'booking_history_\d{1,6}', message.lower().strip()):
            return True
        words = set(normalized.split())
        if not words.intersection({'booking', 'bookings', 'appointment', 'appointments'}):
            return False
        if words.intersection({'cancel', 'reschedule', 'change', 'edit'}):
            return False
        if re.search(r'\b(?:book|create|make|start|arrange|schedule)\b', normalized):
            return False
        return (bool(words.intersection({'list', 'history', 'all', 'show', 'view', 'see'}))
                or normalized in ('my bookings', 'my appointments'))

    @classmethod
    def is_booking_status_enquiry(cls, message):
        """Recognize a status request without depending on one exact word order."""
        normalized = ' '.join(re.findall(r'\w+', message.lower()))
        if cls.is_booking_list_enquiry(message):
            return True
        if any(re.search(pattern, normalized) for pattern in cls.BOOKING_STATUS_PATTERNS):
            return True
        if normalized == 'check status':
            return True
        words = set(normalized.split())
        if not words.intersection({'status', 'update', 'updates', 'progress', 'confirmed', 'confirmation'}):
            return False
        if words.intersection({'cancel', 'reschedule', 'change', 'edit'}):
            return False
        if 'update' in words and words.intersection({'address', 'date', 'time'}):
            return False
        if re.search(
                r'\b(?:book|create|make|start|arrange|schedule)\s+'
                r'(?:(?:a|an|the|my|new|another)\s+){0,3}(?:booking|appointment|visit)\b', normalized):
            return False
        if words.intersection({'booking', 'bookings', 'appointment', 'appointments'}):
            return True
        # Correct a close booking-word typo only in a personal status question.
        # The prefix guard prevents unrelated words such as "cooking" matching.
        return 'my' in words and any(
            word.startswith(('bo', 'app')) and get_close_matches(
                word, ('booking', 'bookings', 'appointment', 'appointments'), n=1, cutoff=0.84)
            for word in words)

    BOOKING_PATTERNS = [
        r'\b(book|booking|appointment|schedule|arrange|need\s+a\s+technician|want\s+to\s+book)\b'
    ]

    HOURS_PATTERNS = [
        r'\b(timing|timings|working\s*hours|open\s*today|closing\s*time|when\s*are\s*you\s*open|sunday)\b'
    ]

    AREAS_PATTERNS = [
        r'\b(area|areas|service\s*(?:areas?|locations?)|coverage|do\s*you\s*come\s*to|serve\s*in|doorstep)\b',
        r'\b(?:do|can)\s+you\s+(?:serve|service|cover|visit)\s+(?:my|our|this|that)\s+location\b',
        r'\blocations?\s+(?:do\s+you\s+)?(?:cover|serve|service)\b',
    ]

    LOCATION_PATTERNS = [
        r'\bwhere\s+(?:is|are)\s+(?:your\s+)?(?:shop|store|office|location)\b',
        r'\bwhere\s+are\s+you\s*(?:located|based)?\b',
        r'\b(?:your|shop|store|office)\s+(?:location|address)\b',
        r'\b(?:send|share)\s+(?:me\s+)?(?:your\s+)?(?:location|address|pin)\b',
        r'\b(?:maps|directions?)\b',
        r'^\s*(?:location|address)(?:\s+please)?\s*[?!.]*$',
    ]

    PAYMENT_PATTERNS = [
        r'\b(payment|pay|upi|cash|card|credit|gpay|phonepe|net\s*banking)\b'
    ]

    WARRANTY_PATTERNS = [
        r'\b(warranty|guarantee|policy|inspection\s*charge|visiting\s*charge)\b'
    ]

    SERVICE_LIST_PATTERNS = [
        r'\b(services|packages|package|available\s*(services|packages)|what\s*(services|work|packages)\s*do\s*you\s*(provide|do|offer))\b'
    ]

    PRICE_PATTERNS = [
        r'\b(price|prices|rate|rates|cost|charges|how\s*much|fees)\b',
        r'\b(ethraya|vila)\b|വില|कीमत',
    ]

    DISCOUNT_PATTERNS = [
        r'\b(discounts?|disounts?|dicounts?|discunts?|offers|promos?|promotions?|coupons?|vouchers?|deals?)\b',
        r'\b(any|special|current|available|ongoing|seasonal|festive|an)\s+(?:\w+\s+){0,2}offer\b',
        r'^\s*offer\b',
        r'\b(best|lowest|last|final)\s+(price|rate)\b',
        r'\b(negotiable|cheaper|price\s+reduction|reduce\s+(?:the\s+)?(?:price|rate))\b',
        r'ഡിസ്കൗണ്ട്|ഓഫർ|छूट|ऑफर',
    ]

    @classmethod
    def is_discount_enquiry(cls, message):
        return any(re.search(pattern, message.strip().lower()) for pattern in cls.DISCOUNT_PATTERNS)

    @staticmethod
    def ac_problem_kind(message):
        """Recognize reported symptoms separately from service/price enquiries."""
        normalized = re.sub(r'[^\w\s]', ' ', message.lower().replace("'", '').replace('’', '')).strip()
        has_ac = bool(re.search(r'\bac\b|\bair\s*conditioner\b', normalized))
        cooling = re.search(
            r'\b(?:not|no|never|isnt|doesnt|didnt|dont|wont|stopped|poor|weak|less)\b'
            r'(?:\s+\w+){0,4}\s+(?:cool(?:ing)?|cold|chill(?:ing)?)\b'
            r'|\bblow(?:ing|s)?\s+(?:only\s+)?(?:hot|warm)\s+air\b', normalized)
        if cooling and (has_ac or cooling.group(0) == normalized):
            return 'cooling'
        if has_ac and re.search(r'\b(problem|issue|broken|malfunction)\b', normalized):
            return 'general'
        return None

    @classmethod
    def detect_intent(cls, message: str) -> Tuple[IntentType, Optional[object]]:
        """
        Analyze incoming message and return (IntentType, matched_entity).
        Matches specific services and FAQs first to give direct, high-precision answers.
        """
        msg = message.strip().lower()

        # Button ID shortcuts from WhatsApp Interactive messages
        if msg.startswith("book_service_") or msg.startswith("book_"):
            raw_id = re.sub(r'^[a-z_]+', '', msg)
            try:
                svc = Service.objects.filter(id=int(raw_id), is_active=True).first()
                return IntentType.BOOKING_START, svc
            except (ValueError, TypeError):
                pass

        if msg.startswith("check_price_") or msg.startswith("price_"):
            raw_id = re.sub(r'^[a-z_]+', '', msg)
            try:
                svc = Service.objects.filter(id=int(raw_id), is_active=True).first()
                return IntentType.SERVICE_PRICE, svc
            except (ValueError, TypeError):
                pass

        if msg in ("view_services", "all_services", "options"):
            return IntentType.SERVICE_LIST, None

        if re.match(r'^(?:service|select_service)_\d+$', msg):
            raw_id = re.sub(r'^[a-z_]+', '', msg)
            try:
                svc = Service.objects.filter(id=int(raw_id), is_active=True).first()
                if svc:
                    return IntentType.SERVICE_SELECT, svc
            except (ValueError, TypeError):
                pass

        if msg in ('talk to team', 'talk to agent', 'human', 'agent'):
            return IntentType.HANDOVER, None
        # 0. Explicit human handover request
        for pat in cls.HANDOVER_PATTERNS:
            if re.search(pat, msg):
                return IntentType.HANDOVER, None

        if re.search(r'\bwho\s+are\s+(?:you|u)\b|\bare\s+(?:you|u)\s+(?:a\s+)?(?:bot|human|robot)\b|\bwhat\s+is\s+your\s+name\b', msg):
            return IntentType.IDENTITY, None

        # 1. Existing Booking Status / Appointment check
        if cls.is_booking_status_enquiry(msg):
            return IntentType.BOOKING_STATUS, None

        # Offer questions stay in scope even when they mention booking or a service.
        if cls.is_discount_enquiry(msg):
            faq = cls.find_matching_faq(msg)
            if faq and cls.is_discount_enquiry(faq.question):
                return IntentType.DISCOUNT_ENQUIRY, faq
            return IntentType.DISCOUNT_ENQUIRY, None

        # 2. New Booking intent
        if re.search(r'\b(book cheyy|booking venam|visit venam)\b|ബുക്ക്|बुक', msg):
            from apps.business.domain import is_it_business
            matched_item = (cls.find_matching_product(msg) or cls.find_matching_service(msg)) if is_it_business() else cls.find_matching_service(msg)
            return IntentType.BOOKING_START, matched_item
        for pat in cls.BOOKING_PATTERNS:
            if re.search(pat, msg):
                from apps.business.domain import is_it_business
                matched_item = (cls.find_matching_product(msg) or cls.find_matching_service(msg)) if is_it_business() else cls.find_matching_service(msg)
                return IntentType.BOOKING_START, matched_item

        # A shop address request can name a service without becoming a price enquiry.
        coverage_question = any(re.search(pat, msg) for pat in cls.AREAS_PATTERNS)
        if not coverage_question and any(re.search(pat, msg) for pat in cls.LOCATION_PATTERNS):
            return IntentType.SHOP_LOCATION, None

        from apps.business.domain import is_it_business
        if is_it_business():
            # Button/action shortcuts for products
            if msg.startswith(('demo_product_', 'book_product_')):
                raw_id = re.sub(r'^[a-z_]+', '', msg)
                try:
                    from apps.business.models import Product
                    prod = Product.objects.filter(id=int(raw_id), is_active=True).first()
                    if prod:
                        return IntentType.BOOKING_START, prod
                except (ValueError, TypeError):
                    pass

            if msg.startswith(('product_', 'check_product_')):
                raw_id = re.sub(r'^[a-z_]+', '', msg)
                try:
                    from apps.business.models import Product
                    prod = Product.objects.filter(id=int(raw_id), is_active=True).first()
                    if prod:
                        return IntentType.PRODUCT_ENQUIRY, prod
                except (ValueError, TypeError):
                    pass

            # Existing Customer Support
            support_target = cls.is_customer_support_enquiry(msg)
            if support_target is not None:
                return IntentType.CUSTOMER_SUPPORT, support_target

            # Product vs Agency Service Comparison
            if (re.search(r'\b(?:custom\s+software|build\s+(?:a\s+)?custom|custom\s+app)\b', msg) and
                    re.search(r'\b(?:tablo|crm|whatsapp\s+crm|ready[\s-]made|existing\s+product)\b', msg)) or \
               re.search(r'\b(?:compare|comparison|difference\s+between)\s+.*(?:custom|tablo|crm)\b', msg):
                matched_prod = cls.find_matching_product(msg)
                return IntentType.PRODUCT_VS_SERVICE, matched_prod

            # Restaurant operational problem probe (unprompted customer problem)
            if re.search(r'\b(?:we\s+run|running|have|our)\s+(?:a\s+)?(?:restaurant|cafe|café|diner|food\s+court|eatery)\b', msg) and \
               re.search(r'\b(?:orders?|kitchen|billing|queue|confusion|confusing|mixed\s+up|delay)\b', msg):
                return IntentType.RESTAURANT_PROBLEM, None

            # WhatsApp lead problem probe
            if re.search(r'\bwhatsapp\b', msg) and re.search(r'\b(?:leads?|enquir(?:y|ies))\b', msg) and \
               re.search(r'\b(?:get\s+lost|missing|missed|unanswered|delay|too\s+many|confusing|follow[\s-]*up)\b', msg):
                return IntentType.WHATSAPP_LEAD_PROBLEM, None

            # Demo request
            if re.search(r'\b(?:demo|walkthrough|preview|presentation)\b', msg):
                matched_prod = cls.find_matching_product(msg)
                matched_svc = cls.find_matching_service(msg)
                if matched_prod:
                    return IntentType.BOOKING_START, matched_prod
                if matched_svc:
                    return IntentType.BOOKING_START, matched_svc
                return IntentType.BOOKING_START, None

            # Product Matching
            matched_prod = cls.find_matching_product(msg)
            if matched_prod:
                # Check price
                for pat in cls.PRICE_PATTERNS:
                    if re.search(pat, msg):
                        return IntentType.PRODUCT_PRICING, matched_prod
                from apps.business.models import Product
                if isinstance(matched_prod, Product):
                    # Check capability or integration query
                    kind, target_obj = cls.find_product_capability_or_integration(matched_prod, msg)
                    if kind == 'capability':
                        return IntentType.PRODUCT_CAPABILITY, (matched_prod, target_obj)
                    if kind == 'integration':
                        return IntentType.PRODUCT_INTEGRATION, (matched_prod, target_obj)
                return IntentType.PRODUCT_ENQUIRY, matched_prod

            # Consultation booking request
            if re.search(r'\b(?:book|schedule|arrange|request)\s+(?:a\s+)?(?:consultation|appointment|call|meeting)\b', msg) or \
               re.search(r'\b(book cheyy|booking venam|consultation venam)\b|ബുക്ക്|बुक', msg):
                matched_svc = cls.find_matching_service(msg)
                return IntentType.BOOKING_START, matched_svc
            for pat in cls.BOOKING_PATTERNS:
                if re.search(pat, msg):
                    matched_svc = cls.find_matching_service(msg)
                    return IntentType.BOOKING_START, matched_svc

            # Agency Service Matching
            matched_svc = cls.find_matching_service(msg)
            if matched_svc:
                for pat in cls.PRICE_PATTERNS:
                    if re.search(pat, msg):
                        return IntentType.SERVICE_PRICE, matched_svc
                if msg == matched_svc.name.lower():
                    return IntentType.SERVICE_SELECT, matched_svc
                return IntentType.SERVICE_PRICE, matched_svc

            # Company overview / what do you do / service list
            if any(re.search(pat, msg) for pat in cls.SERVICE_LIST_PATTERNS) or \
               re.search(r'\bwhat\s+(?:do\s+you|does\s+neoriz)\s+(?:do|provide|offer)\b|\babout\s+neoriz\b', msg):
                return IntentType.SERVICE_LIST, None

        problem = None if is_it_business() else cls.ac_problem_kind(msg)
        price_or_menu = any(re.search(pat, msg) for pat in cls.PRICE_PATTERNS + cls.SERVICE_LIST_PATTERNS)
        if problem and not price_or_menu:
            # A complaint may include a business question; answer that question first.
            for patterns, intent in ((cls.AREAS_PATTERNS, IntentType.SERVICE_AREAS),
                                     (cls.HOURS_PATTERNS, IntentType.WORKING_HOURS),
                                     (cls.PAYMENT_PATTERNS, IntentType.PAYMENT_METHODS),
                                     (cls.WARRANTY_PATTERNS, IntentType.WARRANTY_POLICY)):
                if any(re.search(pat, msg) for pat in patterns):
                    return intent, None
            repair = Service.objects.filter(is_active=True, name__icontains='repair').first()
            return IntentType.AC_PROBLEM, repair

        # 3. Specific Service Price / Lookup Enquiry
        matched_service = cls.find_matching_service(msg)
        if matched_service:
            # If price keywords are used
            for pat in cls.PRICE_PATTERNS:
                if re.search(pat, msg):
                    return IntentType.SERVICE_PRICE, matched_service
            # If user clicked a service option button or entered exact service name
            if msg == matched_service.name.lower():
                return IntentType.SERVICE_SELECT, matched_service
            # If asking about service details
            return IntentType.SERVICE_PRICE, matched_service

        # 3. General Price / Service List Enquiry
        for pat in cls.PRICE_PATTERNS + cls.SERVICE_LIST_PATTERNS:
            if re.search(pat, msg):
                return IntentType.SERVICE_LIST, None


        # 4. Check direct FAQ matches before generic regex
        matched_faq = cls.find_matching_faq(msg)
        if matched_faq:
            return IntentType.FAQ_MATCH, matched_faq

        if coverage_question:
            return IntentType.SERVICE_AREAS, None

        # 5. Working hours & timings
        for pat in cls.HOURS_PATTERNS:
            if re.search(pat, msg):
                return IntentType.WORKING_HOURS, None

        # 7. Payment methods
        for pat in cls.PAYMENT_PATTERNS:
            if re.search(pat, msg):
                return IntentType.PAYMENT_METHODS, None

        # 8. Warranty & policies
        for pat in cls.WARRANTY_PATTERNS:
            if re.search(pat, msg):
                return IntentType.WARRANTY_POLICY, None

        # 10. Greetings
        for pat in cls.GREETING_PATTERNS:
            if re.search(pat, msg):
                return IntentType.GREETING, None

        return IntentType.UNKNOWN, None

    @classmethod
    def is_customer_support_enquiry(cls, message_lower: str):
        """Identify enquiries regarding existing accounts, installations, or technical problems."""
        support_indicators = (
            r'\bexisting\s+(?:customer|client|user|account)\b',
            r'\balready\s+(?:using|have|bought|installed|purchased)\s+(?:tablo|crm|whatsapp|your\s+software|your\s+product)\b',
            r'\b(?:our|my)\s+.*?\b(?:not\s+(?:working|loading)|down|broken|failing|error|issue|problem|bug)\b',
            r'\b(?:not\s+(?:working|loading)|down|broken|failing|error|bug|issue)\s+.*?\b(?:at|in|on|with)\s+(?:our|my|table|outlet|store|pos|qr)\b',
            r'\b(?:technical\s+)?support\s+for\s+(?:our\s+)?(?:tablo|crm|website|app|installation|account)\b',
            r'\baccount\s+reference\b',
            r'\b(?:facing|having)\s+(?:an?\s+)?(?:issue|problem|error|bug)\s+(?:with|in)\s+(?:our\s+)?(?:tablo|crm|website|app)\b',
            r'\b(?:complaint|raised\s+a\s+complaint)\b',
        )
        if any(re.search(pat, message_lower) for pat in support_indicators):
            matched_prod = cls.find_matching_product(message_lower)
            matched_svc = cls.find_matching_service(message_lower)
            return matched_prod or matched_svc or True
        return None

    @classmethod
    def find_matching_product(cls, message_lower: str):
        """
        Search active products (TABLO, WhatsApp Automation + CRM) matching keywords.
        Handles negations and prevents premature matching of custom agency requests.
        """
        from apps.business.models import Product
        active_products = Product.objects.filter(is_active=True)
        if not active_products.exists():
            return None

        # Check button payloads: e.g. demo_product_1, product_1
        m = re.match(r'^(?:demo_|product_|check_product_)?product_(\d+)$', message_lower)
        if m:
            prod = active_products.filter(id=int(m.group(1))).first()
            if prod:
                return prod

        # Handle explicit negations: "not tablo", "don't want tablo", "instead of tablo"
        tablo_negated = bool(re.search(r'\b(?:not|no|don\'t want|dont want|without|instead of)\s+(?:the\s+)?tablo\b', message_lower))
        crm_negated = bool(re.search(r'\b(?:not|no|don\'t want|dont want|without|instead of)\s+(?:the\s+)?(?:crm|whatsapp crm|whatsapp automation)\b', message_lower))

        # Check TABLO keywords
        has_tablo = False
        if not tablo_negated:
            tablo_terms = (
                r'\btablo\b',
                r'\brestaurant\s+(?:software|app|system|solution|pos)\b',
                r'\brestaurant\b.*\b(?:orders?|order management|system for orders|system)\b',
                r'\bqr\s+(?:self\s+)?ordering\b',
                r'\bcounter\s+pickup\s+token\b',
                r'\bfood\s+court\s+ordering\b',
                r'\bcafe\s+ordering\s+(?:software|system|app)\b',
            )
            if any(re.search(term, message_lower) for term in tablo_terms):
                if not re.search(r'\b(?:build|develop|code|create|make)\s+(?:a\s+)?(?:custom|bespoke|new)\s+(?:restaurant\s+)?(?:app|software|website)\b', message_lower):
                    has_tablo = True

        # Check WhatsApp Automation + CRM keywords
        has_crm = False
        if not crm_negated:
            crm_terms = (
                r'\bwhatsapp\s+(?:automation|crm|bot|enquir(?:y|ies)|leads?|follow[\s-]*ups?)\b',
                r'\blead\s+automation\b',
                r'\bwhatsapp\s+customer\s+enquir(?:y|ies)\b',
                r'\b(?:whatsapp\s+business\s+api|whatsapp\s+cloud\s+api)\b',
                r'\bwhatsapp\b.*\b(?:crm|leads?|enquir(?:y|ies)|captur(?:e|ing))\b',
            )
            if any(re.search(term, message_lower) for term in crm_terms):
                has_crm = True

        tablo_obj = active_products.filter(name__iexact='TABLO').first() if has_tablo else None
        crm_obj = active_products.filter(name__icontains='WhatsApp Automation').first() if has_crm else None

        if tablo_obj and crm_obj:
            return (tablo_obj, crm_obj)
        if tablo_obj:
            return tablo_obj
        if crm_obj:
            return crm_obj

        # Also check product aliases field in database
        for prod in active_products:
            if prod.name.lower() in message_lower:
                return prod
            if prod.aliases:
                alias_list = [a.strip().lower() for a in prod.aliases.split(',') if a.strip()]
                for alias in alias_list:
                    if re.search(r'\b' + re.escape(alias) + r'\b', message_lower):
                        return prod

        return None

    @classmethod
    def find_product_capability_or_integration(cls, product, message_lower: str):
        """
        Check if message specifically queries a verified capability or integration.
        Returns ('capability', cap_obj) or ('integration', int_obj) or (None, None).
        """
        caps = product.capabilities.filter(is_active=True)
        for cap in caps:
            name_low = cap.name.lower()
            if 'qr' in name_low and any(w in message_lower for w in ('qr', 'scan', 'camera', 'self ordering', 'self-ordering')):
                return 'capability', cap
            if 'token' in name_low and any(w in message_lower for w in ('token', 'pickup', 'counter slip', 'order token')):
                return 'capability', cap
            if 'pos' in name_low and any(w in message_lower for w in ('pos', 'billing', 'counter billing', 'billing system')):
                return 'capability', cap
            if 'kitchen display' in name_low and any(w in message_lower for w in ('kds', 'kitchen display', 'kitchen screen', 'display screen')):
                return 'capability', cap
            if 'kitchen slip' in name_low and any(w in message_lower for w in ('kitchen slip', 'kot', 'receipt printer')):
                return 'capability', cap
            if 'inventory' in name_low and any(w in message_lower for w in ('inventory', 'recipe', 'ingredient', 'stock')):
                return 'capability', cap
            if 'reporting' in name_low and any(w in message_lower for w in ('report', 'analytics', 'dashboard', 'sales report', 'accounting')):
                return 'capability', cap
            if 'follow-up' in name_low and any(w in message_lower for w in ('follow up', 'follow-up', 'followup', 'reminder', 'reminders', 'drip', 'auto message', 'auto-follow')):
                return 'capability', cap
            if 'shared' in name_low and any(w in message_lower for w in ('shared inbox', 'team inbox', 'multi-agent', 'multi agent', 'multiple agents')):
                return 'capability', cap
            if 'pipeline' in name_low and any(w in message_lower for w in ('pipeline', 'lead stage', 'deal stage', 'kanban')):
                return 'capability', cap
            if 'broadcast' in name_low and any(w in message_lower for w in ('broadcast', 'bulk message', 'campaign', 'mass message', 'marketing message')):
                return 'capability', cap
            if 'qualification' in name_low and any(w in message_lower for w in ('qualify', 'qualification', 'lead capture', 'questions')):
                return 'capability', cap

        ints = product.integrations.filter(is_active=True)
        for int_obj in ints:
            name_low = int_obj.name.lower()
            if 'swiggy' in name_low and any(w in message_lower for w in ('swiggy', 'zomato', 'aggregator', 'online aggregator')):
                return 'integration', int_obj
            if 'pos' in name_low and any(w in message_lower for w in ('pos', 'petpooja', 'posist', 'tally')):
                return 'integration', int_obj
            if 'crm' in name_low and any(w in message_lower for w in ('hubspot', 'salesforce', 'zoho', 'crm integration', 'external crm')):
                return 'integration', int_obj
            if 'payment' in name_low and any(w in message_lower for w in ('payment', 'gateway', 'upi', 'razorpay', 'stripe', 'card payment')):
                return 'integration', int_obj
            if 'cloud api' in name_low and any(w in message_lower for w in ('meta api', 'cloud api', 'official api', 'whatsapp business api')):
                return 'integration', int_obj

        return None, None

    @classmethod
    def find_matching_service(cls, message_lower: str) -> Optional[Service]:
        """
        Search active services in PostgreSQL matching keywords in the message.
        """
        active_services = Service.objects.filter(is_active=True)

        # Check if message is a service button ID like 'service_1' or 'select_service_1'
        m = re.match(r'^(?:service|select_service)_(\d+)$', message_lower)
        if m:
            svc = active_services.filter(id=int(m.group(1))).first()
            if svc:
                return svc

        # Check explicit keywords
        from apps.business.domain import is_it_business
        if is_it_business():
            # If asking about WhatsApp CRM or TABLO product, don't hijack to custom software unless explicit
            is_product_query = any(w in message_lower for w in ('tablo', 'whatsapp crm', 'whatsapp automation', 'restaurant software'))
            is_explicit_custom = any(w in message_lower for w in ('custom software', 'bespoke software', 'software development', 'build custom', 'custom app'))

            aliases = [
                ('website revamp', ('revamp', 'redesign', 'modernize website')),
                ('ecommerce', ('ecommerce', 'e-commerce', 'online store', 'online shop')),
                ('mobile app', ('mobile app', 'android app', 'ios app', 'iphone app', 'flutter app')),
                ('ui/ux', ('ui/ux', 'ui ux', 'interface design', 'ux design')),
                ('software', ('software development', 'custom software', 'business system', 'custom workflow')),
                ('website development', ('website development', 'web development', 'web application', 'web app', 'business website', 'website')),
            ]
            if is_product_query and not is_explicit_custom:
                aliases = [a for a in aliases if a[0] != 'software']

            for name, terms in aliases:
                if any(term in message_lower for term in terms):
                    return active_services.filter(name__icontains=name).first()
            return next((svc for svc in active_services if svc.name.lower() in message_lower), None)

        keywords_map = {
            'gas': ['gas', 'refrigerant', 'freon', 'filling', 'leak', 'cooling'],
            'install': ['install', 'installation', 'fitting', 'mount'],
            'uninstall': ['uninstall', 'uninstallation', 'remove', 'dismantle'],
            'repair': ['repair', 'breakdown', 'noise', 'water leakage', 'not working', 'tripping', 'compressor'],
            'service': ['service', 'servicing', 'cleaning', 'jet', 'wash', 'filter'],
        }

        # Check for service name directly
        for svc in active_services:
            svc_name_lower = svc.name.lower()
            if svc_name_lower in message_lower:
                return svc

        # Water leakage is a repair symptom, not evidence of low refrigerant.
        if cls.ac_problem_kind(message_lower) or any(term in message_lower for term in ('water leak', 'vellam', 'വെള്ളം', 'पानी', 'not cooling', 'not working', 'noise', 'tripping')):
            return active_services.filter(name__icontains='repair').first()
        # Check keyword clusters
        if 'gas' in message_lower or 'refrigerant' in message_lower:
            svc = active_services.filter(name__icontains='gas').first()
            if svc:
                return svc
        if 'uninstall' in message_lower or 'remove' in message_lower:
            svc = active_services.filter(name__icontains='uninstall').first()
            if svc:
                return svc
        if 'install' in message_lower or 'fitting' in message_lower:
            svc = active_services.filter(name__icontains='installation').first()
            if svc:
                return svc
        if 'repair' in message_lower or 'fix' in message_lower or 'broken' in message_lower:
            svc = active_services.filter(name__icontains='repair').first()
            if svc:
                return svc
        if 'cleaning' in message_lower or 'servicing' in message_lower or 'wash' in message_lower:
            svc = active_services.filter(name__icontains='servicing').first()
            if svc:
                return svc

        return None

    @classmethod
    def find_matching_faq(cls, message_lower: str) -> Optional[FAQ]:
        """
        Search active FAQs whose questions contain key query terms.
        """
        faqs = FAQ.objects.filter(is_active=True)
        words = set(re.findall(r'\b\w{4,}\b', message_lower))
        best_match = None
        best_score = 0

        for faq in faqs:
            faq_words = set(re.findall(r'\b\w{4,}\b', faq.question.lower()))
            overlap = len(words.intersection(faq_words))
            if overlap > best_score and overlap >= 2:
                best_score = overlap
                best_match = faq

        return best_match
