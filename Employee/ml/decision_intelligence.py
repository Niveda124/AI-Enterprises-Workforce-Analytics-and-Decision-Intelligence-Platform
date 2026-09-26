"""
Decision Intelligence layer — Prompt 8.

This module combines ONLY genuine available signals:
  - the real ModelVersion registry state (never an invented row),
  - real prediction_service output, and ONLY for a model confirmed ACTIVE
    in ModelVersion (never a MODEL_NOT_READY/INSUFFICIENT_DATA model),
  - real database aggregates/counts, clearly tagged as analytics rather
    than ML, and
  - the project's existing deterministic RULE_BASED functions
    (calculate_workload_status / calculate_allocation_score), reused as-is
    and clearly labelled — never presented as ML/AI.

Academic classification used throughout, per Prompt 8 §9/§10:
    REAL_ML             - an ACTIVE, quality-gated classifier actually predicted
    REAL_NLP             - an ACTIVE NLP model actually predicted (none exist yet)
    FORECASTING          - an ACTIVE regression model actually predicted
    DATABASE_ANALYTICS   - a genuine DB aggregate/count, not model-derived
    RULE_BASED           - a deterministic formula, explicitly not ML
    NOT_READY             - capability not implemented / rejected by its quality gate
    INSUFFICIENT_DATA     - capability attempted but data volume too small

Current audit state (see Prompt 8 audit): zero models are active. This
module is therefore EXPECTED to currently return empty ml_insights, real
analytics, labelled rule-based insights, and a populated unavailable_models
list. That is correct behavior, not a bug — this module must never
manufacture a prediction, metric, or generic AI-sounding text to appear
"more intelligent" than the underlying data supports.
"""
import json

from django.db.models import Count

from Employee.models import ModelVersion, Prediction


# ---------------------------------------------------------------------------
# Registered models (go through the ModelVersion registry) vs. static models
# (structurally never get a ModelVersion row — see Prompt 7/8 audits).
# ---------------------------------------------------------------------------

_REGISTRY_MODEL_NAMES = [
    'project_outcome', 'employee_performance', 'employee_risk', 'workload_forecast',
]

# What an ACTIVE version of each registered model represents academically.
_ACTIVE_CLASSIFICATION = {
    'project_outcome': 'REAL_ML',
    'employee_performance': 'REAL_ML',
    'employee_risk': 'REAL_ML',
    'workload_forecast': 'FORECASTING',
    'nlp_sentiment': 'REAL_NLP',
}

# Models that structurally never receive a ModelVersion row. Their state is
# taken directly from the verified Prompt 7 / Prompt 6 audits — never
# invented, and never given a fake ModelVersion row.
_STATIC_MODEL_HEALTH = {
    'task_delay_risk': {
        'status': 'TASK_DELAY_MODEL_NOT_READY',
        'reason': (
            "No genuine completion-date field exists on Task or TaskTracking, "
            "and Task.assignDate / TaskTracking.updationDate are auto_now=True "
            "(overwritten on every save), so a reliable assignment or "
            "completion timestamp cannot be reconstructed. Task delay cannot "
            "be modelled without risking leakage under the current schema."
        ),
        'classification': 'NOT_READY',
    },
    'smart_task_allocation': {
        'status': 'SMART_ALLOCATION_NOT_READY',
        'reason': (
            "Prompt 7 audit: only 7 Task records exist project-wide (far "
            "below any workable train/test threshold), there is no historical "
            "employee-task assignment log distinct from current state, and "
            "Task.assignDate is auto_now=True so assignment-time features "
            "cannot be reliably separated from outcome information. No "
            "smart_task_allocation model has been built."
        ),
        'classification': 'NOT_READY',
    },
}

ALL_MODEL_NAMES = _REGISTRY_MODEL_NAMES + ['nlp_sentiment'] + list(_STATIC_MODEL_HEALTH.keys())


def _parse_metrics(mv):
    if not mv or not mv.metrics:
        return {}
    try:
        return json.loads(mv.metrics)
    except (TypeError, ValueError):
        return {}


def _samples_from_metrics(metrics):
    """
    Reads training/test sample counts from whatever real keys the metrics
    JSON actually has. Different register_* paths store this differently
    (a trained-but-rejected model has 'training_samples'/'test_samples'; an
    insufficient-data report only has a nested 'validation_report'). Never
    invents a number — returns None where genuinely not recorded.
    """
    training_samples = metrics.get('training_samples')
    test_samples = metrics.get('test_samples')
    if training_samples is None:
        vr = metrics.get('validation_report') or {}
        training_samples = vr.get('total_rows')
    return training_samples, test_samples


