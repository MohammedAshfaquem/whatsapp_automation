"""Small, deterministic translations for controls that must work without an LLM."""
import re


def detect_language(text, current='en'):
    if re.search(r'[\u0d00-\u0d7f]', text):
        return 'ml'
    if re.search(r'[\u0900-\u097f]', text):
        return 'hi'
    if re.search(r'\b(venam|ethraya|aano|aanu|evide|eppo|njan|vellam|varumo|namaskaram|cheyyanam)\b', text, re.I):
        return 'manglish'
    explicit = {'english': 'en', 'malayalam': 'ml', 'manglish': 'manglish', 'hindi': 'hi'}
    return explicit.get(text.strip().lower(), current)


TEXT = {
    'pending_booking_followup': ('Booking #{id} is awaiting confirmation. Our team will review it and contact you to confirm the visit. I don’t have a confirmed approval time yet.', 'Booking #{id} confirmation kaathirikkunnu. Team review cheythu visit confirm cheyyan ningale contact cheyyum. Approval samayam ithuvare confirm aayittilla.', 'ബുക്കിംഗ് #{id} സ്ഥിരീകരണത്തിനായി കാത്തിരിക്കുകയാണ്. ടീം പരിശോധിച്ച് സന്ദർശനം സ്ഥിരീകരിക്കാൻ നിങ്ങളെ ബന്ധപ്പെടും. സ്ഥിരീകരിക്കുന്ന സമയം ഇപ്പോൾ ലഭ്യമല്ല.', 'बुकिंग #{id} पुष्टि की प्रतीक्षा में है। हमारी टीम समीक्षा करके विजिट की पुष्टि के लिए आपसे संपर्क करेगी। पुष्टि का समय अभी तय नहीं है।'),
    'confirmed_booking_followup': ('Booking #{id} is already confirmed. You can contact our team if you need help with the visit.', 'Booking #{id} confirm aayittundu. Visit sambandhicha sahayathinu team-ne contact cheyyam.', 'ബുക്കിംഗ് #{id} സ്ഥിരീകരിച്ചിട്ടുണ്ട്. സന്ദർശനത്തെക്കുറിച്ച് സഹായം വേണമെങ്കിൽ ടീമിനെ ബന്ധപ്പെടാം.', 'बुकिंग #{id} की पुष्टि हो चुकी है। विजिट में सहायता के लिए हमारी टीम से संपर्क कर सकते हैं।'),
    'which_booking_followup': ('Which booking do you mean? Please send its number, for example #2.', 'Ethu booking aanu? Number ayakkamo, udaharanam #2.', 'ഏത് ബുക്കിംഗിനെക്കുറിച്ചാണ് ചോദിക്കുന്നത്? നമ്പർ അയക്കാമോ, ഉദാഹരണത്തിന് #2.', 'आप किस बुकिंग की बात कर रहे हैं? कृपया उसका नंबर भेजें, जैसे #2।'),
    'clarify_ac_type': ('Sorry, I couldn’t understand the AC type. Is it a Window AC, Split AC, or another type?', 'Sorry, AC type manassilaayilla. Window AC aano, Split AC aano, atho vere type aano?', 'ക്ഷമിക്കണം, AC തരം മനസ്സിലായില്ല. Window AC ആണോ, Split AC ആണോ, മറ്റേതെങ്കിലും തരമാണോ?', 'माफ़ कीजिए, AC का प्रकार समझ नहीं आया। क्या यह Window AC, Split AC या कोई अन्य प्रकार है?'),
    'guess_ac_type': ('Did you mean a {ac_type}? Please say yes, or tell me the correct type.', '{ac_type} aano uddeshichathu? Yes enn parayuka, allenkil shariyaya type parayamo?', 'നിങ്ങൾ ഉദ്ദേശിച്ചത് {ac_type} ആണോ? അതെ എന്ന് പറയുക, അല്ലെങ്കിൽ ശരിയായ തരം നൽകുക.', 'क्या आपका मतलब {ac_type} है? हाँ कहें, या सही प्रकार बताएं।'),
    'identity': ('I’m the automated service assistant for {shop}. I can help with AC services and booking requests, or connect you with the team.', 'Njan {shop}-nte automated service assistant aanu. AC service, booking request ennivayil sahayikkam, allengil team-umayi connect cheyyam.', 'ഞാൻ {shop}-ന്റെ ഓട്ടോമേറ്റഡ് സേവന അസിസ്റ്റന്റാണ്. AC സേവനങ്ങൾക്കും ബുക്കിംഗ് അഭ്യർത്ഥനകൾക്കും സഹായിക്കാം, അല്ലെങ്കിൽ ടീമുമായി ബന്ധിപ്പിക്കാം.', 'मैं {shop} का स्वचालित सेवा सहायक हूं। AC सेवाओं और बुकिंग अनुरोधों में मदद कर सकता हूं या टीम से जोड़ सकता हूं।'),
    'recipient_name': ('What is the name of the friend or service recipient you’re booking for?', 'Visit book cheyyunna friend-inte allengil service recipient-inte peru enthaanu?', 'സേവനം ബുക്ക് ചെയ്യുന്ന സുഹൃത്തിന്റെ അല്ലെങ്കിൽ സേവനം സ്വീകരിക്കുന്ന വ്യക്തിയുടെ പേര് എന്താണ്?', 'आप जिसके लिए बुक कर रहे हैं, उस मित्र या सेवा प्राप्तकर्ता का नाम क्या है?'),
    'recipient_type': ('What type of AC does the service recipient have (for example, Split or Window)?', 'Service recipient-inte AC ethu type aanu (Split / Window)?', 'സേവനം സ്വീകരിക്കുന്ന വ്യക്തിയുടെ AC ഏത് തരമാണ് (Split / Window)?', 'सेवा प्राप्तकर्ता का AC किस प्रकार का है (Split / Window)?'),
    'recipient_issue': ('What issue are they facing with their {ac_type}?', 'Avarude {ac_type}-kku enthu prashnam aanu?', 'അവരുടെ {ac_type}-യിൽ എന്താണ് പ്രശ്നം?', 'उनके {ac_type} में क्या समस्या है?'),
    'recipient_address': ('What is the service recipient’s complete address (house, street, locality and PIN code)?', 'Service recipient-inte poornamaya address (house, street, locality, PIN code) parayamo?', 'സേവനം സ്വീകരിക്കുന്ന വ്യക്തിയുടെ പൂർണ്ണ വിലാസം നൽകാമോ (വീട്, തെരുവ്, സ്ഥലം, PIN code)?', 'सेवा प्राप्तकर्ता का पूरा पता बताएं (घर, सड़क, इलाका और PIN code)।'),
    'recipient_ack': ('Understood—this visit is for someone else. I’ll keep you as the person arranging it.', 'Manassilayi—ee visit mattoralkku vendiyaanu. Arrange cheyyunnathu ningal aanu.', 'മനസ്സിലായി—ഈ സന്ദർശനം മറ്റൊരാൾക്കാണ്. ക്രമീകരിക്കുന്നത് നിങ്ങളാണ്.', 'समझ गया—यह विजिट किसी और के लिए है। इसे व्यवस्थित करने वाले आप रहेंगे।'),
    'self_ack': ('Understood—this visit is for you.', 'Manassilayi—ee visit ningalkku vendiyaanu.', 'മനസ്സിലായി—ഈ സന്ദർശനം നിങ്ങൾക്കാണ്.', 'समझ गया—यह विजिट आपके लिए है।'),
    'recipient_label': ('Service recipient', 'Service recipient', 'സേവനം സ്വീകരിക്കുന്ന വ്യക്തി', 'सेवा प्राप्तकर्ता'),
    'cooling_issue': ('It sounds like your AC isn’t cooling properly. A technician needs to inspect it to identify the cause.', 'Ningalude AC shariyayi thanukkunnilla ennu manassilayi. Kaaranam kandethaan technician parishodhikkanam.', 'നിങ്ങളുടെ AC ശരിയായി തണുപ്പിക്കുന്നില്ലെന്ന് മനസ്സിലായി. കാരണം കണ്ടെത്താൻ ടെക്നീഷ്യൻ പരിശോധിക്കണം.', 'लगता है आपका AC ठीक से ठंडा नहीं कर रहा। कारण जानने के लिए तकनीशियन की जांच जरूरी है।'),
    'ac_issue': ('What issue are you facing with your AC—poor cooling, a leak, noise, or something else?', 'AC-kku enthu prashnam aanu—thanuppu kuravano, leakage aano, shabdam aano, atho vere enthenkilum?', 'AC-യിൽ എന്താണ് പ്രശ്നം—തണുപ്പ് കുറവാണോ, ചോർച്ചയാണോ, ശബ്ദമാണോ, മറ്റെന്തെങ്കിലും ആണോ?', 'आपके AC में क्या समस्या है—कम ठंडक, रिसाव, आवाज़ या कुछ और?'),
    'suggest_repair': ('We offer *{service}*. Would you like to request a visit?', 'Njangal *{service}* cheyyunnundu. Oru visit request cheyyano?', 'ഞങ്ങൾ *{service}* നൽകുന്നു. ഒരു സന്ദർശനത്തിനായി അഭ്യർത്ഥിക്കണോ?', 'हम *{service}* उपलब्ध कराते हैं। क्या आप विजिट का अनुरोध करना चाहेंगे?'),
    'inspection_team': ('Our team can help with the next step. Would you like to talk to them?', 'Adutha nadapadikku team sahayikkum. Team-umayi samsarikkano?', 'അടുത്ത നടപടിക്ക് ടീം സഹായിക്കും. ടീമുമായി സംസാരിക്കണോ?', 'हमारी टीम अगले कदम में मदद कर सकती है। क्या आप उनसे बात करना चाहेंगे?'),
    'no_offer_details': ("Sorry, I don't have any confirmed discount or offer details for this service. Our team can check for you.", 'Sorry, ee service-inu confirm cheytha discount/offer details ente kayyil illa. Team-umayi check cheyyam.', 'ക്ഷമിക്കണം, ഈ സേവനത്തിന് സ്ഥിരീകരിച്ച ഡിസ്കൗണ്ട് അല്ലെങ്കിൽ ഓഫർ വിവരങ്ങൾ ലഭ്യമല്ല. ടീമുമായി പരിശോധിക്കാം.', 'माफ़ कीजिए, इस सेवा के लिए मेरे पास किसी पुष्ट छूट या ऑफर की जानकारी नहीं है। हमारी टीम जांच कर सकती है।'),
    'listed_offer_info': ('Here is our listed offer information:', 'Njangal list cheytha offer vivarangal:', 'ലിസ്റ്റ് ചെയ്ത ഓഫർ വിവരങ്ങൾ:', 'हमारी सूची में दर्ज ऑफर की जानकारी:'),
    'offer_eligibility': ('Our team can confirm whether this applies to your selected service.', 'Ithu ningalude service-inu baadhakamaano enn team confirm cheyyum.', 'ഇത് നിങ്ങളുടെ സേവനത്തിന് ബാധകമാണോ എന്ന് ടീം സ്ഥിരീകരിക്കും.', 'हमारी टीम पुष्टि करेगी कि यह आपकी चुनी हुई सेवा पर लागू है या नहीं।'),
    'returning_greeting': ('Hello{name}! Welcome back to {shop}.', 'Hello{name}! {shop}-ilekku veendum swagatham.', 'നമസ്കാരം{name}! {shop}-ലേക്ക് വീണ്ടും സ്വാഗതം.', 'नमस्ते{name}! {shop} में फिर से स्वागत है।'),
    'unfinished_booking': ('You have an unfinished booking request. Would you like to continue it or start fresh?', 'Oru booking request poorthiyaakkan baakiyundu. Athu thudarano, puthiyathayi thudangano?', 'പൂർത്തിയാകാത്ത ഒരു ബുക്കിംഗ് അഭ്യർത്ഥനയുണ്ട്. അത് തുടരണമോ, പുതുതായി തുടങ്ങണമോ?', 'आपका एक बुकिंग अनुरोध अधूरा है। उसे जारी रखना चाहेंगे या नई शुरुआत करना चाहेंगे?'),
    'continue_booking': ('Continue Booking', 'Booking thudaram', 'ബുക്കിംഗ് തുടരുക', 'बुकिंग जारी रखें'),
    'start_fresh': ('Start Fresh', 'Puthiyathayi thudangam', 'പുതുതായി തുടങ്ങുക', 'नई शुरुआत करें'),
    'name_label': ('Name', 'Peru', 'പേര്', 'नाम'),
    'service_label': ('Service', 'Service', 'സേവനം', 'सेवा'),
    'details_label': ('AC details', 'AC vivarangal', 'AC വിവരങ്ങൾ', 'AC विवरण'),
    'address_label': ('Service address', 'Service address', 'വിലാസം', 'सेवा का पता'),
    'schedule_label': ('Date and time', 'Date um time um', 'തീയതിയും സമയവും', 'तारीख और समय'),
    'review_label': ('Review your request', 'Request nokkam', 'വിവരങ്ങൾ പരിശോധിക്കുക', 'अनुरोध जांचें'),
    'edit_label': ('Edit your details', 'Vivarangal maattam', 'വിവരങ്ങൾ മാറ്റുക', 'विवरण बदलें'),
    'start': ('Let’s arrange your service booking.', 'Service booking thudangam.', 'സേവനം ബുക്ക് ചെയ്യാം.', 'सेवा की बुकिंग शुरू करें।'),
    'name': ('May I have your name, please?', 'Ningalude peru parayamo?', 'നിങ്ങളുടെ പേര് പറയാമോ?', 'कृपया अपना नाम बताएं।'),
    'service': ('Which service would you like to book?', 'Ethu service aanu vendathu?', 'ഏത് സേവനമാണ് വേണ്ടത്?', 'आप कौन सी सेवा बुक करना चाहेंगे?'),
    'details': ('What type of AC do you have (for example, Split or Window)?', 'Ethu type AC aanu (Split allengil Window)?', 'ഏത് തരം AC ആണ് (ഉദാ: Split അല്ലെങ്കിൽ Window)?', 'आपका AC किस प्रकार का है (जैसे Split या Window)?'),
    'issue': ('What issue are you facing with your {ac_type}?', 'Ningalude {ac_type}-kku enthu prashnam aanu?', 'നിങ്ങളുടെ {ac_type}-യിൽ എന്താണ് പ്രശ്നം?', 'आपके {ac_type} में क्या समस्या है?'),
    'booking_help': ('You can type “cancel” or “talk to team” at any time.', 'Eppozhum “cancel” allengil “talk to team” enn type cheyyam.', 'എപ്പോൾ വേണമെങ്കിലും “cancel” അല്ലെങ്കിൽ “talk to team” എന്ന് എഴുതാം.', 'कभी भी “cancel” या “talk to team” लिख सकते हैं।'),
    'inspection_price': ('For *{service}*, we can give you an exact quote after a technician inspects the issue.', '*{service}*-inu technician parishodhichathinu shesham exact quote parayam.', '*{service}*-ന് ടെക്നീഷ്യൻ പരിശോധിച്ച ശേഷം കൃത്യമായ തുക അറിയിക്കാം.', '*{service}* के लिए तकनीशियन की जांच के बाद सही कीमत बता सकते हैं।'),
    'inspection_quote': ('Quote: after technician inspection.', 'Quote: technician parishodhanakku shesham.', 'തുക: ടെക്നീഷ്യന്റെ പരിശോധനയ്ക്ക് ശേഷം.', 'कीमत: तकनीशियन की जांच के बाद।'),
    'duration': ('Estimated duration: {duration}.', 'Ekadesha samayam: {duration}.', 'ഏകദേശ സമയം: {duration}.', 'अनुमानित समय: {duration}।'),
    'request_visit': ('Would you like to request a visit?', 'Oru visit request cheyyano?', 'ഒരു സന്ദർശനത്തിനായി അഭ്യർത്ഥിക്കണോ?', 'क्या आप विजिट का अनुरोध करना चाहेंगे?'),
    'issue_label': ('Issue', 'Prashnam', 'പ്രശ്നം', 'समस्या'),
    'time_for_date': ('You’d prefer {date}—what time would suit you? Our team will confirm availability.', '{date} aanu vendathu—ethu time aanu saukaryam? Availability team confirm cheyyum.', '{date} ആണ് താൽപര്യം—ഏത് സമയമാണ് സൗകര്യം? ലഭ്യത ടീം സ്ഥിരീകരിക്കും.', '{date} पसंद है—कौन सा समय ठीक रहेगा? टीम उपलब्धता की पुष्टि करेगी।'),
    'date_for_time': ('You’d prefer {time}. Which date would suit you? Our team will confirm availability.', '{time} aanu vendathu. Ethu date aanu saukaryam? Availability team confirm cheyyum.', '{time} ആണ് താൽപര്യം. ഏത് തീയതിയാണ് സൗകര്യം? ലഭ്യത ടീം സ്ഥിരീകരിക്കും.', '{time} पसंद है। कौन सी तारीख ठीक रहेगी? टीम उपलब्धता की पुष्टि करेगी।'),
    'invalid_time': ('That time is invalid or has already passed for {date}. What time would suit you instead?', '{date}-inu aa time kazhinju allengil valid alla. Vere ethu time aanu saukaryam?', '{date}-ന് ആ സമയം കഴിഞ്ഞു അല്ലെങ്കിൽ സാധുവല്ല. പകരം ഏത് സമയമാണ് സൗകര്യം?', '{date} के लिए वह समय अमान्य है या बीत चुका है। कौन सा दूसरा समय ठीक रहेगा?'),
    'today': ('Today', 'Innu', 'ഇന്ന്', 'आज'),
    'tomorrow': ('Tomorrow', 'Naale', 'നാളെ', 'कल'),
    'another_date': ('Another date', 'Vere date', 'മറ്റൊരു തീയതി', 'दूसरी तारीख'),
    'choose_date': ('Which date would you prefer? You can type tomorrow or a date in YYYY-MM-DD format.', 'Ethu date aanu vendathu? YYYY-MM-DD pole type cheyyam.', 'ഏത് തീയതിയാണ് താൽപര്യം? YYYY-MM-DD രൂപത്തിൽ എഴുതാം.', 'कौन सी तारीख पसंद है? YYYY-MM-DD रूप में लिख सकते हैं।'),
    'morning': ('Morning', 'Ravile', 'രാവിലെ', 'सुबह'),
    'afternoon': ('Afternoon', 'Uchakku', 'ഉച്ചയ്ക്ക് ശേഷം', 'दोपहर'),
    'evening': ('Evening', 'Vaikunneram', 'വൈകുന്നേരം', 'शाम'),
    'address': ('What is your complete service address (house/flat number, street, locality and PIN code)?', 'House number, street, locality, PIN code ulppedunna service address parayamo?', 'വീട്ടുനമ്പർ, തെരുവ്, സ്ഥലം, PIN code ഉൾപ്പെടുന്ന വിലാസം നൽകാമോ?', 'घर/फ्लैट नंबर, सड़क, इलाका और PIN code सहित पूरा पता बताएं।'),
    'schedule': ('Please share your preferred date and time (e.g. Tomorrow at 11 AM, or YYYY-MM-DD morning). Our team will confirm availability.', 'Preferred date um time um parayamo? Udaharanam: Tomorrow at 11 AM. Availability team confirm cheyyum.', 'ഇഷ്ടപ്പെട്ട തീയതിയും സമയവും നൽകൂ (ഉദാ: Tomorrow at 11 AM). ലഭ്യത ടീം സ്ഥിരീകരിക്കും.', 'पसंदीदा तारीख और समय बताएं (जैसे Tomorrow at 11 AM)। टीम उपलब्धता की पुष्टि करेगी।'),
    'invalid': ('That detail is incomplete. Please try again, or choose Talk to team.', 'Ee vivaram poornamalla. Veendum parayamo? Allengil team-ine bandhappedam.', 'വിവരം പൂർണ്ണമല്ല. വീണ്ടും നൽകൂ, അല്ലെങ്കിൽ ടീമുമായി സംസാരിക്കാം.', 'यह जानकारी अधूरी है। दोबारा बताएं या टीम से बात करें।'),
    'invalid_date': ('Please choose a future date and a time or slot, such as Tomorrow at 11 AM or YYYY-MM-DD morning.', 'Future date um time um tharamo? Udaharanam: Tomorrow at 11 AM.', 'ഭാവിയിലെ തീയതിയും സമയവും നൽകൂ. ഉദാഹരണം: Tomorrow at 11 AM.', 'आने वाली तारीख और समय चुनें, जैसे Tomorrow at 11 AM या YYYY-MM-DD morning।'),
    'review': ('Please review your booking request before submitting:', 'Submit cheyyunnathinu munpu booking details nokkamo:', 'സമർപ്പിക്കുന്നതിന് മുമ്പ് ബുക്കിംഗ് വിവരങ്ങൾ പരിശോധിക്കൂ:', 'जमा करने से पहले बुकिंग विवरण जांचें:'),
    'edit': ('Which detail would you like to edit?', 'Ethu vivaram aanu maattendathu?', 'ഏത് വിവരമാണ് മാറ്റേണ്ടത്?', 'कौन सी जानकारी बदलना चाहेंगे?'),
    'cancelled': ('Your booking request has been cancelled. How else can we help?', 'Booking request cancel cheythu. Ini enthu sahayam venam?', 'ബുക്കിംഗ് അഭ്യർത്ഥന റദ്ദാക്കി. ഇനി എങ്ങനെ സഹായിക്കാം?', 'बुकिंग अनुरोध रद्द कर दिया गया। और कैसे मदद करें?'),
    'submitted': ('Your booking request has been submitted successfully. Status: Pending Confirmation. Our team will review the requested date and time.', 'Booking request submit cheythu. Status: Pending Confirmation. Date um time um team confirm cheyyum.', 'ബുക്കിംഗ് അഭ്യർത്ഥന സമർപ്പിച്ചു. സ്ഥിരീകരണം കാത്തിരിക്കുന്നു. തീയതിയും സമയവും ടീം സ്ഥിരീകരിക്കും.', 'बुकिंग अनुरोध जमा हो गया है। स्थिति: पुष्टि की प्रतीक्षा। टीम तारीख और समय की समीक्षा करेगी।'),
    'greeting': ('How can we help with your AC today?', 'AC sambandhamayi enthu sahayam venam?', 'AC സംബന്ധിച്ച് എങ്ങനെ സഹായിക്കാം?', 'आज आपके AC के लिए कैसे मदद कर सकते हैं?'),
    'team': ('Your conversation has been handed over to our service team. Your messages are saved for them. Type “resume bot” to return to automated help.', 'Conversation service team-inu kaimari. Messages save cheythittundu. Bot venamenkil “resume bot” enn type cheyyuka.', 'സംഭാഷണം സേവന ടീമിന് കൈമാറി. സന്ദേശങ്ങൾ സേവ് ചെയ്തിട്ടുണ്ട്. ബോട്ടിലേക്ക് മടങ്ങാൻ “resume bot” എന്ന് ടൈപ്പ് ചെയ്യൂ.', 'बातचीत सेवा टीम को सौंप दी गई है। आपके संदेश सहेजे गए हैं। बॉट पर लौटने के लिए “resume bot” लिखें।'),
    'view': ('View Services', 'Services kaanam', 'സേവനങ്ങൾ', 'सेवाएं देखें'),
    'book': ('Book a Visit', 'Visit book cheyyam', 'സന്ദർശനം ബുക്ക്', 'विजिट बुक करें'),
    'human': ('Talk to Team', 'Team-umayi samsarikkam', 'ടീമുമായി സംസാരിക്കുക', 'टीम से बात करें'),
    'submit': ('Submit Request', 'Request submit', 'സമർപ്പിക്കുക', 'अनुरोध जमा करें'),
    'edit_button': ('Edit Details', 'Details maattam', 'വിവരങ്ങൾ മാറ്റുക', 'विवरण बदलें'),
    'cancel': ('Cancel', 'Cancel cheyyam', 'റദ്ദാക്കുക', 'रद्द करें'),
    'status': ('Check Status', 'Status nokkam', 'നില പരിശോധിക്കുക', 'स्थिति देखें'),
    'price': ('Check Price', 'Vila nokkam', 'വില പരിശോധിക്കുക', 'कीमत देखें'),
    'resume': ('Resume Assistant', 'Bot thudaram', 'ബോട്ട് തുടരുക', 'बॉट फिर शुरू करें'),
}


def say(key, language='en'):
    return TEXT[key][{'en': 0, 'manglish': 1, 'ml': 2, 'hi': 3}.get(language, 0)]


def choice(action, key, language='en'):
    return {'id': action, 'title': say(key, language)}


def display_input(text, language='en'):
    """Present action payloads as readable history without changing routing data."""
    labels = {'booking_submit': 'submit', 'booking_edit': 'edit_button', 'view_services': 'view'}
    if text in labels:
        return say(labels[text], language)
    selected = re.fullmatch(r'(service|select_service|book_service|check_price)_(\d+)', text)
    if selected:
        from apps.services.models import Service
        service = Service.objects.filter(pk=int(selected[2])).first()
        label = say('book' if selected[1] == 'book_service' else ('price' if selected[1] == 'check_price' else 'view'), language)
        return f'{label} · {service.name}' if service else label
    if text.startswith('booking_edit_'):
        return say('edit_button', language)
    action = re.fullmatch(r'(cancel_booking|confirm_cancel|reschedule_booking)_(\d+)', text)
    if action:
        return f"{'Reschedule' if action[1] == 'reschedule_booking' else 'Cancel'} #{action[2]}"
    return text
