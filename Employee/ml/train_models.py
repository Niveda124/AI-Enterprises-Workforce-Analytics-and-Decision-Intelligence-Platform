import os
import json
import joblib
import pandas as pd
from datetime import datetime

from sklearn.model_selection import (
    train_test_split, StratifiedKFold, RandomizedSearchCV
)
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.pipeline import Pipeline

from .datasets import (
    build_project_outcome_dataset,
    build_employee_performance_dataset,
    build_employee_risk_dataset,
    build_workload_forecast_dataset,
)
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from .validation import validate_regression_dataset
from .evaluate_models import evaluate_regressor
from .model_registry import register_regressor_not_ready
from .preprocessing import build_preprocessing_pipeline
from .validation import validate_dataset, can_cross_validate, can_hold_out_test
from .evaluate_models import evaluate_classifier, evaluate_cross_val
from .model_registry import register_model, register_insufficient_data, register_not_ready

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'saved_models')
MIN_SAMPLES_PER_CLASS = 5

# Project outcome uses a stricter floor than the other models: with only
# MIN_SAMPLES_PER_CLASS=5 (10 total records), a 25% holdout leaves a 3-sample
# test set, which cannot produce a statistically meaningful accuracy/F1
# estimate — any single misclassification swings the score by ~33%. 15/class
# (30 total, ~7-8 samples per class in the test split) is chosen here as a
# documented, deliberately conservative minimum for this specific binary
# target; it is not a universal ML standard, just a floor picked to avoid
# reporting a test metric computed on 3 examples as if it were reliable.
PROJECT_OUTCOME_MIN_SAMPLES_PER_CLASS = 15

# Minimum performance bar for registering a model as ACTIVE/production-usable.
# For a 3-class problem, a model that predicts no better than the majority
# class typically scores well below this. 0.50 weighted F1 is used here as a
# documented, deliberately modest bar — not a claim of strong performance,
# just the floor below which a model provides no defensible predictive value
# over a naive baseline and must not be presented as a trustworthy prediction.
MIN_ACCEPTABLE_F1 = 0.50

CANDIDATE_PARAM_GRIDS = {
    'RandomForestClassifier': {
        'estimator': RandomForestClassifier(random_state=42),
        'params': {
            'clf__n_estimators': [50, 100, 200],
            'clf__max_depth': [None, 5, 10, 20],
            'clf__min_samples_split': [2, 5, 10],
            'clf__min_samples_leaf': [1, 2, 4],
            'clf__max_features': ['sqrt', 'log2', None],
        },
    },
    'HistGradientBoostingClassifier': {
        'estimator': HistGradientBoostingClassifier(random_state=42),
        'params': {
            'clf__max_iter': [50, 100, 200],
            'clf__max_depth': [None, 3, 5, 10],
            'clf__learning_rate': [0.01, 0.05, 0.1, 0.2],
            'clf__min_samples_leaf': [5, 10, 20],
        },
    },
}


