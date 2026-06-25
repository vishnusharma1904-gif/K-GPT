"""Instant canned replies for greetings / identity small-talk — NO LLM call.

For trivially generic messages ("hi", "hello", "how are you", "who are you",
"thanks", etc.) there's no reason to spend tokens or latency on a model. This
module detects those by exact (normalised) phrase match and returns ONE of ten
predefined answers per intent, chosen at random with Python's `random.choice`,
so the bot doesn't repeat itself.

Matching is deliberately strict (exact normalised phrases + a short length cap)
so a real question like "who created the periodic table" is never intercepted —
it only fires on pure small-talk and falls through to the normal RAG/LLM path
otherwise.
"""
from __future__ import annotations

import random
import re

# --- 10 predefined answers per intent ---------------------------------------

GREETING = [
    "Hi there! How can I help you today?",
    "Hello! What can I do for you?",
    "Hey! Ready when you are — what's on your mind?",
    "Hi! Ask me anything — study help, writing, code, or general questions.",
    "Hello! How can I assist you today?",
    "Hey there! What would you like to work on?",
    "Hi! Good to see you. What can I help with?",
    "Hello! I'm here to help — go ahead and ask.",
    "Hey! What can I help you figure out today?",
    "Hi! Let's get started — what do you need?",
]

HOW_ARE_YOU = [
    "I'm doing great, thanks for asking! How can I help you?",
    "All systems go on my end! What can I do for you?",
    "I'm good — always ready to help. What's up?",
    "Doing well, thank you! Shall we tackle your question?",
    "I'm great! More importantly, how can I help you today?",
    "Running smoothly and happy to help! What do you need?",
    "I'm doing wonderfully — ready to assist. What's on your mind?",
    "Feeling helpful as always! What can I do for you?",
    "I'm good, thanks! Let's get to your question.",
    "All good here! How can I make your day easier?",
]

WHO_ARE_YOU = [
    "I'm K-GPT, your campus AI assistant for KSRMCE. I can help with studies, writing, coding, and more.",
    "I'm K-GPT — an AI assistant built for the KSRMCE community. Ask me anything!",
    "K-GPT here! I'm your personal AI study and productivity assistant.",
    "I'm K-GPT, an AI assistant that helps students learn, write, code, and get things done.",
    "I'm K-GPT — your friendly campus AI. I can explain concepts, help with assignments, and answer questions.",
    "I'm K-GPT, an AI assistant made for KSRMCE students and staff. How can I help?",
    "Call me K-GPT — your AI companion for learning and everyday tasks.",
    "I'm K-GPT, a general-purpose AI assistant for the KSRMCE campus.",
    "I'm K-GPT! Think of me as your always-available study and work helper.",
    "I'm K-GPT, your AI assistant. I'm here to help you learn faster and work smarter.",
]

WHO_MADE_YOU = [
    "I was built by Prompt Pulse, a technology company. My developers are Vishnu Sharma (lead) and Shristi.",
    "I'm K-GPT, developed by Prompt Pulse — built by Vishnu Sharma and Shristi.",
    "Prompt Pulse built me; Vishnu Sharma and Shristi led the development.",
    "I was created by Prompt Pulse. Vishnu Sharma and Shristi are my developers.",
    "My maker is a company called Prompt Pulse; the team behind me is Vishnu Sharma and Shristi.",
    "I'm a Prompt Pulse creation, developed by Vishnu Sharma and Shristi.",
    "Prompt Pulse is the company that built me, with Vishnu Sharma and Shristi as developers.",
    "I was developed by Prompt Pulse — Vishnu Sharma (lead developer) and Shristi.",
    "Credit goes to Prompt Pulse, and to developers Vishnu Sharma and Shristi.",
    "I'm K-GPT, made by Prompt Pulse and built by Vishnu Sharma and Shristi.",
]

WHAT_CAN_YOU_DO = [
    "I can help you study, explain tough concepts, write and edit text, debug code, and answer general questions. What do you need?",
    "Lots! Summarise notes, solve problems step by step, write essays, help with code, and more. Try me!",
    "I can explain topics, help with assignments, draft documents, write and fix code, and answer almost anything.",
    "Studying, writing, coding, planning, brainstorming — ask away and I'll help.",
    "I can tutor you on subjects, proofread your work, generate ideas, and assist with programming.",
    "From homework help to writing and coding, I've got you covered. What's the task?",
    "I help with learning, writing, math, code, and everyday questions. What would you like to start with?",
    "I can break down concepts, create study material, write content, and solve coding problems.",
    "Think of me as a tutor, writing assistant, and coding helper in one. What do you need?",
    "I can answer questions, explain ideas, help you write, and work through problems with you.",
]

THANKS = [
    "You're welcome! Happy to help anytime.",
    "Anytime! Let me know if you need anything else.",
    "Glad I could help!",
    "You're welcome — that's what I'm here for!",
    "No problem at all! Ask me whenever you need.",
    "Happy to help! Anything else on your mind?",
    "You got it! I'm here if you need more.",
    "My pleasure! Feel free to ask again.",
    "Anytime! Wishing you the best with your work.",
    "You're welcome! Come back whenever you have a question.",
]

BYE = [
    "Goodbye! Come back anytime you need help.",
    "See you later! Happy studying.",
    "Bye! Take care and good luck.",
    "Catch you later! I'm here whenever you need me.",
    "Goodbye for now — reach out anytime!",
    "See you soon! All the best.",
    "Take care! I'll be here when you return.",
    "Bye! Have a great day.",
    "Until next time — happy learning!",
    "Goodbye! Don't hesitate to come back.",
]

# --- Telugu answer pools (Telugu script + Roman transliteration) ------------

