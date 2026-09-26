import os
import json
import joblib
import pandas as pd

from Employee.models import ModelVersion, Prediction
from .feature_engineering import (
    build_project_features,
    build_employee_risk_features,
    build_employee_performance_features,
)

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'saved_models')


def load_model(model_name):
    """
    Loads the persisted artifact for the active ModelVersion. Returns
    (pipeline, feature_columns, model_version_obj) or (None, None, None)
    if no active, on-disk model exists. Never retrains here.
    """
    mv = ModelVersion.objects.filter(model_name=model_name, is_active=True).first()
    if not mv or not mv.model_file_path or not os.path.exists(mv.model_file_path):
        return None, None, None
    artifact = joblib.load(mv.model_file_path)
    return artifact['model'], artifact['feature_columns'], mv


def get_model_metadata(model_name):
    mv = ModelVersion.objects.filter(model_name=model_name, is_active=True).first()
    if not mv:
        return None
    return {
        'model_name': mv.model_name,
        'version': mv.version,
        'algorithm': mv.algorithm,
        'training_date': mv.training_date,
        'metrics': json.loads(mv.metrics) if mv.metrics else None,
    }


def prepare_features(raw_features, feature_columns):
    """Aligns a raw feature dict to the exact column order the pipeline was fit on."""
    return pd.DataFrame([raw_features])[feature_columns]


def predict_project_outcome(project, save=True, force=False):
    """
    Loads the persisted Pipeline (preprocessing + tuned classifier) and runs
    real inference on this project's current features. No retraining here.
    """
    pipeline, feature_columns, mv = load_model('project_outcome')
    if pipeline is None:
        return {'status': 'unavailable', 'message': "Insufficient historical data for reliable ML prediction."}

    features = build_project_features(project)

    if not force and save:
        existing = Prediction.objects.filter(
            project=project, prediction_type='PROJECT_OUTCOME'
        ).order_by('-prediction_date').first()
        if existing and existing.input_reference == str(features):
            prob_dict = json.loads(existing.probabilities) if existing.probabilities else None
            explanation = json.loads(existing.explanation) if existing.explanation else None
            return {
                'status': 'ok', 'reused': True,
                'predicted_outcome': existing.predicted_outcome,
                'confidence': existing.confidence, 'risk_level': existing.risk_level,
                'probabilities': prob_dict, 'explanation': explanation,
                'prediction_date': existing.prediction_date, 'model_version': existing.model_version,
            }

    X = prepare_features(features, feature_columns)
    prediction = pipeline.predict(X)[0]
    proba = pipeline.predict_proba(X)[0]
    class_labels = list(pipeline.named_steps['clf'].classes_)
    prob_dict = {label: round(float(p), 3) for label, p in zip(class_labels, proba)}
    confidence = round(max(proba), 3)

    risk_level = "High" if prediction == "Failure Risk" else "Low"

    explanation = None
    clf = pipeline.named_steps['clf']
    if hasattr(clf, 'feature_importances_'):
        importances = sorted(zip(feature_columns, clf.feature_importances_), key=lambda x: x[1], reverse=True)[:5]
        explanation = [{'feature': f, 'importance': round(float(v), 3), 'value': features.get(f)} for f, v in importances]

    result = {
        'status': 'ok', 'reused': False,
        'predicted_outcome': prediction, 'confidence': confidence, 'risk_level': risk_level,
        'probabilities': prob_dict, 'explanation': explanation,
        'model_version': f"{mv.model_name} {mv.version}",
    }

    if save:
        pred_obj = Prediction.objects.create(
            prediction_type='PROJECT_OUTCOME', project=project,
            predicted_outcome=prediction, confidence=confidence, risk_level=risk_level,
            model_version=result['model_version'], input_reference=str(features),
            probabilities=json.dumps(prob_dict),
            explanation=json.dumps(explanation) if explanation else None,
        )
        result['prediction_date'] = pred_obj.prediction_date

    return result