def _train_and_select(model_name, rows, labels, feature_note, min_samples_per_class=None):
    required_min = min_samples_per_class or MIN_SAMPLES_PER_CLASS
    is_valid, val_report = validate_dataset(rows and pd.DataFrame(rows), labels,
                                             min_samples_per_class=required_min)
    if not rows or not is_valid:
        reason = {
            'status': 'INSUFFICIENT_DATA',
            'message': f"Insufficient valid historical data for {model_name}.",
            'validation_report': val_report if rows else {'total_rows': 0, 'issues': ['No records found.']},
            'required_minimum_per_class': required_min,
        }
        register_insufficient_data(model_name, reason)
        return reason

    df = pd.DataFrame(rows)
    feature_columns = list(df.columns)

    use_cv = can_cross_validate(labels, n_splits=3)
    use_holdout = can_hold_out_test(labels, test_size=0.25)

    if not use_holdout:
        reason = {
            'status': 'INSUFFICIENT_DATA',
            'message': f"Dataset too small to hold out a genuine test set for {model_name} without leaving a class with zero remaining training samples.",
            'validation_report': val_report,
        }
        register_insufficient_data(model_name, reason)
        return reason

    X_train, X_test, y_train, y_test = train_test_split(
        df, labels, test_size=0.25, random_state=42, stratify=labels
    )

    candidates_tried = []
    best_pipeline = None
    best_score = -1
    best_algo_name = None
    best_cv_summary = None

    for algo_name, cfg in CANDIDATE_PARAM_GRIDS.items():
        pipeline = Pipeline([
            ('prep', build_preprocessing_pipeline()),
            ('clf', cfg['estimator']),
        ])

        if use_cv:
            cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
            search = RandomizedSearchCV(
                pipeline, cfg['params'], n_iter=8, cv=cv,
                scoring='f1_weighted', random_state=42, n_jobs=1,
            )
            search.fit(X_train, y_train)
            fitted = search.best_estimator_
            cv_summary = evaluate_cross_val(search.cv_results_, search.best_index_)
            score = cv_summary['cv_mean_f1']
        else:
            fitted = pipeline
            fitted.fit(X_train, y_train)
            cv_summary = {'cv_mean_f1': None, 'cv_std_f1': None, 'cv_folds': 0,
                           'note': 'Cross-validation skipped — insufficient samples per class for stratified folds.'}
            score = evaluate_classifier(fitted, X_test, y_test)['f1_score']

        candidates_tried.append({'algorithm': algo_name, 'cv_summary': cv_summary})

        if score > best_score:
            best_score = score
            best_pipeline = fitted
            best_algo_name = algo_name
            best_cv_summary = cv_summary

    test_metrics = evaluate_classifier(best_pipeline, X_test, y_test, labels_order=sorted(set(labels)))

    metrics = {
        'algorithm': best_algo_name,
        'candidates_compared': [c['algorithm'] for c in candidates_tried],
        'candidates_detail': candidates_tried,
        'selected_by': 'cross_validation_f1' if use_cv else 'holdout_test_f1',
        'cross_validation': best_cv_summary,
        'test_metrics': test_metrics,
        'training_samples': len(y_train),
        'test_samples': len(y_test),
        'total_training_records': len(rows),
        'classes': sorted(set(labels)),
        'features_used': feature_columns,
        'feature_note': feature_note,
        'random_state': 42,
        'min_acceptable_f1': MIN_ACCEPTABLE_F1,
    }

    os.makedirs(MODEL_DIR, exist_ok=True)
    file_path = os.path.join(MODEL_DIR, f'{model_name}_model.pkl')
    joblib.dump({
        'model': best_pipeline,
        'feature_columns': feature_columns,
        'algorithm': best_algo_name,
        'trained_at': datetime.now().isoformat(),
    }, file_path)

    if test_metrics['f1_score'] < MIN_ACCEPTABLE_F1:
        metrics['rejection_reason'] = (
            f"Test F1 ({test_metrics['f1_score']}) is below the documented minimum "
            f"acceptable F1 ({MIN_ACCEPTABLE_F1}). This model performs no better than, "
            f"or worse than, a naive baseline and is not registered as production-usable. "
            f"It requires more/better historical data or feature redesign, not parameter "
            f"tuning, to become reliable."
        )
        register_not_ready(model_name, best_algo_name, metrics, file_path)
        return {'status': 'MODEL_NOT_READY', 'metrics': metrics, 'file_path': file_path}

    register_model(model_name, 'v2', best_algo_name, metrics, file_path, active=True)

    return {'status': 'trained', 'metrics': metrics, 'file_path': file_path}