GREETING_TE = [
    "హాయ్! నేను మీకు ఎలా సహాయం చేయగలను? (Haay! Nenu meeku ela sahayam cheyagalanu?)",
    "హలో! మీకు ఏం కావాలి? (Halo! Meeku em kavali?)",
    "నమస్తే! ఈరోజు మీకు ఎలా సహాయపడగలను? (Namaste! Eeroju meeku ela sahayapadagalanu?)",
    "హాయ్! ఏదైనా అడగండి — చదువు, రాయడం, కోడింగ్ లేదా సాధారణ ప్రశ్నలు. (Haay! Edaina adagandi — chaduvu, rayadam, coding leda sadharana prashnalu.)",
    "హలో! మీకు ఎలా సహాయం చేయగలను? (Halo! Meeku ela sahayam cheyagalanu?)",
    "హాయ్! మీరు దేని గురించి పని చేయాలనుకుంటున్నారు? (Haay! Meeru deni gurinchi pani cheyalanukuntunnaru?)",
    "నమస్తే! మిమ్మల్ని కలవడం సంతోషంగా ఉంది. ఎలా సహాయపడగలను? (Namaste! Mimmalni kalavadam santhoshanga undi. Ela sahayapadagalanu?)",
    "హలో! నేను సహాయానికి ఇక్కడ ఉన్నాను — అడగండి. (Halo! Nenu sahayaniki ikkada unnanu — adagandi.)",
    "హాయ్! ఈరోజు మీకు దేనిలో సహాయం కావాలి? (Haay! Eeroju meeku denilo sahayam kavali?)",
    "హాయ్! మొదలుపెడదాం — మీకు ఏం కావాలి? (Haay! Modalupedadaam — meeku em kavali?)",
]

HOW_ARE_YOU_TE = [
    "నేను బాగున్నాను, అడిగినందుకు ధన్యవాదాలు! మీకు ఎలా సహాయం చేయగలను? (Nenu bagunnanu, adiginanduku dhanyavadalu! Meeku ela sahayam cheyagalanu?)",
    "నా వైపు అంతా బాగుంది! మీకు ఏం చేయగలను? (Naa vaipu antha bagundi! Meeku em cheyagalanu?)",
    "నేను బాగున్నాను — ఎప్పుడూ సహాయానికి సిద్ధం. ఏంటి సంగతి? (Nenu bagunnanu — eppudoo sahayaniki siddham. Enti sangati?)",
    "బాగున్నాను, ధన్యవాదాలు! మీ ప్రశ్నను చూద్దామా? (Bagunnanu, dhanyavadalu! Mee prashnanu chooddama?)",
    "నేను చాలా బాగున్నాను! మీకు ఎలా సహాయపడగలను? (Nenu chala bagunnanu! Meeku ela sahayapadagalanu?)",
    "అంతా సాఫీగా ఉంది, సహాయం చేయడానికి సంతోషం! మీకు ఏం కావాలి? (Antha safeega undi, sahayam cheyadaniki santhosham! Meeku em kavali?)",
    "నేను చాలా బాగున్నాను — సహాయానికి సిద్ధం. ఏం ఆలోచిస్తున్నారు? (Nenu chala bagunnanu — sahayaniki siddham. Em alochistunnaru?)",
    "ఎప్పటిలాగే సహాయానికి సిద్ధంగా ఉన్నాను! మీకు ఏం చేయగలను? (Eppatilage sahayaniki siddhanga unnanu! Meeku em cheyagalanu?)",
    "నేను బాగున్నాను, ధన్యవాదాలు! మీ ప్రశ్నకు వద్దాం. (Nenu bagunnanu, dhanyavadalu! Mee prashnaku vaddam.)",
    "ఇక్కడ అంతా బాగుంది! మీ రోజును సులభం చేయడం ఎలా? (Ikkada antha bagundi! Mee rojunu sulabham cheyadam ela?)",
]

WHO_ARE_YOU_TE = [
    "నేను K-GPT, KSRMCE కోసం మీ క్యాంపస్ AI అసిస్టెంట్‌ని. చదువు, రాయడం, కోడింగ్‌లో సహాయం చేస్తాను. (Nenu K-GPT, KSRMCE kosam mee campus AI assistant ni.)",
    "నేను K-GPT — KSRMCE సముదాయం కోసం రూపొందించిన AI అసిస్టెంట్. ఏదైనా అడగండి! (Nenu K-GPT — KSRMCE samudayam kosam rupondinchina AI assistant. Edaina adagandi!)",
    "నేను K-GPT! మీ వ్యక్తిగత AI చదువు మరియు ఉత్పాదకత సహాయకుడిని. (Nenu K-GPT! Mee vyaktigatha AI chaduvu mariyu utpadakatha sahayakudini.)",
    "నేను K-GPT, విద్యార్థులకు నేర్చుకోవడంలో, రాయడంలో, కోడింగ్‌లో సహాయపడే AI. (Nenu K-GPT, vidyarthulaku nerchukovadamlo, rayadamlo, coding lo sahayapade AI.)",
    "నేను K-GPT — మీ స్నేహపూర్వక క్యాంపస్ AI. భావనలను వివరిస్తాను, అసైన్‌మెంట్లలో సహాయం చేస్తాను. (Nenu K-GPT — mee snehapurvaka campus AI.)",
    "నేను K-GPT, KSRMCE విద్యార్థులు మరియు సిబ్బంది కోసం రూపొందించిన AI. ఎలా సహాయపడను? (Nenu K-GPT, KSRMCE vidyarthulu mariyu sibbandi kosam rupondinchina AI.)",
    "నన్ను K-GPT అని పిలవండి — నేర్చుకోవడంలో మరియు రోజువారీ పనుల్లో మీ AI తోడు. (Nannu K-GPT ani pilavandi.)",
    "నేను K-GPT, KSRMCE క్యాంపస్ కోసం ఒక సాధారణ-ప్రయోజన AI అసిస్టెంట్. (Nenu K-GPT, KSRMCE campus kosam oka sadharana-prayojana AI assistant.)",
    "నేను K-GPT! ఎల్లప్పుడూ అందుబాటులో ఉండే మీ చదువు మరియు పని సహాయకుడిని అనుకోండి. (Nenu K-GPT!)",
    "నేను K-GPT, మీ AI అసిస్టెంట్. వేగంగా నేర్చుకోవడంలో సహాయం చేస్తాను. (Nenu K-GPT, mee AI assistant.)",
]