def predict_employee_risk(employee, save=True, force=False):
    pipeline, feature_columns, mv = load_model('employee_risk')
    if pipeline is None:
        return {'status': 'unavailable', 'message': "Insufficient historical data for reliable ML prediction."}

    features = build_employee_risk_features(employee)
    if features is None:
        return {'status': 'unavailable', 'message': "No performance/workload history recorded for this employee yet."}

    if not force and save:
        existing = Prediction.objects.filter(
            employee=employee, prediction_type='EMPLOYEE_RISK'
        ).order_by('-prediction_date').first()
        if existing and existing.input_reference == str(features):
            prob_dict = json.loads(existing.probabilities) if existing.probabilities else None
            explanation = json.loads(existing.explanation) if existing.explanation else None
            return {
                'status': 'ok', 'reused': True,
                'predicted_outcome': existing.predicted_outcome,
                'confidence': existing.confidence, 'risk_level': existing.risk_level,
                'probabilities': prob_dict, 'explanation': explanation,
                'prediction_date': existing.prediction_date, 'model_version': existing.model_version,
            }

    X = prepare_features(features, feature_columns)
    prediction = pipeline.predict(X)[0]
    proba = pipeline.predict_proba(X)[0]
    class_labels = list(pipeline.named_steps['clf'].classes_)
    prob_dict = {label: round(float(p), 3) for label, p in zip(class_labels, proba)}
    confidence = round(max(proba), 3)

    explanation = None
    clf = pipeline.named_steps['clf']
    if hasattr(clf, 'feature_importances_'):
        importances = sorted(zip(feature_columns, clf.feature_importances_), key=lambda x: x[1], reverse=True)[:5]
        explanation = [{'feature': f, 'importance': round(float(v), 3), 'value': features.get(f)} for f, v in importances]

    result = {
        'status': 'ok', 'reused': False,
        'predicted_outcome': prediction, 'confidence': confidence, 'risk_level': prediction,
        'probabilities': prob_dict, 'explanation': explanation,
        'model_version': f"{mv.model_name} {mv.version}",
    }

    if save:
        pred_obj = Prediction.objects.create(
            prediction_type='EMPLOYEE_RISK', employee=employee,
            predicted_outcome=prediction, confidence=confidence, risk_level=prediction,
            model_version=result['model_version'], input_reference=str(features),
            probabilities=json.dumps(prob_dict),
            explanation=json.dumps(explanation) if explanation else None,
        )
        result['prediction_date'] = pred_obj.prediction_date

    return result


def predict_employee_performance(employee, save=True):
    """
    Predicts NEXT-period performance bucket from the employee's most recent
    recorded period's features, using the leakage-corrected
    employee_performance model. Loads the persisted model only — never
    retrains here. Fails safely (status='unavailable') if the model is
    MODEL_NOT_READY / not yet trained.

    PREDICTION-SERVICE CONSISTENCY FIX (Prompt 8 audit): this previously
    loaded the registry under the key 'employee_future_performance', which
    never matched the actual registered/trained name 'employee_performance'
    (see train_models.py), so this function could never serve a prediction
    even once the model passed its quality gate. It also previously saved
    Prediction.prediction_type='EMPLOYEE_FUTURE_PERFORMANCE', which is not
    in Prediction.TYPE_CHOICES and does not match what views.py queries for
    ('EMPLOYEE_PERFORMANCE'). Both are corrected below. The feature dict is
    now built via the shared build_employee_performance_features() from
    feature_engineering.py instead of being duplicated inline, so training
    and prediction can never silently drift apart.
    """
    from Employee.models import PerformanceHistory
    pipeline, feature_columns, mv = load_model('employee_performance')
    if pipeline is None:
        return {'status': 'unavailable', 'message': "Insufficient historical data for reliable ML prediction."}

    latest = PerformanceHistory.objects.filter(employee=employee).order_by('-period').first()
    if not latest:
        return {'status': 'unavailable', 'message': "No performance history recorded for this employee yet."}

    features = build_employee_performance_features(latest)
    X = prepare_features(features, feature_columns)
    prediction = pipeline.predict(X)[0]
    proba = pipeline.predict_proba(X)[0]
    class_labels = list(pipeline.named_steps['clf'].classes_)
    prob_dict = {label: round(float(p), 3) for label, p in zip(class_labels, proba)}
    confidence = round(max(proba), 3)

    explanation = None
    clf = pipeline.named_steps['clf']
    if hasattr(clf, 'feature_importances_'):
        importances = sorted(zip(feature_columns, clf.feature_importances_), key=lambda x: x[1], reverse=True)[:5]
        explanation = [{'feature': f, 'importance': round(float(v), 3), 'value': features.get(f)} for f, v in importances]

    result = {
        'status': 'ok', 'predicted_outcome': prediction, 'confidence': confidence,
        'probabilities': prob_dict, 'explanation': explanation,
        'model_version': f"{mv.model_name} {mv.version}",
    }

    if save:
        pred_obj = Prediction.objects.create(
            prediction_type='EMPLOYEE_PERFORMANCE', employee=employee,
            predicted_outcome=prediction, confidence=confidence,
            model_version=result['model_version'], input_reference=str(features),
            probabilities=json.dumps(prob_dict),
            explanation=json.dumps(explanation) if explanation else None,
        )
        result['prediction_date'] = pred_obj.prediction_date

    return result