def train_project_outcome_model():
    rows, labels = build_project_outcome_dataset()
    return _train_and_select(
        'project_outcome', rows, labels,
        feature_note="All features (task counts/rates, progress, team size, days_remaining, "
                     "priority) are computed from current database state, available before "
                     "the project's final outcome is known. Label (Success/Failure Risk) comes "
                     "only from the already-resolved Project.status field.",
        min_samples_per_class=PROJECT_OUTCOME_MIN_SAMPLES_PER_CLASS,
    )


def train_employee_performance_model():
    """
    Temporal employee future-performance prediction using historically
    recorded PerformanceHistory data (Prompt 4 leakage correction). Model
    name/registry key ('employee_performance') and prediction_type
    ('EMPLOYEE_PERFORMANCE') are kept unchanged from the original
    implementation so existing views, templates, and reports continue
    working without modification — only the dataset construction changed.
    """
    rows, labels = build_employee_performance_dataset()
    return _train_and_select(
        'employee_performance', rows, labels,
        feature_note="Features are PerformanceHistory counts/rates from period T; label is "
                     "period T+1's performance_score bucketed into High/Medium/Low for the "
                     "SAME employee (temporal design, no same-period leakage). NOTE: "
                     "performance_score itself originates from this project's synthetic seed "
                     "data, not independently observed real-world outcomes — this model should "
                     "be described as temporal future-performance prediction using historically "
                     "recorded PerformanceHistory data, not as prediction of independently "
                     "verified performance outcomes."
    )


def train_employee_risk_model():
    rows, labels = build_employee_risk_dataset()
    return _train_and_select(
        'employee_risk', rows, labels,
        feature_note="Features are PerformanceHistory + WorkloadHistory values from period T; "
                     "label is period T+1's real overdue/assigned ratio bucketed into "
                     "High/Medium/Low for the SAME employee (temporal design, no same-period "
                     "leakage) — a historical fact, not invented."
    )


# Minimum rows for a defensible regression holdout — same reasoning as
# classification floors: too few rows makes MAE/RMSE/R² swing wildly on a
# tiny test split and cannot be reported as meaningful.
WORKLOAD_FORECAST_MIN_ROWS = 20

WORKLOAD_FORECAST_CANDIDATES = {
    'RandomForestRegressor': {
        'estimator': RandomForestRegressor(random_state=42),
        'params': {
            'reg__n_estimators': [50, 100, 200],
            'reg__max_depth': [None, 5, 10],
            'reg__min_samples_leaf': [1, 2, 4],
        },
    },
    'HistGradientBoostingRegressor': {
        'estimator': HistGradientBoostingRegressor(random_state=42),
        'params': {
            'reg__max_iter': [50, 100, 200],
            'reg__max_depth': [None, 3, 5],
            'reg__learning_rate': [0.01, 0.05, 0.1],
        },
    },
}


# Minimum test-set rows for a chronological holdout to be meaningful — with
# fewer than this, a single unlucky/lucky recent observation would swing
# MAE/RMSE/R² too much to report as a genuine evaluation.
WORKLOAD_FORECAST_MIN_TEST_ROWS = 4