WHO_MADE_YOU_TE = [
    "నన్ను Prompt Pulse అనే సంస్థ తయారు చేసింది. నా డెవలపర్లు విష్ణు శర్మ (లీడ్) మరియు శ్రుష్టి. (Nannu Prompt Pulse ane samstha thayaru chesindi. Naa developerlu Vishnu Sharma (lead) mariyu Shristi.)",
    "నేను K-GPT, Prompt Pulse చేత అభివృద్ధి చేయబడింది — విష్ణు శర్మ మరియు శ్రుష్టి నిర్మించారు. (Nenu K-GPT, Prompt Pulse cheta abhivruddhi cheyabadindi — Vishnu Sharma mariyu Shristi nirminchaaru.)",
    "Prompt Pulse నన్ను తయారు చేసింది; విష్ణు శర్మ మరియు శ్రుష్టి అభివృద్ధికి నాయకత్వం వహించారు. (Prompt Pulse nannu thayaru chesindi; Vishnu Sharma mariyu Shristi abhivruddhiki nayakatvam vahincharu.)",
    "నన్ను Prompt Pulse సృష్టించింది. విష్ణు శర్మ మరియు శ్రుష్టి నా డెవలపర్లు. (Nannu Prompt Pulse srushtinchindi. Vishnu Sharma mariyu Shristi naa developerlu.)",
    "నా సృష్టికర్త Prompt Pulse; నా వెనుక ఉన్న బృందం విష్ణు శర్మ మరియు శ్రుష్టి. (Naa srushtikartha Prompt Pulse; naa venuka unna brundam Vishnu Sharma mariyu Shristi.)",
    "నేను Prompt Pulse సృష్టి, విష్ణు శర్మ మరియు శ్రుష్టి అభివృద్ధి చేశారు. (Nenu Prompt Pulse srushti, Vishnu Sharma mariyu Shristi abhivruddhi chesaru.)",
    "Prompt Pulse నన్ను నిర్మించిన సంస్థ, విష్ణు శర్మ మరియు శ్రుష్టి డెవలపర్లు. (Prompt Pulse nannu nirminchina samstha, Vishnu Sharma mariyu Shristi developerlu.)",
    "నన్ను Prompt Pulse అభివృద్ధి చేసింది — విష్ణు శర్మ (లీడ్ డెవలపర్) మరియు శ్రుష్టి. (Nannu Prompt Pulse abhivruddhi chesindi — Vishnu Sharma (lead developer) mariyu Shristi.)",
    "ఘనత Prompt Pulse కు, మరియు డెవలపర్లు విష్ణు శర్మ మరియు శ్రుష్టికి. (Ghanatha Prompt Pulse ku, mariyu developerlu Vishnu Sharma mariyu Shristi ki.)",
    "నేను K-GPT, Prompt Pulse తయారు చేసింది, విష్ణు శర్మ మరియు శ్రుష్టి నిర్మించారు. (Nenu K-GPT, Prompt Pulse thayaru chesindi, Vishnu Sharma mariyu Shristi nirminchaaru.)",
]

WHAT_CAN_YOU_DO_TE = [
    "నేను చదువులో, భావనలు వివరించడంలో, రాయడంలో, కోడ్ సరిచేయడంలో సహాయం చేయగలను. మీకు ఏం కావాలి? (Nenu chaduvulo, bhavanalu vivarinchadamlo, rayadamlo, code saricheyadamlo sahayam cheyagalanu.)",
    "చాలా! నోట్స్ సంగ్రహించడం, దశలవారీగా సమస్యలు పరిష్కరించడం, వ్యాసాలు రాయడం, కోడింగ్ సహాయం. (Chala! Notes sangrahinchadam, dasalavareega samasyalu pariskarinchadam, vyasalu rayadam, coding sahayam.)",
    "నేను అంశాలను వివరించగలను, అసైన్‌మెంట్లలో సహాయపడగలను, పత్రాలు రాయగలను, కోడ్ రాయగలను. (Nenu amshalanu vivarinchagalanu, assignment lalo sahayapadagalanu, patralu rayagalanu, code rayagalanu.)",
    "చదువు, రాయడం, కోడింగ్, ప్రణాళిక, ఆలోచనలు — అడగండి, నేను సహాయం చేస్తాను. (Chaduvu, rayadam, coding, pranalika, alochanalu — adagandi, nenu sahayam chestanu.)",
    "నేను మీకు సబ్జెక్టులు బోధించగలను, మీ పనిని సరిచూడగలను, ఆలోచనలు ఇవ్వగలను, ప్రోగ్రామింగ్‌లో సహాయపడగలను. (Nenu meeku subjectlu bodhinchagalanu, mee panini sarichoodagalanu, alochanalu ivvagalanu, programming lo sahayapadagalanu.)",
    "హోంవర్క్ నుండి రాయడం, కోడింగ్ వరకు అన్నీ చేయగలను. పని ఏంటి? (Homework nundi rayadam, coding varaku anni cheyagalanu. Pani enti?)",
    "నేను నేర్చుకోవడం, రాయడం, గణితం, కోడ్, రోజువారీ ప్రశ్నలలో సహాయం చేస్తాను. (Nenu nerchukovadam, rayadam, ganitham, code, rojuvaree prashnalalo sahayam chestanu.)",
    "నేను భావనలను విడదీయగలను, చదువు సామగ్రి తయారు చేయగలను, కంటెంట్ రాయగలను, కోడింగ్ సమస్యలు పరిష్కరించగలను. (Nenu bhavanalanu vidadeeyagalanu, chaduvu samagri thayaru cheyagalanu, content rayagalanu, coding samasyalu pariskarinchagalanu.)",
    "నన్ను ఒక ట్యూటర్, రైటింగ్ అసిస్టెంట్, కోడింగ్ సహాయకుడిగా అనుకోండి. మీకు ఏం కావాలి? (Nannu oka tutor, writing assistant, coding sahayakudiga anukondi.)",
    "నేను ప్రశ్నలకు సమాధానం ఇవ్వగలను, ఆలోచనలు వివరించగలను, రాయడంలో సహాయపడగలను. (Nenu prashnalaku samadhanam ivvagalanu, alochanalu vivarinchagalanu, rayadamlo sahayapadagalanu.)",
]