def _build_current_workload_forecast_features(employee):
    """
    Builds the feature row for predicting an employee's NEXT-period
    workload_score, using exactly the same field names and current/prev
    convention as the training-side dataset builder
    (Employee/ml/datasets.py: build_workload_forecast_dataset()).

    'current' = the employee's most recent recorded WorkloadHistory period
    (the training loop's period t for the last usable i). 'prev' = the
    period immediately before it (period t-1), or None if only one period
    exists — in which case prev_* falls back to current's own values,
    identically to the i==0 case in build_workload_forecast_dataset(). If
    that training-side dataset builder's field set ever changes, this
    function must be updated to match, since prediction reuses the exact
    same feature_columns list persisted alongside the trained model.

    Returns (features_dict, latest_period) or (None, None) if the employee
    has no recorded WorkloadHistory at all.
    """
    from Employee.models import WorkloadHistory

    history = list(WorkloadHistory.objects.filter(employee=employee).order_by('-period')[:2])
    if not history:
        return None, None

    current = history[0]
    prev = history[1] if len(history) > 1 else None

    features = {
        'assigned_count': current.assigned_count,
        'completed_count': current.completed_count,
        'pending_count': current.pending_count,
        'overdue_count': current.overdue_count,
        'workload_score': current.workload_score,
        'prev_workload_score': prev.workload_score if prev else current.workload_score,
        'prev_assigned_count': prev.assigned_count if prev else current.assigned_count,
    }
    return features, current.period


def predict_workload_forecast(employee, save=True):
    """
    Predicts the employee's NEXT-period workload_score using the active
    'workload_forecast' regression model. Loads the persisted model only —
    never retrains here. Uses the exact feature_columns list persisted
    alongside the trained pipeline (via prepare_features), so column order
    always matches training regardless of this dict's construction order.

    Fails safely (status='unavailable') and predicts nothing if:
      - no active 'workload_forecast' ModelVersion exists (e.g. it is
        currently MODEL_NOT_READY — load_model() only ever loads
        is_active=True rows, so a rejected model is never silently used), or
      - the employee has no recorded WorkloadHistory yet.
    """
    pipeline, feature_columns, mv = load_model('workload_forecast')
    if pipeline is None:
        return {'status': 'unavailable', 'message': "Insufficient historical data for reliable ML prediction."}

    features, latest_period = _build_current_workload_forecast_features(employee)
    if features is None:
        return {'status': 'unavailable', 'message': "No workload history recorded for this employee yet."}

    X = prepare_features(features, feature_columns)
    predicted_score = float(pipeline.predict(X)[0])

    explanation = None
    reg = pipeline.named_steps['reg']
    if hasattr(reg, 'feature_importances_'):
        importances = sorted(zip(feature_columns, reg.feature_importances_), key=lambda x: x[1], reverse=True)[:5]
        explanation = [{'feature': f, 'importance': round(float(v), 3), 'value': features.get(f)} for f, v in importances]

    result = {
        'status': 'ok',
        'predicted_workload_score': round(predicted_score, 2),
        'based_on_period': str(latest_period) if latest_period else None,
        'explanation': explanation,
        'model_version': f"{mv.model_name} {mv.version}",
    }

    if save:
        pred_obj = Prediction.objects.create(
            prediction_type='WORKLOAD_FORECAST', employee=employee,
            predicted_outcome=str(result['predicted_workload_score']),
            model_version=result['model_version'], input_reference=str(features),
            explanation=json.dumps(explanation) if explanation else None,
        )
        result['prediction_date'] = pred_obj.prediction_date

    return result


def whatif_project_outcome(project, override_features):
    """Hypothetical scenario — reuses the persisted model, never a manual formula."""
    pipeline, feature_columns, mv = load_model('project_outcome')
    if pipeline is None:
        return {'status': 'unavailable', 'message': "Insufficient historical data for reliable ML prediction."}

    base_features = build_project_features(project)
    base_features.update(override_features)

    X = prepare_features(base_features, feature_columns)
    prediction = pipeline.predict(X)[0]
    proba = pipeline.predict_proba(X)[0]
    class_labels = list(pipeline.named_steps['clf'].classes_)
    prob_dict = {label: round(float(p), 3) for label, p in zip(class_labels, proba)}

    return {
        'status': 'ok',
        'scenario_label': "Hypothetical scenario — not a new trained prediction.",
        'predicted_outcome': prediction,
        'probabilities': prob_dict,
        'used_features': base_features,
    }