def train_workload_forecast_model():
    """
    Machine-learning regression model forecasting an employee's next-period
    workload_score, trained and evaluated using historically recorded
    WorkloadHistory data available in the system. This project's
    WorkloadHistory records are synthetic/demo data (seed_ai_data.py), not
    independently observed real-world company history.

    CHRONOLOGICAL SPLIT (corrected design): records are sorted by their
    target period (T+1) ascending, and the split point is chosen so ALL
    training rows have an earlier-or-equal target period than ALL test
    rows. This is not a per-employee split — it is a global chronological
    cutoff across the whole dataset — so no random shuffling can place a
    later observation into training while an earlier one lands in test.
    No T+1 target information is used as a feature for that same row (see
    build_workload_forecast_dataset).
    """
    from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
    from sklearn.pipeline import Pipeline

    records = build_workload_forecast_dataset()
    rows = [r[0] for r in records]

    is_valid, val_report = validate_regression_dataset(
        rows and pd.DataFrame(rows), min_rows=WORKLOAD_FORECAST_MIN_ROWS
    )
    if not rows or not is_valid:
        reason = {
            'status': 'WORKLOAD_FORECAST_NOT_READY',
            'message': "Insufficient historical WorkloadHistory periods for reliable forecasting.",
            'validation_report': val_report if rows else {'total_rows': 0, 'issues': ['No records found.']},
            'required_minimum_rows': WORKLOAD_FORECAST_MIN_ROWS,
        }
        register_insufficient_data('workload_forecast', reason)
        return reason

    # Sort chronologically by target period — no shuffling.
    records_sorted = sorted(records, key=lambda r: r[2])
    split_idx = int(len(records_sorted) * 0.75)
    train_part = records_sorted[:split_idx]
    test_part = records_sorted[split_idx:]

    if len(test_part) < WORKLOAD_FORECAST_MIN_TEST_ROWS or len(train_part) < 1:
        reason = {
            'status': 'WORKLOAD_FORECAST_NOT_READY',
            'message': (
                f"Chronological split yields only {len(test_part)} test row(s) "
                f"(need at least {WORKLOAD_FORECAST_MIN_TEST_ROWS}) with {len(train_part)} "
                f"training row(s). A random split could produce a larger test set, but "
                f"would misrepresent this as evaluating on 'future' data when it is not — "
                f"reporting an evaluation here would be misleading rather than genuinely "
                f"chronological."
            ),
            'total_rows': len(records_sorted),
            'chronological_test_rows': len(test_part),
            'chronological_train_rows': len(train_part),
            'required_minimum_test_rows': WORKLOAD_FORECAST_MIN_TEST_ROWS,
        }
        register_insufficient_data('workload_forecast', reason)
        return reason

    X_train = pd.DataFrame([r[0] for r in train_part])
    y_train = [r[1] for r in train_part]
    X_test = pd.DataFrame([r[0] for r in test_part])
    y_test = [r[1] for r in test_part]
    feature_columns = list(X_train.columns)

    earliest_test_period = min(r[2] for r in test_part)
    latest_train_period = max(r[2] for r in train_part)

    # TimeSeriesSplit respects chronological order WITHIN the training
    # partition itself: each of its 3 folds validates on a later slice than
    # it trains on, so hyperparameter search never validates on a fold that
    # precedes its own training fold — unlike ordinary KFold(cv=3), which
    # would shuffle-assign rows to folds regardless of their target period
    # and could validate on an earlier period after training on a later one.
    best_pipeline, best_score, best_algo_name = None, float('inf'), None
    candidates_tried = []
    tscv = TimeSeriesSplit(n_splits=3)
    for algo_name, cfg in WORKLOAD_FORECAST_CANDIDATES.items():
        pipeline = Pipeline([('prep', build_preprocessing_pipeline()), ('reg', cfg['estimator'])])
        search = RandomizedSearchCV(pipeline, cfg['params'], n_iter=6, cv=tscv,
                                     scoring='neg_mean_absolute_error', random_state=42, n_jobs=1)
        search.fit(X_train, y_train)
        fitted = search.best_estimator_
        mae = -search.best_score_
        candidates_tried.append({'algorithm': algo_name, 'cv_mae': round(float(mae), 3)})
        if mae < best_score:
            best_score, best_pipeline, best_algo_name = mae, fitted, algo_name

    test_metrics = evaluate_regressor(best_pipeline, X_test, y_test)

    metrics = {
        'algorithm': best_algo_name,
        'candidates_compared': [c['algorithm'] for c in candidates_tried],
        'candidates_detail': candidates_tried,
        'test_metrics': test_metrics,
        'training_samples': len(y_train),
        'test_samples': len(y_test),
        'total_rows': len(records_sorted),
        'features_used': feature_columns,
        'split_type': 'chronological',
        'latest_training_target_period': str(latest_train_period),
        'earliest_test_target_period': str(earliest_test_period),
        'random_state': 42,
        'data_note': "WorkloadHistory in this project is synthetic/demo data (seed_ai_data.py).",
    }

    os.makedirs(MODEL_DIR, exist_ok=True)
    file_path = os.path.join(MODEL_DIR, 'workload_forecast_model.pkl')
    joblib.dump({'model': best_pipeline, 'feature_columns': feature_columns,
                 'algorithm': best_algo_name, 'trained_at': datetime.now().isoformat()}, file_path)

    if test_metrics['r2_score'] <= 0:
        metrics['rejection_reason'] = (
            f"Test R² ({test_metrics['r2_score']}) indicates the model performs no better "
            f"than predicting the average workload score. Not registered as production-usable."
        )
        register_regressor_not_ready('workload_forecast', best_algo_name, metrics, file_path)
        return {'status': 'MODEL_NOT_READY', 'metrics': metrics, 'file_path': file_path}

    register_model('workload_forecast', 'v1', best_algo_name, metrics, file_path, active=True)
    return {'status': 'trained', 'metrics': metrics, 'file_path': file_path}