def _health_for_registry_model(name):
    """
    Reads the single most recent ModelVersion row for `name` and reports its
    real state. Never queries or invents anything beyond what that row (and
    its metrics JSON) actually contains.
    """
    mv = ModelVersion.objects.filter(model_name=name).order_by('-id').first()

    if not mv:
        return {
            'model_name': name,
            'status': 'NOT_READY',
            'is_active': False,
            'algorithm': None,
            'training_date': None,
            'version': None,
            'training_samples': None,
            'test_samples': None,
            'metrics': None,
            'reason': "No training has been attempted for this model yet.",
            'classification': 'NOT_READY',
        }

    metrics = _parse_metrics(mv)
    training_samples, test_samples = _samples_from_metrics(metrics)
    reason = metrics.get('rejection_reason') or metrics.get('message')

    if mv.is_active:
        status = 'ACTIVE'
        classification = _ACTIVE_CLASSIFICATION.get(name, 'REAL_ML')
    elif mv.version == 'INSUFFICIENT_DATA':
        status = 'INSUFFICIENT_DATA'
        classification = 'INSUFFICIENT_DATA'
    elif mv.version == 'MODEL_NOT_READY':
        status = 'MODEL_NOT_READY'
        classification = 'NOT_READY'
    else:
        # A real trained version (e.g. "v1") that is simply not the current
        # active one (superseded by a later training run).
        status = 'INACTIVE'
        classification = 'NOT_READY'

    return {
        'model_name': name,
        'status': status,
        'is_active': mv.is_active,
        'algorithm': mv.algorithm,
        'training_date': mv.training_date,  # genuinely None today — nothing in
        'version': mv.version,              # this project currently sets this field
        'training_samples': training_samples,
        'test_samples': test_samples,
        'metrics': metrics or None,
        'reason': reason,
        'classification': classification,
    }


def _health_for_nlp_sentiment():
    """
    nlp_sentiment has PATH C's honest status hard-coded in nlp_sentiment.py
    (Prompt 6). If python manage.py train_ml_models has been run since, a
    real ModelVersion row will exist and is reported the same way as any
    other registered model. If not, this reports the same NOT_READY reason
    directly from nlp_sentiment.py's own constant, plus a live (real,
    queried-now) Feedback count for transparency — never a fabricated
    training_samples/test_samples value.
    """
    mv = ModelVersion.objects.filter(model_name='nlp_sentiment').order_by('-id').first()
    if mv:
        health = _health_for_registry_model('nlp_sentiment')
        health['classification'] = (
            _ACTIVE_CLASSIFICATION['nlp_sentiment'] if mv.is_active else health['classification']
        )
        return health

    from Employee.models import Feedback
    from .nlp_sentiment import NOT_READY_REASON

    feedback_count = Feedback.objects.count()
    return {
        'model_name': 'nlp_sentiment',
        'status': 'NLP_SENTIMENT_NOT_READY',
        'is_active': False,
        'algorithm': None,
        'training_date': None,
        'version': None,
        'training_samples': None,
        'test_samples': None,
        'metrics': {'feedback_record_count': feedback_count},
        'reason': NOT_READY_REASON,
        'classification': 'INSUFFICIENT_DATA',
        'note': (
            "No ModelVersion row exists yet for nlp_sentiment because "
            "train_ml_models has not been re-run since this module was added. "
            "Feedback record count was checked live from the database instead "
            "of being read from a training run."
        ),
    }


def get_model_health(model_name=None):
    """
    Reports the real, current state of every AI capability in this project:
    project_outcome, employee_performance, employee_risk, workload_forecast,
    nlp_sentiment (all read from ModelVersion / live DB as applicable), and
    task_delay_risk / smart_task_allocation (which never receive a
    ModelVersion row — their state is the audit-verified static reason
    above, never an invented row).

    Args:
        model_name: if given, returns a single health dict (or None if the
            name isn't recognized). Otherwise returns the list for all 7
            models.
    """
    all_health = []
    for name in _REGISTRY_MODEL_NAMES:
        all_health.append(_health_for_registry_model(name))
    all_health.append(_health_for_nlp_sentiment())
    for name, info in _STATIC_MODEL_HEALTH.items():
        all_health.append({
            'model_name': name,
            'status': info['status'],
            'is_active': False,
            'algorithm': None,
            'training_date': None,
            'version': None,
            'training_samples': None,
            'test_samples': None,
            'metrics': None,
            'reason': info['reason'],
            'classification': info['classification'],
        })

    if model_name is not None:
        return next((h for h in all_health if h['model_name'] == model_name), None)
    return all_health


