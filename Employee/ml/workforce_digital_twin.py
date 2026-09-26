"""
Workforce Digital Twin (Prompt 3 — Foundation)
================================================
A read-only aggregation layer that assembles a single, unified snapshot of
an employee, a project, or the whole workforce from EXISTING real database
records only.

This module does NOT:
  - train, retrain, or call any ML model directly
  - fabricate, randomize, or estimate any value
  - duplicate the scoring logic already in prediction_service.py /
    decision_intelligence.py / feature_engineering.py

It DOES:
  - reuse `get_model_metadata()` from prediction_service.py to find out
    whether an ACTIVE model exists for a given prediction type (per the
    project's own rule: only report ML output if a model is actually
    active — never fabricate a stand-in)
  - read the LATEST already-stored `Prediction` row for that type, exactly
    like `_build_project_signal` / `_build_employee_signal` in views.py do
    (no new prediction is triggered here — regeneration only happens via
    the existing explicit "Run AI Analysis" action)
  - compute simple, transparent, real-data statistics (task counts,
    trends between the two most recent history periods, project rosters)
    directly from Task / PerformanceHistory / WorkloadHistory / Project /
    ProjectMember / TaskTracking records

Public functions:
    get_employee_digital_twin(employee_id)
    get_project_digital_twin(project_id)
    get_workforce_digital_twin()
"""
from datetime import date

from Employee.models import (
    Employee, Project, ProjectMember, Task, TaskTracking,
    PerformanceHistory, WorkloadHistory, Department, Prediction,
)
from .prediction_service import get_model_metadata

RECENT_ACTIVITY_LIMIT = 5

# The exact model_name strings the training pipeline registers under
# (see train_models.py / model_registry.py) — reused as-is, not redefined.
MODEL_PROJECT_OUTCOME = 'project_outcome'
MODEL_EMPLOYEE_PERFORMANCE = 'employee_performance'
MODEL_EMPLOYEE_RISK = 'employee_risk'
MODEL_WORKLOAD_FORECAST = 'workload_forecast'


# ---------------------------------------------------------------------------
# Small real-data helpers (no ML, no fabrication)
# ---------------------------------------------------------------------------

def _employee_task_stats(employee):
    tasks = Task.objects.filter(emp=employee)
    assigned = tasks.count()
    completed = tasks.filter(status="Completed").count()
    overdue = tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
    pending = assigned - completed
    return {
        'assigned': assigned,
        'completed': completed,
        'pending': pending,
        'overdue': overdue,
        'completion_rate': round(completed / assigned, 3) if assigned else None,
        'overdue_ratio': round(overdue / assigned, 3) if assigned else None,
    }


def _project_task_stats(project):
    tasks = Task.objects.filter(project=project)
    total = tasks.count()
    completed = tasks.filter(status="Completed").count()
    overdue = tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
    pending = total - completed
    return {
        'total': total,
        'completed': completed,
        'pending': pending,
        'overdue': overdue,
        'completion_rate': round(completed / total, 3) if total else None,
        'overdue_ratio': round(overdue / total, 3) if total else None,
    }


def _trend_from_history(qs, score_field):
    """
    Compares the two most recent rows of a history queryset (ordered by
    period) on `score_field`. Returns a real, computed direction — never
    a guess — or 'insufficient_history' if fewer than 2 periods exist.
    """
    rows = list(qs.order_by('-period')[:2])
    if len(rows) < 2:
        return {'direction': 'insufficient_history', 'latest': getattr(rows[0], score_field) if rows else None, 'delta': None}
    latest, previous = getattr(rows[0], score_field), getattr(rows[1], score_field)
    delta = round(latest - previous, 3)
    if delta > 0:
        direction = 'improving'
    elif delta < 0:
        direction = 'declining'
    else:
        direction = 'stable'
    return {'direction': direction, 'latest': latest, 'previous': previous, 'delta': delta}


