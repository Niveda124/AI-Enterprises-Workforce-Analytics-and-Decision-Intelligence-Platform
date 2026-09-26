"""
Interaction Intelligence (Prompt 10)
=======================================
Honest, transparent RULE-BASED text classification for employee-submitted
interactions (blockers, clarification requests, assistance requests).

This project has no trained/active NLP model (nlp_sentiment.py exists but
has 0 Feedback rows and always reports NOT_READY — see the Prompt 1
audit), so this module does NOT pretend to be an ML/NLP classifier. It is
transparent keyword pattern matching, labeled 'RULE-BASED TEXT ANALYSIS'
everywhere it is shown, with confidence always left as None — there is no
calibrated probability for this method, and inventing one would be
dishonest (per the prompt's explicit instruction).
"""

CATEGORY_KEYWORDS = {
    'ACCESS_PROBLEM': ['cannot access', "can't access", 'access denied', 'permission denied', 'locked out', 'login failed', 'server down'],
    'DEPENDENCY': ['waiting', 'dependency', 'blocked by', 'depends on', 'pending approval', 'approval'],
    'REQUIREMENT_UNCLEAR': ['unclear', 'confused', 'not sure', 'clarify', 'ambiguous', 'what should'],
    'TECHNICAL_PROBLEM': ['error', 'bug', 'crash', 'exception', 'not working', 'broken'],
    'DEADLINE_CONCERN': ['deadline', 'running out of time', 'need more time', 'extension', 'behind schedule'],
}

PRIORITY_KEYWORDS = [
    ('URGENT', ['urgent', 'asap', 'immediately', 'critical', 'blocking everything', 'production down']),
    ('ATTENTION', ['cannot', "can't", 'unable', 'blocked', 'help', 'stuck']),
]

LIMITATION_TEXT = "This classification is an automated interpretation and may require human review."

# Soft, non-causal impact phrasing per category — worded as "potential
# impact", never a certainty, per Part 7/19's explicit instruction.
POSSIBLE_IMPACT = {
    'ACCESS_PROBLEM': "Task execution may be delayed until access is restored.",
    'DEPENDENCY': "Progress on the related task may be delayed while the dependency is pending.",
    'REQUIREMENT_UNCLEAR': "Work may proceed in the wrong direction until the requirement is clarified.",
    'TECHNICAL_PROBLEM': "Task completion may be delayed until the technical issue is resolved.",
    'DEADLINE_CONCERN': "The related deadline may be at risk if this is not addressed.",
    'GENERAL': None,
}


def classify_interaction_text(text):
    """
    Pure, deterministic keyword matching over the submitted text. Returns
    a dict: category, priority, detected_signals (the literal matched
    phrases), confidence (always None here), source, explanation, and
    limitation.
    """
    if not text or not text.strip():
        return {
            'category': 'GENERAL', 'priority': 'NORMAL', 'detected_signals': [],
            'confidence': None, 'source': 'RULE-BASED TEXT ANALYSIS',
            'explanation': "No text was submitted to analyze.",
            'limitation': LIMITATION_TEXT,
        }

    lower = text.lower()

    # Score every category by how many of its keywords actually appear,
    # and pick the strongest match — NOT simply the first category
    # defined, which would make classification depend on arbitrary
    # dict-ordering rather than the actual evidence in the text.
    category, category_signals = 'GENERAL', []
    best_hit_count = 0
    for cat, keywords in CATEGORY_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in lower]
        if len(hits) > best_hit_count:
            category, category_signals, best_hit_count = cat, hits, len(hits)

    priority, priority_signals = 'NORMAL', []
    for level, keywords in PRIORITY_KEYWORDS:
        hits = [kw for kw in keywords if kw in lower]
        if hits:
            priority, priority_signals = level, hits
            break

    all_signals = category_signals + [s for s in priority_signals if s not in category_signals]

    if category == 'GENERAL' and not all_signals:
        explanation = "No specific keyword pattern was detected in the submitted text; classified as GENERAL by default."
    else:
        quoted = ", ".join(f'"{s}"' for s in all_signals)
        explanation = f"The submitted text contains indicator(s) such as {quoted}."

    return {
        'category': category, 'priority': priority, 'detected_signals': all_signals,
        'confidence': None, 'source': 'RULE-BASED TEXT ANALYSIS',
        'explanation': explanation, 'limitation': LIMITATION_TEXT,
    }


def possible_impact(category, has_related_task):
    """Returns a soft, non-causal 'potential impact' statement, or None if
    there's nothing meaningful to say (matches the prompt's ban on
    claiming causal certainty)."""
    if not has_related_task:
        return None
    return POSSIBLE_IMPACT.get(category)
