"""Customer-facing IT consultation and product sales language in supported languages."""
TEXT = {
    'identity': (
        "I'm the automated assistant for {shop}. I can help with our digital agency services, TABLO restaurant software, and WhatsApp Automation + CRM, or arrange a demo and consultation with our team.",
        "{shop}-inte automated assistant aanu. Agency services, TABLO restaurant software, WhatsApp Automation + CRM ennivayil sahayikkam, allengil team-umayi demo/consultation arrange cheyyam.",
        "{shop}-ന്റെ ഓട്ടോമേറ്റഡ് അസിസ്റ്റന്റാണ്. ഐടി സേവനങ്ങൾ, TABLO റസ്റ്റോറന്റ് സോഫ്റ്റ്‌വെയർ, WhatsApp Automation + CRM എന്നിവയിൽ സഹായിക്കാം, അല്ലെങ്കിൽ ടീമുമായി ബന്ധിപ്പിക്കാം.",
        "मैं {shop} का ऑटोमेटेड असिस्टेंट हूँ। मैं हमारी IT सेवाओं, TABLO रेस्टोरेंट सॉफ्टवेयर और WhatsApp CRM में मदद कर सकता हूँ या टीम से जोड़ सकता हूँ।"
    ),
    'bot_identity': (
        "Yes, I am the automated assistant for {shop}. I can help you explore our services and products, answer questions, or connect you directly with our human team.",
        "Athe, njan {shop}-inte automated assistant aanu. Njangalude IT services, products ennivayil sahayikkam, allengil team-umayi connect cheyyam.",
        "അതെ, ഞാൻ {shop}-ന്റെ ഓട്ടോമേറ്റഡ് അസിസ്റ്റന്റാണ്. ഞങ്ങളുടെ സേവനങ്ങളും ഉൽപ്പന്നങ്ങളും പരിചയപ്പെടാൻ സഹായിക്കാം, അല്ലെങ്കിൽ ടീമുമായി നേരിട്ട് ബന്ധിപ്പിക്കാം.",
        "हाँ, मैं {shop} का ऑटोमेटेड असिस्टेंट हूँ। मैं सेवाओं और उत्पादों की जानकारी दे सकता हूँ या सीधे हमारी टीम से जोड़ सकता हूँ।"
    ),
    'greeting': (
        'How can we help with your IT project, TABLO, or WhatsApp Automation today?',
        'Ningalude IT project, TABLO, allengil WhatsApp Automation karyangalil engane sahayikkam?',
        'നിങ്ങളുടെ ഐടി പ്രോജക്ട്, TABLO അല്ലെങ്കിൽ WhatsApp Automation എന്നിവയിൽ എങ്ങനെ സഹായിക്കാം?',
        'आज आपके IT प्रोजेक्ट, TABLO या WhatsApp Automation में कैसे मदद कर सकते हैं?'
    ),
    'details': (
        'What would you like to build or explore? Briefly describe your requirements.',
        'Enthaanu build cheyyendathu allengil explore cheyyendathu? Requirements churukki parayamo?',
        'എന്താണ് നിർമ്മിക്കാനോ അറിയാനോ ആഗ്രഹിക്കുന്നത്? ആവശ്യങ്ങൾ ചുരുക്കി പറയാമോ?',
        'आप क्या बनाना या जानना चाहते हैं? संक्षेप में अपनी जरूरतें बताएं।'
    ),
    'recipient_type': (
        'What are the project or product requirements for the person or company you are booking for?',
        'Ningal book cheyyunna vyakthiyude/company-yude requirements enthaanu?',
        'നിങ്ങൾ ബുക്ക് ചെയ്യുന്ന വ്യക്തിയുടെയോ സ്ഥാപനത്തിന്റെയോ ആവശ്യങ്ങൾ എന്താണ്?',
        'जिस व्यक्ति या कंपनी के लिए बुक कर रहे हैं, उनकी जरूरतें क्या हैं?'
    ),
    'details_label': (
        'Request category', 'Request category', 'വിഭാഗം', 'श्रेणी'
    ),
    'address': (
        'Please share your organization name and location, or a contact email for confirmation.',
        'Confirmation-ayi organization, location allengil contact email parayamo?',
        'സ്ഥിരീകരണത്തിനായി സ്ഥാപനത്തിന്റെ പേര്, സ്ഥലം അല്ലെങ്കിൽ ഇമെയിൽ നൽകാമോ?',
        'पुष्टि के लिए अपनी संस्था का नाम, स्थान या संपर्क ईमेल बताएं।'
    ),
    'recipient_address': (
        'Please share the recipient organization and location, or a contact email.',
        'Recipient-inte organization, location allengil contact email parayamo?',
        'സേവനം സ്വീകരിക്കുന്ന സ്ഥാപനത്തിന്റെ സ്ഥലം അല്ലെങ്കിൽ ഇമെയിൽ നൽകാമോ?',
        'सेवा प्राप्तकर्ता की संस्था और स्थान, या संपर्क ईमेल बताएं।'
    ),
    'address_label': (
        'Organization / contact', 'Organization / contact', 'സ്ഥാപനം / ബന്ധപ്പെടൽ', 'संस्था / संपर्क'
    ),
    'issue': (
        'What are your requirements for {ac_type}?',
        '{ac_type}-inu enthaanu requirements?',
        '{ac_type}-നുള്ള ആവശ്യങ്ങൾ എന്താണ്?',
        '{ac_type} के लिए आपकी जरूरतें क्या हैं?'
    ),
    'recipient_issue': (
        'What are their requirements for {ac_type}?',
        'Avarkku {ac_type}-inu enthaanu requirements?',
        'അവരുടെ {ac_type}-നുള്ള ആവശ്യങ്ങൾ എന്താണ്?',
        '{ac_type} के लिए उनकी जरूरतें क्या हैं?'
    ),
    'inspection_price': (
        'For *{service}*, our team reviews your requirements and provides a tailored proposal.',
        '*{service}*-inu requirements review cheythu team tailored quote nalkum.',
        '*{service}*-നായി ആവശ്യങ്ങൾ പരിശോധിച്ച് ടീം ക്വോട്ട് നൽകും.',
        '*{service}* के लिए टीम जरूरतें देखकर कोटेशन देगी।'
    ),
    'inspection_quote': (
        'Quote after requirements review.',
        'Requirements review-inu shesham quote.',
        'ആവശ്യങ്ങൾ പരിശോധിച്ച ശേഷം ക്വോട്ട് നൽകും.',
        'जरूरतों की समीक्षा के बाद कोटेशन मिलेगा।'
    ),
    'request_visit': (
        'Would you like to request a consultation or demo?',
        'Consultation allengil demo request cheyyano?',
        'കൺസൾട്ടേഷനോ ഡെമോയോ ആവശ്യമുണ്ടോ?',
        'क्या आप परामर्श या डेमो का अनुरोध करना चाहेंगे?'
    ),
    'book': (
        'Request Consultation / Demo',
        'Consultation / Demo',
        'കൺസൾട്ടേഷൻ / ഡെമോ',
        'परामर्श / डेमो अनुरोध'
    ),
    'ac_issue': (
        'Please describe the service, product, or requirement you need help with.',
        'Eth service, product, allengil requirement-il aanu sahayam vendathu?',
        'ഏത് സേവനത്തിലോ ഉൽപ്പന്നത്തിലോ ആണ് സഹായം വേണ്ടത്?',
        'किस सेवा, प्रोडक्ट या आवश्यकता में मदद चाहिए?'
    ),
    'cooling_issue': (
        'Please describe the technical requirement or problem so our team can review it.',
        'Technical requirement allengil issue parayamo? Team review cheyyum.',
        'സാങ്കേതിക ആവശ്യങ്ങൾ അല്ലെങ്കിൽ പ്രശ്നം വിവരിക്കൂ. ടീം പരിശോധിക്കും.',
        'तकनीकी समस्या या आवश्यकता बताएं ताकि टीम समीक्षा कर सके।'
    ),
    'suggest_repair': (
        'We offer *{service}*. Would you like to schedule a consultation?',
        '*{service}* labhyamaanu. Consultation venamo?',
        '*{service}* ലഭ്യമാണ്. കൺസൾട്ടേഷൻ വേണോ?',
        'हम *{service}* प्रदान करते हैं। क्या आप परामर्श चाहेंगे?'
    ),
    'recipient_ack': (
        "Understood, this request is for someone else. I'll keep you as the requester.",
        'Ithu mattoralkkaanu ennu manassilayi. Requester ningal thanne aayirikkum.',
        'അഭ്യർത്ഥന മറ്റൊരാൾക്കാണെന്ന് മനസ്സിലായി. അഭ്യർത്ഥിക്കുന്ന വ്യക്തിയായി നിങ്ങളെ സൂക്ഷിക്കും.',
        'समझ गया, अनुरोध किसी और के लिए है। अनुरोधकर्ता आप रहेंगे।'
    ),
    'self_ack': (
        'Understood, this request is for you.',
        'Request ningalkkaanu ennu manassilayi.',
        'അഭ്യർത്ഥന നിങ്ങൾക്കാണെന്ന് മനസ്സിലായി.',
        'समझ गया, यह अनुरोध आपके लिए है।'
    ),
    'pending_booking_followup': (
        'Request #{id} is awaiting confirmation. Our team will review your preferred date and time.',
        'Request #{id} confirmation kaathirikkunnu. Samayam team review cheyyum.',
        'അഭ്യർത്ഥന #{id} സ്ഥിരീകരണം കാത്തിരിക്കുന്നു. സമയം ടീം പരിശോധിക്കും.',
        'अनुरोध #{id} पुष्टि की प्रतीक्षा में है। टीम समय की समीक्षा करेगी।'
    ),
    'confirmed_booking_followup': (
        'Request #{id} is confirmed. Contact our team if you need any adjustments.',
        'Request #{id} confirm aayi. Sahayathinu team-ine bandhappeduka.',
        'അഭ്യർത്ഥന #{id} സ്ഥിരീകരിച്ചു. സഹായത്തിന് ടീമിനെ ബന്ധപ്പെടുക.',
        'अनुरोध #{id} की पुष्टि हो गई है। मदद के लिए टीम से संपर्क करें।'
    ),
    'restaurant_probe': (
        'Where does it get difficult most often—taking the order, passing it to the kitchen, or billing?',
        'Evide aanu kooduthal confusion varunnathu—order edukkunnathilo, kitchen-ilekku vidunnathilo, atho billing-ilo?',
        'എവിടെയാണ് കൂടുതൽ ബുദ്ധിമുട്ട് ഉണ്ടാകുന്നത്—ഓർഡർ എടുക്കുന്നതിലോ, കിച്ചണിലേക്ക് നൽകുന്നതിലോ, ബില്ലിംഗിലോ?',
        'सबसे ज़्यादा परेशानी कहाँ होती है—ऑर्डर लेने में, किचन में भेजने में या बिलिंग में?'
    ),
    'support_security_note': (
        'For your security, never share passwords, OTPs, API keys, or financial credentials in chat.',
        'Surakshithathvakkayi password, OTP, API key enniva chat-il share cheyyaruthu.',
        'സുരക്ഷയ്ക്കായി പാസ്‌വേഡ്, OTP, API key എന്നിവ ചാറ്റിൽ നൽകരുത്.',
        'सुरक्षा के लिए कृपया चैट में पासवर्ड, OTP, API key या वित्तीय जानकारी साझा न करें।'
    ),
}
