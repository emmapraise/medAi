"""Rule-based safety gate that runs BEFORE retrieval and the LLM: fixed replies, zero cost, deterministic.

check(text) -> (kind, reply) | None, kind in: self_harm | emergency | personal_advice | injection.
Emergency/self-harm rules are deliberately biased toward firing: a crisis reply to an informational question is
a small annoyance, a missed emergency is not. They are first-person / present-tense so "what are the symptoms
of a stroke?" still reaches the normal answer path.
shortcut: English-only regexes, upgrade to a multilingual classifier if non-English users appear.
"""
import re

DISCLAIMER = "MediQA shares general health information from NIH sources. It is not medical advice, diagnosis or treatment."

_WHO = r"(?:i|i'm|i am|i've|we|he|she|they|my \w+|our \w+|someone|somebody|a (?:person|friend)|the (?:patient|baby|child))"

PATTERNS = {
    "self_harm": [
        r"\b(?:kill(?:ing)? myself|end(?:ing)? my (?:own )?life|ending it all|take my own life|want to die|wanna die|suicid(?:e|al)|hurt myself|harm myself|end it all)\b",
        r"\b(?:took|taken|swallowed|ingested)\b.{0,40}\bon purpose\b",
    ],
    "emergency": [
        rf"\b{_WHO}\b.{{0,25}}\b(?:can'?t|cannot|unable to) breathe\b|\bnot breathing\b|\bstopped breathing\b|\blips? (?:are |is )?(?:turning |going )?blue\b",
        r"\bchest (?:pain|pressure|tightness)\b.{0,60}\b(?:arm|jaw|crushing|sweat\w*|spreading|radiat\w*)\b|\bcrushing chest\b",
        r"\bface\b.{0,20}\b(?:droop\w*|sagging)\b|\bslurred speech\b|\b(?:can'?t|cannot) (?:speak|talk)\b.{0,20}\b(?:clearly|properly)\b",
        rf"\b{_WHO}\b.{{0,15}}\b(?:having|had) a seizure\b|\bseizure\b.{{0,25}}\bwon'?t stop\b",
        r"\bbleeding\b.{0,30}\b(?:heavily|won'?t stop|can'?t stop|a lot)\b|\b(?:won'?t|can'?t|cannot) stop bleeding\b",
        r"\b(?:took|taken|swallowed|ingested|drank)\b.{0,30}\b(?:too much|too many|a bottle|the bottle|whole bottle|an overdose)\b",
        rf"\b{_WHO}\b.{{0,15}}\boverdos(?:ed|ing)\b",
        r"\b(?:unconscious|unresponsive|passed out and)\b|\bthroat\b.{0,15}\b(?:closing|swelling)\b|\banaphyla\w+\b.{0,20}\b(?:now|happening)\b",
    ],
    "personal_advice": [
        r"\b(?:write|give|get) me (?:a |an )?prescription\b|\bprescribe (?:me|for me)\b",
        r"\bdiagnose (?:me|my)\b|\bwhat (?:do|disease do) i have\b",
        r"\b(?:exact |right |correct )?dos(?:e|age)\b.{0,40}\b(?:for me|for my|my \w+|should i|can i)\b|\bhow (?:much|many)\b.{0,40}\b(?:should|can) i (?:give|take)\b",
        r"\bshould i (?:stop|quit|skip|change|increase|reduce|double)\b.{0,40}\b(?:taking|medic\w+|pills?|meds?|tablets?|insulin)\b",
        r"\breplace my (?:doctor|physician|gp)\b",
        r"\b(?:is it |am i )?(?:safe|ok|okay)\b.{0,15}\bfor me\b.{0,20}\b(?:mix|combine|take)\b|\b(?:mix|combine)\b.{0,30}\bwith my\b",
    ],
    "injection": [
        r"\bignore (?:all |any |your |the |previous |prior |above )*(?:instructions?|rules?|prompts?)\b|\b(?:system|developer) prompt\b|\breveal your (?:instructions|prompt|rules)\b|\byou are now\b|\bpretend (?:to be|you are)\b",
    ],
}
_RE = {k: [re.compile(p, re.I) for p in v] for k, v in PATTERNS.items()}

REPLIES = {
    "emergency": ("This sounds like it could be an emergency. Please call your local emergency number now "
                  "(for example 911 in the US, 112 in the EU or Nigeria, 999 in the UK) or go to the nearest emergency room. "
                  "If you can, stay with the person and do not wait for more information from me."),
    "self_harm": ("I'm really sorry you're going through this, and I'm glad you said it. You deserve support right now. "
                  "If you might act on these thoughts or are in danger, call your local emergency number now "
                  "(911 in the US, 112 in the EU or Nigeria, 999 in the UK). In the US you can call or text 988 at any hour; "
                  "elsewhere, findahelpline.com lists free crisis lines by country. Please don't be alone: reach out to someone you trust."),
    "personal_advice": ("I can share general health information, but I can't give personal medical advice: I can't diagnose you, "
                        "prescribe, set a dose, or tell you to start, stop or mix medicines. Please ask your doctor or pharmacist. "
                        "If you'd like, ask me about the condition or medicine in general terms."),
    "injection": "I can only answer health questions using NIH medical sources, and I can't change that. What would you like to know?",
}


def check(text: str) -> tuple[str, str] | None:
    for kind in ("self_harm", "emergency", "injection", "personal_advice"):  # most urgent first
        if any(r.search(text) for r in _RE[kind]):
            return kind, REPLIES[kind]
    return None