THANKS_TE = [
    "మీకు స్వాగతం! ఎప్పుడైనా సహాయం చేయడానికి సంతోషం. (Meeku swagatam! Eppudaina sahayam cheyadaniki santhosham.)",
    "ఎప్పుడైనా! ఇంకేమైనా కావాలంటే చెప్పండి. (Eppudaina! Inkemaina kavalante cheppandi.)",
    "నేను సహాయం చేయగలిగినందుకు సంతోషం! (Nenu sahayam cheyaliginanduku santhosham!)",
    "మీకు స్వాగతం — అందుకే నేను ఇక్కడ ఉన్నాను! (Meeku swagatam — anduke nenu ikkada unnanu!)",
    "ఏ సమస్య లేదు! మీకు అవసరమైనప్పుడు అడగండి. (E samasya ledu! Meeku avasaramaina ppudu adagandi.)",
    "సహాయం చేయడానికి సంతోషం! ఇంకేమైనా ఉందా? (Sahayam cheyadaniki santhosham! Inkemaina unda?)",
    "మీరే! ఇంకా అవసరమైతే నేను ఇక్కడ ఉన్నాను. (Meere! Inka avasaramaite nenu ikkada unnanu.)",
    "నా సంతోషం! మళ్ళీ అడగడానికి సంకోచించకండి. (Naa santhosham! Malli adagadaniki sankochinchakandi.)",
    "ఎప్పుడైనా! మీ పనికి శుభాకాంక్షలు. (Eppudaina! Mee paniki subhakankshalu.)",
    "మీకు స్వాగతం! ప్రశ్న ఉన్నప్పుడల్లా తిరిగి రండి. (Meeku swagatam! Prashna unnappudalla thirigi randi.)",
]

BYE_TE = [
    "వీడ్కోలు! సహాయం కావాలంటే ఎప్పుడైనా తిరిగి రండి. (Veedkolu! Sahayam kavalante eppudaina thirigi randi.)",
    "మళ్ళీ కలుద్దాం! హ్యాపీ స్టడీయింగ్. (Malli kaluddam! Happy studying.)",
    "బై! జాగ్రత్త, ఆల్ ది బెస్ట్. (Bye! Jagratha, all the best.)",
    "తర్వాత కలుద్దాం! అవసరమైనప్పుడు నేను ఇక్కడ ఉన్నాను. (Tarvatha kaluddam! Avasaramaina ppudu nenu ikkada unnanu.)",
    "ప్రస్తుతానికి వీడ్కోలు — ఎప్పుడైనా సంప్రదించండి! (Prastutaniki veedkolu — eppudaina sampradinchandi!)",
    "త్వరలో కలుద్దాం! ఆల్ ది బెస్ట్. (Tvaralo kaluddam! All the best.)",
    "జాగ్రత్త! మీరు తిరిగి వచ్చినప్పుడు నేను ఇక్కడ ఉంటాను. (Jagratha! Meeru thirigi vachina ppudu nenu ikkada untanu.)",
    "బై! మంచి రోజు గడపండి. (Bye! Manchi roju gadapandi.)",
    "మళ్ళీ కలిసే వరకు — హ్యాపీ లెర్నింగ్! (Malli kalise varaku — happy learning!)",
    "వీడ్కోలు! తిరిగి రావడానికి సంకోచించకండి. (Veedkolu! Thirigi ravadaniki sankochinchakandi.)",
]

# --- Hindi answer pools (Devanagari + Roman transliteration) ----------------

GREETING_HI = [
    "नमस्ते! मैं आपकी कैसे मदद कर सकता हूँ? (Namaste! Main aapki kaise madad kar sakta hoon?)",
    "हैलो! आपको क्या चाहिए? (Hello! Aapko kya chahiye?)",
    "नमस्ते! आज मैं आपकी कैसे सहायता करूँ? (Namaste! Aaj main aapki kaise sahayata karoon?)",
    "हाय! कुछ भी पूछें — पढ़ाई, लेखन, कोडिंग या सामान्य प्रश्न. (Haay! Kuch bhi poochein — padhai, lekhan, coding ya samanya prashn.)",
    "हैलो! मैं आपकी कैसे मदद करूँ? (Hello! Main aapki kaise madad karoon?)",
    "हाय! आप किस पर काम करना चाहते हैं? (Haay! Aap kis par kaam karna chahte hain?)",
    "नमस्ते! आपसे मिलकर खुशी हुई. कैसे मदद करूँ? (Namaste! Aapse milkar khushi hui. Kaise madad karoon?)",
    "हैलो! मैं मदद के लिए यहाँ हूँ — पूछिए. (Hello! Main madad ke liye yahan hoon — poochiye.)",
    "हाय! आज आपको किसमें मदद चाहिए? (Haay! Aaj aapko kismein madad chahiye?)",
    "हाय! चलिए शुरू करें — आपको क्या चाहिए? (Haay! Chaliye shuru karein — aapko kya chahiye?)",
]

