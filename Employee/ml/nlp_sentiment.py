"""
NLP sentiment module — Prompt 6, PATH C (NOT READY).

AUDIT FINDING (Prompt 6 audit): the Feedback table currently contains
zero records, so there is no genuine natural-language text corpus and no
genuine sentiment label of any kind (no stored sentiment field, no
rating-derived labels validated against real text) to train a supervised
model (PATH A) or to meaningfully validate a pretrained model against
(PATH B).

This module therefore implements PATH C only: it never fabricates a
sentiment prediction. `predict_sentiment` always reports that sentiment
prediction is unavailable, with the concrete reason, rather than
returning a Positive/Neutral/Negative guess from keyword rules, random
assignment, or an unvalidated pretrained model.

When genuine Feedback.feedback_text data becomes available in sufficient
quantity, this module should be revisited to implement PATH A (TF-IDF +
LogisticRegression/LinearSVC, trained/evaluated on real text) or PATH B
(a pretrained model, only after verifying it can be validated against
real data in this environment) — not before.
"""

NOT_READY_REASON = (
    "Feedback table contains zero records; no genuine sentiment dataset "
    "is currently available."
)


def predict_sentiment(text):
    """
    Report sentiment-prediction status for a piece of text.

    This function does NOT predict sentiment. There is currently no
    trained model, no pretrained model, and no genuine labelled dataset
    to justify a Positive/Neutral/Negative output. It safely accepts any
    input (None, empty string, non-string, very short text) without
    raising, and always returns a structured NOT_READY result explaining
    why no prediction is being made.

    Args:
        text: the input to (eventually) analyze. Accepted for interface
            compatibility with a future real implementation; not used to
            produce a prediction here, since no genuine model exists yet.

    Returns:
        dict with keys:
            sentiment: "NOT_READY"
            status:    "NLP_SENTIMENT_NOT_READY"
            model:     "NOT_READY"
            reason:    explanation of why prediction is unavailable
    """
    # Input is intentionally not inspected for content (no keyword rules,
    # no heuristics). Any input — None, "", whitespace, a non-string
    # object, or normal text — receives the same honest NOT_READY result,
    # since no genuine model exists to apply to it regardless of what it
    # contains.
    return {
        "sentiment": "NOT_READY",
        "status": "NLP_SENTIMENT_NOT_READY",
        "model": "NOT_READY",
        "reason": NOT_READY_REASON,
    }