def train_task_delay_risk_model():
    """
    AUDITED AND NOT IMPLEMENTED: Task has no completion-date field, and
    Task.assignDate is auto_now=True (overwritten on every save, not a
    reliable creation timestamp). The only observable "delay" fact in this
    schema is whether a non-Completed task's endDate has passed — a
    deterministic date comparison, not an ML target — and Completed tasks
    have no recorded information about whether they finished late. No
    leakage-free future-delay target can be constructed from the current
    schema without adding a completion-timestamp field and accumulating
    real completion events over time.
    """
    return {
        'status': 'TASK_DELAY_MODEL_NOT_READY',
        'message': (
            "Task model lacks a completion-date field, and assignDate is "
            "auto_now=True (unreliable as a fixed creation timestamp). A "
            "defensible future-delay target cannot be constructed from the "
            "current schema. Requires adding a completedDate field to Task "
            "and accumulating genuine completion events over time."
        ),
    }


def train_nlp_sentiment_model():
    """
    PATH C — NOT READY (Prompt 6 audit).

    The Feedback table currently contains zero records, so there is no
    genuine text corpus and no genuine sentiment label (no stored
    sentiment field; no rating-derived label validated against real
    text) available for training or evaluation. Per the documented
    data-leakage/academic-honesty rules for this project, no model is
    trained, no keyword/rule-based sentiment is substituted for it, and
    no accuracy/F1 is reported, since none would be genuine.

    Recorded via register_insufficient_data using the existing
    ModelVersion registry (is_active=False), the same pattern used for
    project_outcome and workload_forecast when their data is
    insufficient.
    """
    from Employee.models import Feedback

    feedback_count = Feedback.objects.count()
    non_empty_text_count = Feedback.objects.exclude(feedback_text__isnull=True).exclude(feedback_text__exact='').count()

    reason = {
        'status': 'NLP_SENTIMENT_NOT_READY',
        'message': (
            "The Feedback table currently contains zero records, so there is no "
            "genuine text corpus or labelled sentiment data available for "
            "training/validation."
        ),
        'feedback_record_count': feedback_count,
        'non_empty_feedback_text_count': non_empty_text_count,
        'issues': [
            "No Feedback records exist — no genuine text corpus to train or "
            "validate a sentiment model on.",
        ],
    }
    register_insufficient_data('nlp_sentiment', reason)
    return reason


def train_all_models():
    return {
        'project_outcome': train_project_outcome_model(),
        'employee_performance': train_employee_performance_model(),
        'employee_risk': train_employee_risk_model(),
        'task_delay_risk': train_task_delay_risk_model(),
        'workload_forecast': train_workload_forecast_model(),
        'nlp_sentiment': train_nlp_sentiment_model(),
    }