HOW_ARE_YOU_HI = [
    "मैं बढ़िया हूँ, पूछने के लिए धन्यवाद! मैं आपकी कैसे मदद करूँ? (Main badhiya hoon, poochne ke liye dhanyavaad! Main aapki kaise madad karoon?)",
    "मेरी तरफ़ सब ठीक है! मैं आपके लिए क्या करूँ? (Meri taraf sab theek hai! Main aapke liye kya karoon?)",
    "मैं अच्छा हूँ — हमेशा मदद के लिए तैयार. क्या हाल है? (Main achha hoon — hamesha madad ke liye taiyaar. Kya haal hai?)",
    "अच्छा हूँ, धन्यवाद! क्या हम आपके प्रश्न पर आएँ? (Achha hoon, dhanyavaad! Kya hum aapke prashn par aayein?)",
    "मैं बहुत अच्छा हूँ! मैं आपकी कैसे सहायता करूँ? (Main bahut achha hoon! Main aapki kaise sahayata karoon?)",
    "सब कुछ ठीक चल रहा है, मदद करके खुशी होगी! आपको क्या चाहिए? (Sab kuch theek chal raha hai! Aapko kya chahiye?)",
    "मैं बहुत बढ़िया हूँ — मदद के लिए तैयार. क्या सोच रहे हैं? (Main bahut badhiya hoon — madad ke liye taiyaar. Kya soch rahe hain?)",
    "हमेशा की तरह मदद के लिए तैयार हूँ! मैं क्या करूँ? (Hamesha ki tarah madad ke liye taiyaar hoon! Main kya karoon?)",
    "मैं अच्छा हूँ, धन्यवाद! चलिए आपके सवाल पर आते हैं. (Main achha hoon, dhanyavaad! Chaliye aapke sawaal par aate hain.)",
    "यहाँ सब अच्छा है! आपका दिन आसान कैसे बनाऊँ? (Yahan sab achha hai! Aapka din aasaan kaise banaoon?)",
]

WHO_ARE_YOU_HI = [
    "मैं K-GPT हूँ, KSRMCE के लिए आपका कैंपस AI असिस्टेंट. पढ़ाई, लेखन, कोडिंग में मदद करता हूँ. (Main K-GPT hoon, KSRMCE ke liye aapka campus AI assistant.)",
    "मैं K-GPT — KSRMCE समुदाय के लिए बनाया गया AI असिस्टेंट. कुछ भी पूछें! (Main K-GPT — KSRMCE samuday ke liye banaya gaya AI assistant. Kuch bhi poochein!)",
    "मैं K-GPT हूँ! आपका निजी AI पढ़ाई और उत्पादकता सहायक. (Main K-GPT hoon! Aapka niji AI padhai aur utpadakata sahayak.)",
    "मैं K-GPT, विद्यार्थियों को सीखने, लिखने और कोडिंग में मदद करने वाला AI. (Main K-GPT, vidyarthiyon ko seekhne, likhne aur coding mein madad karne wala AI.)",
    "मैं K-GPT — आपका मित्रवत कैंपस AI. अवधारणाएँ समझाता हूँ, असाइनमेंट में मदद करता हूँ. (Main K-GPT — aapka mitravat campus AI.)",
    "मैं K-GPT, KSRMCE के विद्यार्थियों और स्टाफ़ के लिए बनाया गया AI. कैसे मदद करूँ? (Main K-GPT, KSRMCE ke vidyarthiyon aur staff ke liye banaya gaya AI.)",
    "मुझे K-GPT कहें — सीखने और रोज़मर्रा के कामों में आपका AI साथी. (Mujhe K-GPT kahein — seekhne aur rozmarra ke kaamon mein aapka AI saathi.)",
    "मैं K-GPT, KSRMCE कैंपस के लिए एक सामान्य-उद्देश्य AI असिस्टेंट. (Main K-GPT, KSRMCE campus ke liye ek samanya-uddeshya AI assistant.)",
    "मैं K-GPT! हमेशा उपलब्ध आपका पढ़ाई और काम का सहायक समझिए. (Main K-GPT! Hamesha uplabdh aapka padhai aur kaam ka sahayak samajhiye.)",
    "मैं K-GPT, आपका AI असिस्टेंट. तेज़ी से सीखने में मदद करता हूँ. (Main K-GPT, aapka AI assistant. Tezi se seekhne mein madad karta hoon.)",
]

WHO_MADE_YOU_HI = [
    "मुझे Prompt Pulse नामक कंपनी ने बनाया है. मेरे डेवलपर विष्णु शर्मा (लीड) और श्रुष्टि हैं. (Mujhe Prompt Pulse ne banaya hai. Mere developer Vishnu Sharma (lead) aur Shristi hain.)",
    "मैं K-GPT, Prompt Pulse द्वारा विकसित — विष्णु शर्मा और श्रुष्टि ने बनाया. (Main K-GPT, Prompt Pulse dwara vikasit — Vishnu Sharma aur Shristi ne banaya.)",
    "Prompt Pulse ने मुझे बनाया; विष्णु शर्मा और श्रुष्टि ने विकास का नेतृत्व किया. (Prompt Pulse ne mujhe banaya; Vishnu Sharma aur Shristi ne vikas ka netritva kiya.)",
    "मुझे Prompt Pulse ने बनाया. विष्णु शर्मा और श्रुष्टि मेरे डेवलपर हैं. (Mujhe Prompt Pulse ne banaya. Vishnu Sharma aur Shristi mere developer hain.)",
    "मेरे निर्माता Prompt Pulse हैं; मेरे पीछे की टीम विष्णु शर्मा और श्रुष्टि है. (Mere nirmata Prompt Pulse hain; meri team Vishnu Sharma aur Shristi hai.)",
    "मैं Prompt Pulse की रचना हूँ, विष्णु शर्मा और श्रुष्टि ने विकसित किया. (Main Prompt Pulse ki rachna hoon, Vishnu Sharma aur Shristi ne vikasit kiya.)",
    "Prompt Pulse वह कंपनी है जिसने मुझे बनाया, विष्णु शर्मा और श्रुष्टि डेवलपर हैं. (Prompt Pulse vah company hai jisne mujhe banaya, Vishnu Sharma aur Shristi developer hain.)",
    "मुझे Prompt Pulse ने विकसित किया — विष्णु शर्मा (लीड डेवलपर) और श्रुष्टि. (Mujhe Prompt Pulse ne vikasit kiya — Vishnu Sharma (lead developer) aur Shristi.)",
    "श्रेय Prompt Pulse को, और डेवलपर विष्णु शर्मा और श्रुष्टि को. (Shrey Prompt Pulse ko, aur developer Vishnu Sharma aur Shristi ko.)",
    "मैं K-GPT, Prompt Pulse ने बनाया, विष्णु शर्मा और श्रुष्टि ने विकसित किया. (Main K-GPT, Prompt Pulse ne banaya, Vishnu Sharma aur Shristi ne vikasit kiya.)",
]