def get_model_monitoring(model_name):
    """
    Reports real model/version/training/metrics information for one model,
    plus an honest drift section. Drift is always reported as
    MONITORING_NOT_AVAILABLE: this project's Prediction model has no
    ground-truth/actual-outcome field at all (only predicted_outcome), so
    even the historical Prediction rows that do exist in the database can
    never be scored for drift under the current schema — this is not merely
    "no data has accumulated yet."
    """
    health = get_model_health(model_name)
    if health is None:
        return {
            'model_name': model_name,
            'status': 'UNKNOWN',
            'message': f"'{model_name}' is not a recognized model in this project.",
        }

    stale_prediction_count = 0
    if model_name in ('project_outcome', 'employee_performance', 'employee_risk', 'workload_forecast'):
        type_map = {
            'project_outcome': 'PROJECT_OUTCOME', 'employee_performance': 'EMPLOYEE_PERFORMANCE',
            'employee_risk': 'EMPLOYEE_RISK', 'workload_forecast': 'WORKLOAD_FORECAST',
        }
        stale_prediction_count = Prediction.objects.filter(prediction_type=type_map[model_name]).count()

    return {
        'model_name': health['model_name'],
        'version': health.get('version'),
        'algorithm': health.get('algorithm'),
        'training_date': health.get('training_date'),
        'training_samples': health.get('training_samples'),
        'test_samples': health.get('test_samples'),
        'metrics': health.get('metrics'),
        'is_active': health.get('is_active'),
        'status': health.get('status'),
        'reason': health.get('reason'),
        'drift': {
            'status': 'MONITORING_NOT_AVAILABLE',
            'reason': (
                "No production prediction history has accumulated for the "
                "currently active model (there is no active model right now), "
                "and even the {0} historical Prediction record(s) already "
                "stored for this model type cannot be used for drift analysis: "
                "the Prediction model has no ground-truth/actual-outcome field "
                "to compare predictions against."
            ).format(stale_prediction_count),
        },
    }


# ---------------------------------------------------------------------------
# Decision Intelligence assembly
# ---------------------------------------------------------------------------

def _ml_insights_for_context(employee=None, project=None):
    """
    Calls prediction_service functions ONLY for models confirmed ACTIVE in
    ModelVersion right now. Never calls an inactive model and never
    synthesizes an insight from a rejected one.
    """
    from . import prediction_service as ps

    insights = []
    active_names = {h['model_name'] for h in get_model_health() if h.get('is_active')}

    if employee is not None:
        if 'employee_performance' in active_names:
            result = ps.predict_employee_performance(employee, save=False)
            if result.get('status') == 'ok':
                insights.append({
                    'category': 'REAL_ML', 'model': 'employee_performance',
                    'subject': str(employee), 'result': result,
                })
        if 'employee_risk' in active_names:
            result = ps.predict_employee_risk(employee, save=False)
            if result.get('status') == 'ok':
                insights.append({
                    'category': 'REAL_ML', 'model': 'employee_risk',
                    'subject': str(employee), 'result': result,
                })
        if 'workload_forecast' in active_names:
            result = ps.predict_workload_forecast(employee, save=False)
            if result.get('status') == 'ok':
                insights.append({
                    'category': 'FORECASTING', 'model': 'workload_forecast',
                    'subject': str(employee), 'result': result,
                })

    if project is not None and 'project_outcome' in active_names:
        result = ps.predict_project_outcome(project, save=False)
        if result.get('status') == 'ok':
            insights.append({
                'category': 'REAL_ML', 'model': 'project_outcome',
                'subject': str(project), 'result': result,
            })

    return insights


def _analytics_for_context(employee=None, project=None):
    """
    Genuine database aggregates only — every item explicitly tagged
    DATABASE_ANALYTICS. Reuses the same query shapes already used in
    Employee/views.py:admin_workload_intelligence for consistency, without
    importing views.py (kept independent to avoid any import-order coupling
    with the request/response layer).
    """
    from datetime import date
    from Employee.models import Task, WorkloadHistory, PerformanceHistory, Department, Project as ProjectModel

    analytics = []

    if employee is not None:
        tasks = Task.objects.filter(emp=employee)
        pending = tasks.exclude(status="Completed").count()
        overdue = tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
        completed = tasks.filter(status="Completed").count()
        latest_workload = WorkloadHistory.objects.filter(employee=employee).order_by('-period').first()
        latest_perf = PerformanceHistory.objects.filter(employee=employee).order_by('-period').first()
        analytics.append({
            'category': 'DATABASE_ANALYTICS', 'scope': 'employee', 'subject': str(employee),
            'data': {
                'tasks_assigned': tasks.count(), 'tasks_completed': completed,
                'tasks_pending': pending, 'tasks_overdue': overdue,
                'latest_workload_score': latest_workload.workload_score if latest_workload else None,
                'latest_workload_period': str(latest_workload.period) if latest_workload else None,
                'latest_performance_score': latest_perf.performance_score if latest_perf else None,
                'latest_performance_period': str(latest_perf.period) if latest_perf else None,
            },
        })

    if project is not None:
        p_tasks = Task.objects.filter(project=project)
        analytics.append({
            'category': 'DATABASE_ANALYTICS', 'scope': 'project', 'subject': str(project),
            'data': {
                'status': project.status, 'progress': project.progress,
                'tasks_total': p_tasks.count(),
                'tasks_completed': p_tasks.filter(status="Completed").count(),
                'tasks_overdue': p_tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count(),
            },
        })

    if employee is None and project is None:
        # Organization-wide summary.
        all_tasks = Task.objects.all()
        analytics.append({
            'category': 'DATABASE_ANALYTICS', 'scope': 'organization', 'subject': 'All tasks',
            'data': {
                'total_tasks': all_tasks.count(),
                'completed_tasks': all_tasks.filter(status="Completed").count(),
                'overdue_tasks': all_tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count(),
            },
        })
        analytics.append({
            'category': 'DATABASE_ANALYTICS', 'scope': 'organization', 'subject': 'Departments',
            'data': {'department_count': Department.objects.count()},
        })
        analytics.append({
            'category': 'DATABASE_ANALYTICS', 'scope': 'organization', 'subject': 'Projects',
            'data': {
                'total_projects': ProjectModel.objects.count(),
                'by_status': dict(
                    ProjectModel.objects.values_list('status').annotate(Count('id'))
                ) if ProjectModel.objects.exists() else {},
            },
        })

    return analytics