def _latest_prediction_if_active(model_name, prediction_type, **entity_filter):
    """
    Only surfaces prediction output if an ACTIVE ModelVersion exists for
    `model_name` (reuses the existing prediction_service check — no
    duplicated logic). If no active model, or no stored prediction yet,
    says so explicitly rather than inventing a value.
    """
    metadata = get_model_metadata(model_name)
    if not metadata:
        return {'available': False, 'reason': 'no_active_model'}

    pred = Prediction.objects.filter(prediction_type=prediction_type, **entity_filter).order_by('-prediction_date').first()
    if not pred:
        return {'available': False, 'reason': 'no_prediction_generated_yet', 'active_model': metadata}

    return {
        'available': True,
        'predicted_outcome': pred.predicted_outcome,
        'confidence': pred.confidence,
        'risk_level': pred.risk_level,
        'model_version': pred.model_version,
        'prediction_date': pred.prediction_date,
        'actual_outcome': pred.actual_outcome,
        'active_model': metadata,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_employee_digital_twin(employee_id):
    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return {'error': 'employee_not_found', 'employee_id': employee_id}

    perf_history = PerformanceHistory.objects.filter(employee=employee)
    load_history = WorkloadHistory.objects.filter(employee=employee)
    latest_perf = perf_history.order_by('-period').first()
    latest_load = load_history.order_by('-period').first()

    memberships = ProjectMember.objects.filter(employee=employee, is_active=True).select_related('project')
    recent_activity = TaskTracking.objects.filter(taskId__emp=employee).order_by('-updationDate')[:RECENT_ACTIVITY_LIMIT]

    return {
        'employee_id': employee.id,
        'name': employee.user.first_name if employee.user else employee.empid,
        'profile': {
            'empid': employee.empid,
            'designation': employee.designation,
            'department': employee.dept.name if employee.dept else None,
            'contact': employee.contact,
            'date_of_joining': employee.doj,
            'on_leave': employee.on_leave,
            'leave_return_date': employee.leave_return_date,
            'description': employee.description,
            # Not tracked anywhere in the current schema — reported honestly
            # as unavailable rather than inferred from designation/description.
            'skills': None,
        },
        'current_workload': _employee_task_stats(employee),
        'performance_snapshot': {
            'latest_period': latest_perf.period if latest_perf else None,
            'completion_rate': latest_perf.completion_rate if latest_perf else None,
            'on_time_rate': latest_perf.on_time_rate if latest_perf else None,
            'avg_delay_days': latest_perf.avg_delay_days if latest_perf else None,
            'performance_score': latest_perf.performance_score if latest_perf else None,
        } if latest_perf else None,
        'performance_trend': _trend_from_history(perf_history, 'performance_score') if perf_history.exists() else {'direction': 'no_history'},
        'workload_snapshot': {
            'latest_period': latest_load.period if latest_load else None,
            'assigned_count': latest_load.assigned_count if latest_load else None,
            'pending_count': latest_load.pending_count if latest_load else None,
            'overdue_count': latest_load.overdue_count if latest_load else None,
            'workload_score': latest_load.workload_score if latest_load else None,
        } if latest_load else None,
        'workload_trend': _trend_from_history(load_history, 'workload_score') if load_history.exists() else {'direction': 'no_history'},
        'project_involvement': [
            {'project_id': m.project.id, 'project_name': m.project.name, 'role': m.role, 'status': m.project.status}
            for m in memberships
        ],
        'recent_task_activity': [
            {'task_id': t.taskId_id, 'task_title': t.taskId.title, 'status': t.status,
             'work_completed': t.workCompleted, 'updated': t.updationDate}
            for t in recent_activity
        ],
        'risk_prediction': _latest_prediction_if_active(MODEL_EMPLOYEE_RISK, 'EMPLOYEE_RISK', employee=employee),
        'performance_prediction': _latest_prediction_if_active(MODEL_EMPLOYEE_PERFORMANCE, 'EMPLOYEE_PERFORMANCE', employee=employee),
    }


def get_project_digital_twin(project_id):
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {'error': 'project_not_found', 'project_id': project_id}

    members = ProjectMember.objects.filter(project=project, is_active=True).select_related('employee', 'employee__user')

    workload_distribution = []
    perf_scores = []
    completion_rates = []
    for m in members:
        stats = _employee_task_stats(m.employee)
        workload_distribution.append({
            'employee_id': m.employee.id,
            'name': m.employee.user.first_name if m.employee.user else m.employee.empid,
            'role': m.role,
            **stats,
        })
        latest_perf = PerformanceHistory.objects.filter(employee=m.employee).order_by('-period').first()
        if latest_perf:
            perf_scores.append(latest_perf.performance_score)
            completion_rates.append(latest_perf.completion_rate)

    return {
        'project_id': project.id,
        'name': project.name,
        'code': project.code,
        'status': project.status,
        'priority': project.priority,
        'progress': project.progress,
        'start_date': project.start_date,
        'deadline': project.deadline,
        'department': project.dept.name if project.dept else None,
        'manager': project.manager.user.first_name if project.manager and project.manager.user else None,
        'task_stats': _project_task_stats(project),
        'employee_count': members.count(),
        'workload_distribution': workload_distribution,
        'performance_indicators': {
            'team_avg_performance_score': round(sum(perf_scores) / len(perf_scores), 3) if perf_scores else None,
            'team_avg_completion_rate': round(sum(completion_rates) / len(completion_rates), 3) if completion_rates else None,
            'members_with_history': len(perf_scores),
            'members_without_history': members.count() - len(perf_scores),
        },
        'risk_prediction': _latest_prediction_if_active(MODEL_PROJECT_OUTCOME, 'PROJECT_OUTCOME', project=project),
    }


def get_workforce_digital_twin():
    """
    Org-wide rollup. Aggregates only what get_employee_digital_twin /
    get_project_digital_twin already compute per entity, plus simple
    real counts — no separate scoring logic of its own.
    """
    employees = Employee.objects.all()
    projects = Project.objects.all()

    dept_rollup = []
    for dept in Department.objects.all():
        dept_employees = employees.filter(dept=dept)
        dept_rollup.append({
            'department_id': dept.id,
            'department': dept.name,
            'employee_count': dept_employees.count(),
        })

    active_models = {
        name: bool(get_model_metadata(name))
        for name in [MODEL_PROJECT_OUTCOME, MODEL_EMPLOYEE_PERFORMANCE, MODEL_EMPLOYEE_RISK, MODEL_WORKLOAD_FORECAST]
    }

    project_status_breakdown = {}
    for status_choice, _label in Project.STATUS_CHOICES:
        project_status_breakdown[status_choice] = projects.filter(status=status_choice).count()

    org_task_stats = {
        'total_tasks': Task.objects.count(),
        'completed_tasks': Task.objects.filter(status="Completed").count(),
        'overdue_tasks': Task.objects.exclude(status="Completed").filter(endDate__lt=date.today()).count(),
    }

    high_risk_employees = Prediction.objects.filter(
        prediction_type='EMPLOYEE_RISK', risk_level='High'
    ).values('employee').distinct().count() if active_models[MODEL_EMPLOYEE_RISK] else 0

    high_risk_projects = Prediction.objects.filter(
        prediction_type='PROJECT_OUTCOME', risk_level='High'
    ).values('project').distinct().count() if active_models[MODEL_PROJECT_OUTCOME] else 0

    return {
        'employee_count': employees.count(),
        'project_count': projects.count(),
        'department_rollup': dept_rollup,
        'project_status_breakdown': project_status_breakdown,
        'org_task_stats': org_task_stats,
        'active_models': active_models,
        'high_risk_employee_count': high_risk_employees,
        'high_risk_project_count': high_risk_projects,
    }