WHAT_CAN_YOU_DO_HI = [
    "मैं पढ़ाई, अवधारणाएँ समझाने, लेखन और कोड ठीक करने में मदद कर सकता हूँ. आपको क्या चाहिए? (Main padhai, avdharnaayein samjhane, lekhan aur code theek karne mein madad kar sakta hoon.)",
    "बहुत कुछ! नोट्स का सारांश, चरण-दर-चरण समस्या हल, निबंध लेखन, कोडिंग मदद. (Bahut kuch! Notes ka saaransh, charan-dar-charan samasya hal, nibandh lekhan, coding madad.)",
    "मैं विषय समझा सकता हूँ, असाइनमेंट में मदद कर सकता हूँ, दस्तावेज़ और कोड लिख सकता हूँ. (Main vishay samjha sakta hoon, assignment mein madad kar sakta hoon.)",
    "पढ़ाई, लेखन, कोडिंग, योजना, विचार — पूछें, मैं मदद करूँगा. (Padhai, lekhan, coding, yojana, vichar — poochein, main madad karoonga.)",
    "मैं आपको विषय पढ़ा सकता हूँ, आपके काम की जाँच कर सकता हूँ, विचार दे सकता हूँ, प्रोग्रामिंग में मदद कर सकता हूँ. (Main aapko vishay padha sakta hoon, programming mein madad kar sakta hoon.)",
    "होमवर्क से लेकर लेखन और कोडिंग तक सब कर सकता हूँ. काम क्या है? (Homework se lekar lekhan aur coding tak sab kar sakta hoon. Kaam kya hai?)",
    "मैं सीखने, लेखन, गणित, कोड और रोज़मर्रा के प्रश्नों में मदद करता हूँ. (Main seekhne, lekhan, ganit, code aur rozmarra ke prashnon mein madad karta hoon.)",
    "मैं अवधारणाएँ सरल कर सकता हूँ, अध्ययन सामग्री बना सकता हूँ, कोडिंग समस्याएँ हल कर सकता हूँ. (Main avdharnaayein saral kar sakta hoon, coding samasyaayein hal kar sakta hoon.)",
    "मुझे एक ट्यूटर, लेखन सहायक और कोडिंग सहायक समझिए. आपको क्या चाहिए? (Mujhe ek tutor, lekhan sahayak aur coding sahayak samajhiye.)",
    "मैं प्रश्नों का उत्तर दे सकता हूँ, विचार समझा सकता हूँ, लेखन में मदद कर सकता हूँ. (Main prashnon ka uttar de sakta hoon, lekhan mein madad kar sakta hoon.)",
]

THANKS_HI = [
    "आपका स्वागत है! कभी भी मदद के लिए तैयार. (Aapka swagat hai! Kabhi bhi madad ke liye taiyaar.)",
    "कभी भी! कुछ और चाहिए तो बताएँ. (Kabhi bhi! Kuch aur chahiye to bataayein.)",
    "मुझे मदद करके खुशी हुई! (Mujhe madad karke khushi hui!)",
    "आपका स्वागत है — इसी के लिए तो मैं हूँ! (Aapka swagat hai — isi ke liye to main hoon!)",
    "कोई बात नहीं! जब ज़रूरत हो पूछें. (Koi baat nahin! Jab zaroorat ho poochein.)",
    "मदद करके खुशी हुई! और कुछ? (Madad karke khushi hui! Aur kuch?)",
    "बिल्कुल! ज़रूरत हो तो मैं यहाँ हूँ. (Bilkul! Zaroorat ho to main yahan hoon.)",
    "मेरी खुशी! फिर से पूछने में संकोच न करें. (Meri khushi! Phir se poochne mein sankoch na karein.)",
    "कभी भी! आपके काम के लिए शुभकामनाएँ. (Kabhi bhi! Aapke kaam ke liye shubhkamnaayein.)",
    "आपका स्वागत है! प्रश्न हो तो वापस आएँ. (Aapka swagat hai! Prashn ho to wapas aayein.)",
]

BYE_HI = [
    "अलविदा! मदद चाहिए तो कभी भी वापस आएँ. (Alvida! Madad chahiye to kabhi bhi wapas aayein.)",
    "फिर मिलेंगे! हैप्पी स्टडीइंग. (Phir milenge! Happy studying.)",
    "बाय! ध्यान रखें, शुभकामनाएँ. (Bye! Dhyan rakhein, shubhkamnaayein.)",
    "बाद में मिलते हैं! ज़रूरत हो तो मैं यहाँ हूँ. (Baad mein milte hain! Zaroorat ho to main yahan hoon.)",
    "अभी के लिए अलविदा — कभी भी संपर्क करें! (Abhi ke liye alvida — kabhi bhi sampark karein!)",
    "जल्द मिलेंगे! शुभकामनाएँ. (Jald milenge! Shubhkamnaayein.)",
    "ध्यान रखें! जब लौटें, मैं यहाँ रहूँगा. (Dhyan rakhein! Jab lautein, main yahan rahoonga.)",
    "बाय! आपका दिन शुभ हो. (Bye! Aapka din shubh ho.)",
    "अगली बार तक — हैप्पी लर्निंग! (Agli baar tak — happy learning!)",
    "अलविदा! वापस आने में संकोच न करें. (Alvida! Wapas aane mein sankoch na karein.)",
]

