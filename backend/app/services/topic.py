"""Topic and Intent Classification (v8) — Multi-signal confidence scoring.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from app.services import smalltalk

@dataclass
class Classification:
    mode: str
    intent: str
    subtype: str
    confidence: float
    is_emergency: bool = False

# Sourced from smalltalk.py (single source of truth) so this classifier's
# greeting detection can never drift out of sync with what actually skips a
# KB search in chat.py — that gap ("em chesthunnav ra mawaa" running a full
# retrieval instead of getting an instant reply) was a real bug this session.
_GREETING_EXTRA = smalltalk.GREETING_SUBSTRINGS + ("good night", "good morning")

_PERSONAL = (
    "i feel", "i am feeling", "i'm feeling", "feeling low", "feeling sad",
    "i am sad", "i'm sad", "i am depressed", "i'm depressed", "depressed",
    "anxiety", "anxious", "lonely", "i hate myself", "hate my life",
    "my girlfriend", "my boyfriend", "my crush", "breakup", "break up",
    "relationship advice", "should i text", "my parents", "family problem",
    "stressed out", "panic attack", "suicidal", "self harm",
)

_MEDICAL = (
    "symptom", "fever", "headache", "migraine", "medicine", "tablet", "dosage",
    "doctor", "disease", "diagnos", "infection", "covid", "blood pressure",
    "diabetes", "prescription", "antibiotic", "vaccine", "allergy", "rash",
    "pain", "syndrome", "treatment", "therapy", "surgery", "hospital", "clinic",
    "cure", "health", "condition", "illness", "injury", "cancer", "tumor",
    "heart attack", "stroke", "blood", "medical", "crps"
)

_TECH = (
    "computer", "software", "hardware", "programming", "algorithm",
    "database", "operating system", "machine learning", "deep learning",
    "blockchain", "framework", "cybersecurity", "data structure", "compiler",
    "neural network", "cloud computing", "microcontroller",
)

_EDU = (
    "exam", "syllabus", "unit ", "subject", "assignment", "semester", "lecture",
    "notes", "question paper", "theorem", "formula", "define", "derivation",
    "viva", "lab ", "experiment", "marks", "internal", "chapter", "textbook",
    "previous year", "important questions", "model paper", "record", "practical",
    "regulation", "credits", "backlog", "supplementary",
)

_LIFESTYLE = (
    "recipe", "cook", "workout", "gym", "diet plan", "weight loss", "movie",
    "song", "music", "cricket", "football", "ipl", "travel plan", "trip",
    "fashion", "outfit", "netflix", "anime", "biryani", "restaurant",
)

# Coding intent keywords
_CODING_REGEX = re.compile(r"(\{|\}|def |class |import |Traceback|Exception|npm |pip )")

# Medical emergency keywords
_MED_EMERGENCY = re.compile(r"(chest pain|shortness of breath).*(sudden|sweating)|(sudden|sweating).*(chest pain|shortness of breath)", re.IGNORECASE)
_PAST_TENSE = re.compile(r"(yesterday|my grandfather|my grandmother|last week|last year)", re.IGNORECASE)

def classify(text: str) -> Classification:
    t = (text or "").lower()
    
    # 1. Medical emergency intercept
    if _MED_EMERGENCY.search(t) and not _PAST_TENSE.search(t):
        return Classification("medical", "health", "emergency", 1.0, is_emergency=True)

    # 2. Coding explicit detection
    if _CODING_REGEX.search(text) or "code" in t or "python" in t or "sql query" in t:
        return Classification("education", "coding", "", 1.0)
        
    # 3. Smalltalk
    if smalltalk.is_smalltalk(text) or any(g in t for g in _GREETING_EXTRA):
        return Classification("general", "greeting", "", 1.0)
        
    # 4. Score-based Auto-mode
    scores = {"education": 0.0, "medical": 0.0, "personal": 0.0, "lifestyle": 0.0, "general": 0.0}
    
    if any(k in t for k in _EDU) or any(k in t for k in _TECH):
        scores["education"] += 1.0
    if any(k in t for k in _MEDICAL):
        scores["medical"] += 1.0
    if any(k in t for k in _PERSONAL):
        scores["personal"] += 1.0
    if any(k in t for k in _LIFESTYLE):
        scores["lifestyle"] += 1.0
        
    total = sum(scores.values())
    if total == 0:
        return Classification("general", "general", "", 1.0)
        
    best_mode = max(scores, key=scores.get)
    confidence = scores[best_mode] / total
    
    if confidence >= 0.60:
        return Classification(best_mode, "general", "", confidence)
    
    return Classification("general", "general", "", confidence)

def should_use_kb(mode: str) -> bool:
    """Whether the shared knowledge base is worth searching for this mode."""
    return mode == "education"