def _rule_based_insights_for_context(employee=None):
    """
    Reuses the project's EXISTING deterministic functions from
    Employee/views.py as-is (no reimplementation), explicitly labelled
    RULE_BASED — never presented as ML/AI.
    """
    from datetime import date
    from Employee.models import Task, WorkloadHistory, PerformanceHistory
    from Employee.views import calculate_workload_status, calculate_allocation_score

    insights = []
    if employee is not None:
        tasks = Task.objects.filter(emp=employee)
        pending = tasks.exclude(status="Completed").count()
        overdue = tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
        latest_workload = WorkloadHistory.objects.filter(employee=employee).order_by('-period').first()
        latest_perf = PerformanceHistory.objects.filter(employee=employee).order_by('-period').first()
        workload_score = latest_workload.workload_score if latest_workload else 0
        performance_score = latest_perf.performance_score if latest_perf else 0

        insights.append({
            'category': 'RULE_BASED', 'function': 'calculate_workload_status', 'subject': str(employee),
            'result': calculate_workload_status(pending, overdue),
            'inputs': {'pending': pending, 'overdue': overdue},
        })
        insights.append({
            'category': 'RULE_BASED', 'function': 'calculate_allocation_score', 'subject': str(employee),
            'result': calculate_allocation_score(pending, overdue, workload_score, performance_score),
            'inputs': {
                'pending': pending, 'overdue': overdue,
                'workload_score': workload_score, 'performance_score': performance_score,
            },
        })

    return insights


def generate_decision_intelligence(context=None):
    """
    Central Decision Intelligence entry point.

    Args:
        context: optional dict with any of:
            'employee' -> an Employee instance (adds per-employee ML
                insights/analytics/rule-based results)
            'project'  -> a Project instance (adds per-project ML
                insights/analytics)
        If omitted or empty, returns an organization-wide view (analytics +
        full model health only — no single-entity ML/rule-based results).

    Returns:
        {
            "ml_insights": [...],        # only from CONFIRMED ACTIVE models
            "analytics": [...],           # genuine DB aggregates, tagged DATABASE_ANALYTICS
            "rule_based_insights": [...], # existing deterministic functions, tagged RULE_BASED
            "unavailable_models": [...],  # every non-active model with its real reason
            "model_health": [...],        # full get_model_health() for all 7 models
        }
    """
    context = context or {}
    employee = context.get('employee')
    project = context.get('project')

    model_health = get_model_health()
    unavailable_models = [h for h in model_health if not h.get('is_active')]

    return {
        'ml_insights': _ml_insights_for_context(employee=employee, project=project),
        'analytics': _analytics_for_context(employee=employee, project=project),
        'rule_based_insights': _rule_based_insights_for_context(employee=employee),
        'unavailable_models': unavailable_models,
        'model_health': model_health,
    }


def scenario_what_if(project, overrides):
    """
    Structured what-if support. Only ever wraps the project's EXISTING
    whatif_project_outcome() (the only what-if implementation in this
    project), and only when project_outcome is confirmed ACTIVE right now.
    Never fabricates a hypothetical outcome for a model that has no
    what-if implementation or is not active.
    """
    from . import prediction_service as ps

    health = get_model_health('project_outcome')
    if not health or not health.get('is_active'):
        return {
            'status': 'SCENARIO_NOT_READY',
            'reason': (health or {}).get('reason') or (
                "project_outcome model is not currently active."
            ),
        }
    return ps.whatif_project_outcome(project, overrides)