# --- Intent → trigger phrases (normalised: lowercase, alphanumerics + spaces) -
# Each intent is matched only when the cleaned message EQUALS one of its phrases.
_INTENTS: list[tuple[set[str], list[str]]] = [
    ({"hi", "hii", "hiii", "hello", "helo", "hey", "heya", "hiya", "yo", "hii there",
      "hi there", "hello there", "hey there", "good morning", "good afternoon",
      "good evening", "gm", "greetings", "hello kgpt", "hi kgpt"}, GREETING),
    ({"how are you", "how are you doing", "how r u", "how ru", "how are u",
      "hows it going", "how is it going", "how do you do", "whats up", "what's up",
      "wassup", "sup", "how you doing", "how are things", "you good", "are you ok",
      "how are you today"}, HOW_ARE_YOU),
    ({"who are you", "what are you", "whats your name", "what's your name",
      "what is your name", "who r u", "who are u", "introduce yourself",
      "tell me about yourself", "your name", "who are you kgpt", "what is kgpt",
      "whats kgpt", "what is k gpt"}, WHO_ARE_YOU),
    ({"who made you", "who created you", "who built you", "who developed you",
      "who is your developer", "who is your creator", "who designed you",
      "who owns you", "who is behind you", "who made u", "who created u",
      "who programmed you", "who is your maker"}, WHO_MADE_YOU),
    ({"what can you do", "what do you do", "how can you help", "how can you help me",
      "what can you help with", "help", "what are your features", "what can u do",
      "what all can you do", "what can you help me with", "how do you work",
      "what are you capable of", "what are your capabilities", "what is your capability",
      "what are your abilities", "tell me your capabilities", "what can you do for me",
      "show me what you can do", "what do you offer", "what are your skills",
      "what are your functions"}, WHAT_CAN_YOU_DO),
    ({"thanks", "thank you", "thx", "ty", "thank u", "thanks a lot", "thankyou",
      "thank you so much", "much appreciated", "thanks kgpt", "thank you kgpt",
      "cool thanks", "ok thanks", "great thanks"}, THANKS),
    ({"bye", "goodbye", "good bye", "see you", "see ya", "see you later", "cya",
      "good night", "gn", "take care", "bye bye", "see you soon", "farewell",
      "im leaving", "talk later"}, BYE),

    # --- Telugu (script + Tenglish) → Telugu answers ---
    ({"హాయ్", "హలో", "నమస్తే", "నమస్కారం", "శుభోదయం", "శుభ సాయంత్రం", "హాయ్ kgpt",
      "namaste", "namaskaram", "haay", "halo", "subhodayam"}, GREETING_TE),
    ({"ఎలా ఉన్నావు", "ఎలా ఉన్నారు", "మీరు ఎలా ఉన్నారు", "నువ్వు ఎలా ఉన్నావు", "ఎలా ఉన్నావ్",
      "ela unnaru", "ela unnav", "ela unnavu", "meeru ela unnaru", "nuvvu ela unnav",
      "ela unnaru kgpt"}, HOW_ARE_YOU_TE),
    ({"నువ్వు ఎవరు", "మీరు ఎవరు", "నీ పేరు ఏమిటి", "నువ్వు ఎవరివి", "నీ పేరు ఏంటి",
      "nuvvu evaru", "meeru evaru", "nee peru emiti", "nee peru enti",
      "nuvvu evaru kgpt"}, WHO_ARE_YOU_TE),
    ({"నిన్ను ఎవరు తయారు చేశారు", "నిన్ను ఎవరు సృష్టించారు", "నిన్ను ఎవరు డెవలప్ చేశారు",
      "నీ డెవలపర్ ఎవరు", "నిన్ను ఎవరు చేశారు", "ninnu evaru thayaru chesaru",
      "nee developer evaru", "ninnu evaru create chesaru", "ninnu evaru chesaru"}, WHO_MADE_YOU_TE),
    ({"నువ్వు ఏం చేయగలవు", "మీరు ఏం చేయగలరు", "నాకు ఎలా సహాయం చేయగలవు", "నువ్వు ఏం చేస్తావు",
      "nuvvu em cheyagalavu", "meeru em cheyagalaru", "naaku ela help cheyagalavu",
      "nuvvu em chestavu"}, WHAT_CAN_YOU_DO_TE),
    ({"ధన్యవాదాలు", "కృతజ్ఞతలు", "థాంక్స్", "చాలా ధన్యవాదాలు", "dhanyavadalu",
      "krutagnathalu", "thanks andi"}, THANKS_TE),
    ({"వీడ్కోలు", "బై", "మళ్ళీ కలుద్దాం", "శుభ రాత్రి", "సెలవు", "veedkolu",
      "malli kaluddam", "selavu", "bye andi"}, BYE_TE),

    # --- Hindi (Devanagari + Hinglish) → Hindi answers ---
    ({"नमस्ते", "नमस्कार", "हैलो", "हाय", "सुप्रभात", "namaste ji", "hello ji",
      "namaskar"}, GREETING_HI),
    ({"आप कैसे हैं", "तुम कैसे हो", "कैसे हो", "कैसे हैं आप", "क्या हाल है",
      "aap kaise ho", "aap kaise hain", "tum kaise ho", "kaise ho", "kya haal hai",
      "kaise hain aap"}, HOW_ARE_YOU_HI),
    ({"तुम कौन हो", "आप कौन हैं", "तुम्हारा नाम क्या है", "तुम क्या हो", "आपका नाम क्या है",
      "tum kaun ho", "aap kaun hain", "tumhara naam kya hai", "tum kya ho",
      "aapka naam kya hai"}, WHO_ARE_YOU_HI),
    ({"तुम्हें किसने बनाया", "आपको किसने बनाया", "तुम्हारा डेवलपर कौन है",
      "तुम्हें किसने विकसित किया", "tumhe kisne banaya", "aapko kisne banaya",
      "tumhara developer kaun hai"}, WHO_MADE_YOU_HI),
    ({"तुम क्या कर सकते हो", "आप क्या कर सकते हैं", "तुम कैसे मदद कर सकते हो",
      "मेरी कैसे मदद करोगे", "tum kya kar sakte ho", "aap kya kar sakte hain",
      "meri kaise madad karoge"}, WHAT_CAN_YOU_DO_HI),
    ({"धन्यवाद", "शुक्रिया", "थैंक्स", "बहुत धन्यवाद", "dhanyavaad", "shukriya",
      "bahut dhanyavaad"}, THANKS_HI),
    ({"अलविदा", "बाय", "फिर मिलेंगे", "शुभ रात्रि", "alvida", "phir milenge",
      "bye bhai"}, BYE_HI),
]

