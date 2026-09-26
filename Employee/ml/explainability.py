"""
Explainability (Prompt 4)
===========================
Turns data ALREADY stored on a Prediction row into a human-readable
explanation. Does NOT recompute, guess, or invent feature importances or
percentages — those already exist, verbatim, as `Prediction.explanation`,
saved at prediction time directly from the trained sklearn model's own
`feature_importances_` attribute (see prediction_service.py). This module
only reads and narrates what the model already produced, plus compares
the two most recent REAL stored predictions for the same entity to
describe genuine changes over time.
"""
import ast
import json

from Employee.models import Prediction


def _parse_input_reference(raw):
    """input_reference is stored as str(dict) by prediction_service.py —
    not JSON. Parsed defensively; returns None rather than guessing if it
    doesn't parse cleanly."""
    if not raw:
        return None
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None


def _explain_trend(pred):
    """
    Compares this prediction to the PREVIOUS stored prediction of the same
    type for the same entity. Reports only a real, computed delta between
    two actual saved snapshots — if there's no earlier prediction, says so
    plainly instead of inventing a trend.
    """
    entity_filter = {'employee': pred.employee} if pred.employee_id else {'project': pred.project}
    previous = (
        Prediction.objects.filter(prediction_type=pred.prediction_type, **entity_filter)
        .exclude(id=pred.id)
        .filter(prediction_date__lt=pred.prediction_date)
        .order_by('-prediction_date')
        .first()
    )
    if not previous:
        return {'available': False, 'reason': 'no_earlier_prediction_for_this_entity'}

    result = {
        'available': True,
        'previous_prediction_date': previous.prediction_date,
        'previous_outcome': previous.predicted_outcome,
        'previous_risk_level': previous.risk_level,
        'outcome_changed': previous.predicted_outcome != pred.predicted_outcome,
        'risk_level_changed': previous.risk_level != pred.risk_level,
    }

    prev_features = _parse_input_reference(previous.input_reference)
    curr_features = _parse_input_reference(pred.input_reference)
    if prev_features and curr_features:
        deltas = {}
        for key, curr_val in curr_features.items():
            prev_val = prev_features.get(key)
            if isinstance(curr_val, (int, float)) and isinstance(prev_val, (int, float)):
                delta = round(curr_val - prev_val, 3)
                if delta != 0:
                    deltas[key] = {'previous': prev_val, 'current': curr_val, 'delta': delta}
        result['feature_deltas'] = deltas
    else:
        result['feature_deltas'] = None

    return result


def explain_prediction(prediction_id):
    """Human-readable explanation for ONE stored Prediction, built entirely
    from real values already on that row plus the previous stored
    prediction for the same entity."""
    try:
        pred = Prediction.objects.get(id=prediction_id)
    except Prediction.DoesNotExist:
        return {'error': 'prediction_not_found', 'prediction_id': prediction_id}

    factors = json.loads(pred.explanation) if pred.explanation else None
    probabilities = json.loads(pred.probabilities) if pred.probabilities else None

    if not factors:
        return {
            'prediction_id': pred.id,
            'available': False,
            'reason': 'No feature-importance data was stored for this prediction '
                      '(the underlying model does not expose feature_importances_, '
                      'or none was saved at prediction time).',
        }

    factor_sentences = [
        f"{f['feature']} (importance {f['importance']}, current value {f['value']})"
        for f in factors
    ]
    confidence_clause = f" with {pred.confidence} confidence" if pred.confidence is not None else ""
    summary = (
        f"Predicted '{pred.predicted_outcome}'{confidence_clause} ({pred.model_version}). "
        f"Top contributing factors, in order of the trained model's own feature importance: "
        + "; ".join(factor_sentences) + "."
    )

    return {
        'prediction_id': pred.id,
        'available': True,
        'predicted_outcome': pred.predicted_outcome,
        'confidence': pred.confidence,
        'risk_level': pred.risk_level,
        'probabilities': probabilities,
        'top_factors': factors,
        'summary': summary,
        'trend': _explain_trend(pred),
        'model_version': pred.model_version,
        'prediction_date': pred.prediction_date,
    }


def explain_latest_for_employee(employee_id, prediction_type='EMPLOYEE_RISK'):
    pred = Prediction.objects.filter(
        employee_id=employee_id, prediction_type=prediction_type
    ).order_by('-prediction_date').first()
    if not pred:
        return {'available': False, 'reason': 'no_prediction_found'}
    return explain_prediction(pred.id)


def explain_latest_for_project(project_id, prediction_type='PROJECT_OUTCOME'):
    pred = Prediction.objects.filter(
        project_id=project_id, prediction_type=prediction_type
    ).order_by('-prediction_date').first()
    if not pred:
        return {'available': False, 'reason': 'no_prediction_found'}
    return explain_prediction(pred.id)
