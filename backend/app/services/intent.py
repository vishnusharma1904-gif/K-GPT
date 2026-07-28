"""Lightweight intent → category routing (keyword-first, like TRON-X).

Picks the cheapest category that fits, without an extra LLM call in the common
case. Vision / long_context are set by the chat layer (image present, big doc),
not here.
"""
from __future__ import annotations

_CODING = ("code", "bug", "function", "python", "java", "c++", "error", "compile",
           "algorithm", "leetcode", "debug", "regex", "sql query", "segmentation fault",
           "syntax", "stack trace", "npm", "pip install")
_REASON = ("prove", "derive", "explain why", "step by step", "math", "theorem",
           "calculate", "reason", "logic", "integral", "derivative", "probability",
           "differential", "matrix", "optimi")
# Definitional / knowledge questions. These need a CAPABLE model — the tiny 8B
# fabricates definitions and abbreviations (e.g. answering "what is RAG?" with a
# made-up "Robotics Assembly and Gear"), so we route them to the reasoning tier.
_KNOWLEDGE = ("what is", "what's", "whats ", "what are", "what does", "define ",
              "definition", "meaning of", "full form", "stands for", "abbreviation",
              "acronym", "difference between", "compare ", "explain ", "how does",
              "why is", "what do you mean")

# Romanised-Telugu ("Tenglish") markers — common function words students mix in.
_TENGLISH = ("ela", "enti", "em ", "cheyy", "cheyi", "kavali", "ledu", "unna",
             "unnava", "bagunnava", "nuvvu", "nenu", "chestunna", "cheppu",
             "kani", "kuda", "ledhu", "avunu", "ostha", "telusu", "ardham")


# Greetings / acknowledgements / chit-chat → route to the cheapest model.
_SMALLTALK_PHRASES = ("how are you", "how r u", "hows it going", "how's it going",
                      "whats up", "what's up", "wassup", "good morning", "good afternoon",
                      "good evening", "good night", "nice to meet", "who are you",
                      "what can you do", "thank you", "thanks a lot")
_FILLER_WORDS = {
    "hi", "hii", "hiii", "hello", "helloo", "hey", "heyy", "yo", "hiya", "heya",
    "sup", "hola", "namaste", "greetings", "dude", "bro", "bruh", "man", "buddy",
    "there", "u", "you", "ur", "r", "how", "are", "is", "it", "going", "wassup",
    "thanks", "thank", "thankyou", "thx", "ty", "tysm", "ok", "okay", "okk", "kk",
    "cool", "nice", "great", "awesome", "lol", "lmao", "haha", "hehe", "hmm", "hmmm",
    "bye", "goodbye", "gn", "gm", "good", "morning", "afternoon", "evening", "night",
    "and", "the", "a", "please", "pls", "ya", "yeah", "yep", "nope", "no", "yes",
}


def _is_small_talk(text: str) -> bool:
    import re
    t = re.sub(r"[^a-z\s]", " ", text.lower()).strip()
    if not t:
        return False  # no Latin words (e.g. Telugu script) — not small talk
    if any(ph in text.lower() for ph in _SMALLTALK_PHRASES):
        return True
    words = t.split()
    # short and made up entirely of greeting/filler tokens
    return len(words) <= 6 and all(w in _FILLER_WORDS for w in words)


def _has_telugu_script(text: str) -> bool:
    return any("ఀ" <= ch <= "౿" for ch in text)


def _is_tenglish(text: str) -> bool:
    t = f" {text.lower()} "
    return sum(1 for w in _TENGLISH if w in t) >= 2


def classify(text: str) -> str:
    if _has_telugu_script(text) or _is_tenglish(text):
        return "multilingual"
    if _is_small_talk(text):
        return "instant"   # cheap 8B model for greetings / chit-chat
    t = text.lower()
    if any(k in t for k in _CODING):
        return "coding"
    if any(k in t for k in _REASON):
        return "reasoning"
    if any(k in t for k in _KNOWLEDGE):
        return "reasoning"   # definitions/abbreviations → capable model, not the 8B
    return "fast_chat"