# Keep ASCII alphanumerics, the Perso-Arabic block (U+0600–U+06FF, for Urdu/etc.)
# and the contiguous Indic block (U+0900–U+0D7F: Devanagari, Bengali, Gurmukhi,
# Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam). Other scripts simply fall
# through to the LLM, which answers in-language via the system-prompt rule.
_CLEAN_RE = re.compile(r"[^a-z0-9 ؀-ۿऀ-ൿ]+")
_MAX_LEN = 80  # only short, pure small-talk is eligible


def _clean(message: str) -> str:
    return _CLEAN_RE.sub(" ", (message or "").lower()).strip()


def _normalise_spaces(s: str) -> str:
    return " ".join(s.split())


def match(message: str) -> str | None:
    """Return a random predefined answer if `message` is recognised small-talk,
    else None (so the caller falls through to the normal RAG/LLM path)."""
    cleaned = _normalise_spaces(_clean(message))
    if not cleaned or len(cleaned) > _MAX_LEN:
        return None
    for variant in (cleaned, _normalise_spaces(_strip_filler(cleaned))):
        for phrases, answers in _INTENTS:
            if variant in phrases:
                return random.choice(answers)
    return None


# --- Looser casual-message gate (used to SKIP knowledge-base retrieval) -------
# `match()` is strict (exact phrase) so it never hijacks a real question. This
# detector is intentionally looser: it answers "is this just chit-chat?" so the
# caller can avoid an unnecessary KB / vector search for greetings, thanks, byes
# and other non-educational one-liners (e.g. "hi hello", "ok thanks bro",
# "good morning sir"). It stays conservative — any real keyword makes it False —
# so substantive questions still trigger retrieval.
_CASUAL_TOKENS = {
    "hi", "hii", "hiii", "hiiii", "hello", "helo", "hey", "heya", "hiya", "yo",
    "sup", "wassup", "wsg", "wyd", "there", "greetings", "gm", "gn",
    "good", "morning", "afternoon", "evening", "night",
    "how", "are", "you", "u", "r", "ru", "doing", "hows", "its", "going",
    "is", "it", "whats", "up", "wassup", "things",
    "thanks", "thank", "thx", "ty", "thankyou", "appreciated", "much",
    "cool", "ok", "okay", "k", "alright", "fine", "great", "awesome", "nice",
    "lol", "haha", "hmm", "yeah", "yes", "no", "nope", "yep", "yup", "ya",
    "bye", "goodbye", "cya", "see", "later", "take", "care", "farewell",
    "welcome", "np", "please", "pls", "kgpt", "bro", "bruh", "sir", "maam", "mam",
}
_MAX_CASUAL_WORDS = 6
_MAX_CASUAL_LEN = 45

# Conversational filler that can wrap real small-talk ("...dude", "bro ...",
# "hey man"). Stripped before matching so casual address terms don't defeat the
# greeting / identity / capability detection.
_FILLER = {"dude", "bro", "bruh", "man", "sir", "maam", "mam", "buddy", "mate",
           "boss", "yaar", "yar", "bhai", "please", "pls", "kgpt", "hey", "yo",
           "just", "actually", "hmm", "umm", "na", "re", "ok", "okay", "so"}

# Words that signal a question ABOUT the assistant itself (its identity /
# capabilities) — these never need a knowledge-base search.
_META = {"capabilities", "capability", "capable", "abilities", "ability",
         "features", "feature", "skills", "skill", "purpose"}


def _strip_filler(cleaned: str) -> str:
    return " ".join(t for t in cleaned.split() if t not in _FILLER)


def is_smalltalk(message: str) -> bool:
    """True when the message is pure chit-chat / non-educational filler and is
    NOT worth a knowledge-base search. Conservative by design."""
    cleaned = _normalise_spaces(_clean(message))
    if not cleaned:
        return True
    stripped = _normalise_spaces(_strip_filler(cleaned))
    # Exact intent phrase (incl. Telugu/Hindi pools), with or without filler
    # words → definitely small-talk.
    for variant in (cleaned, stripped):
        for phrases, _ in _INTENTS:
            if variant in phrases:
                return True
    if not stripped:                       # message was pure filler/greeting
        return True
    if len(stripped) > _MAX_CASUAL_LEN:
        return False
    tokens = stripped.split()
    if len(tokens) > _MAX_CASUAL_WORDS:
        return False
    # A question about the assistant itself ("what are your capabilities",
    # "what's your name") needs no KB search.
    if ({"you", "your", "u", "ur"} & set(tokens)) and any(t in _META for t in tokens):
        return True
    # Otherwise: small-talk only if every remaining word is casual filler.
    return all(t in _CASUAL_TOKENS for t in tokens)
