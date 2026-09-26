"""
Early Warning Engine (Prompt 9)
=================================
Computes genuine, CURRENT early-warning signals from real data, reusing
Digital Twin / anomaly_detection / prediction_service — nothing here
duplicates their calculations. Warnings are recomputed live from current
database state each call (same pattern as anomaly_detection's own
workforce-wide scan), because the underlying state changes constantly
and a stored "warning" row would go stale immediately. No new database
model was created for this (see Part 17 of the prompt — the existing
Notification model already covers the one case that genuinely needs
persistence: deduplicated alerting, wired in views.py).

Severity is a transparent, DOCUMENTED rule-based bucket — NOT a
statistically calibrated probability:
  INFO     - a data point worth surfacing, no real pressure yet
  WATCH    - exactly one piece of real evidence present
  WARNING  - two+ pieces of evidence, or a Medium-risk active ML signal
  CRITICAL - an overdue/high-risk situation that has already materialized,
             or a High-risk active ML signal

Every warning is a plain dict with: signal_type, entity_type, entity_id,
entity_name, severity, evidence (literal real numbers/facts), source
(RULE-BASED SIGNAL / ML FORECAST / ANOMALY DETECTION), and a disclaimer
that this is not a guarantee.
"""
from datetime import date, timedelta

from Employee.models import Employee, Project, Task, WorkloadHistory, Prediction
from .workforce_digital_twin import _employee_task_stats, _project_task_stats
from .anomaly_detection import detect_workforce_anomalies
from .prediction_service import get_model_metadata, predict_workload_forecast

DISCLAIMER = ("This is an early warning based on available historical/current data. "
              "It does not guarantee that the predicted situation will occur.")


def _workload_trend(employee):
    hist = list(WorkloadHistory.objects.filter(employee=employee).order_by('-period')[:2])
    if len(hist) < 2:
        return None
    latest, previous = hist[0], hist[1]
    delta = round(latest.workload_score - previous.workload_score, 2)
    direction = 'increasing' if delta > 0 else ('decreasing' if delta < 0 else 'stable')
    return {'direction': direction, 'latest': latest.workload_score, 'previous': previous.workload_score, 'delta': delta}


def _employee_warnings(employee, anomaly_summary=None):
    warnings = []
    stats = _employee_task_stats(employee)
    trend = _workload_trend(employee)
    name = employee.user.first_name if employee.user else employee.empid

    evidence, points = [], 0
    if trend and trend['direction'] == 'increasing':
        evidence.append(f"Workload score increased from {trend['previous']} to {trend['latest']} across the last two recorded periods.")
        points += 1
    if stats['pending'] and stats['pending'] >= 3:
        evidence.append(f"{stats['pending']} pending task(s) currently assigned.")
        points += 1
    if stats['overdue']:
        evidence.append(f"{stats['overdue']} task(s) already overdue.")
        points += 2
    upcoming = Task.objects.filter(emp=employee).exclude(status="Completed").filter(
        endDate__gte=date.today(), endDate__lte=date.today() + timedelta(days=3)
    ).count()
    if upcoming:
        evidence.append(f"{upcoming} task(s) due within 3 days.")
        points += 1

    if evidence:
        severity = 'CRITICAL' if (stats['overdue'] and points >= 4) else ('WARNING' if points >= 3 else 'WATCH')
        warnings.append({
            'signal_type': 'WORKLOAD_PRESSURE', 'entity_type': 'employee', 'entity_id': employee.id,
            'entity_name': name, 'severity': severity, 'evidence': evidence,
            'source': 'RULE-BASED SIGNAL', 'disclaimer': DISCLAIMER,
            'whatif_scenario': 'WORKLOAD_SCENARIO', 'whatif_params': {'entity_type': 'employee', 'entity_id': employee.id},
        })

    if anomaly_summary is None:
        anomaly_summary = detect_workforce_anomalies()
    if anomaly_summary['status'] == 'OK':
        for a in anomaly_summary['anomalies']:
            if a['employee_id'] == employee.id:
                warnings.append({
                    'signal_type': 'ANOMALY_DETECTED', 'entity_type': 'employee', 'entity_id': employee.id,
                    'entity_name': name, 'severity': 'WARNING',
                    'evidence': [f"Statistical anomaly score {a['anomaly_score']} (IsolationForest) relative to the current workforce."],
                    'source': 'ANOMALY DETECTION', 'disclaimer': DISCLAIMER,
                    'whatif_scenario': None, 'whatif_params': None,
                })

    risk_meta = get_model_metadata('employee_risk')
    if risk_meta:
        pred = Prediction.objects.filter(employee=employee, prediction_type='EMPLOYEE_RISK').order_by('-prediction_date').first()
        if pred and pred.risk_level in ('High', 'Medium'):
            warnings.append({
                'signal_type': 'ML_RISK_FORECAST', 'entity_type': 'employee', 'entity_id': employee.id,
                'entity_name': name, 'severity': 'CRITICAL' if pred.risk_level == 'High' else 'WARNING',
                'evidence': [f"Active model {pred.model_version} predicts '{pred.predicted_outcome}' with confidence {pred.confidence}."],
                'source': 'ML FORECAST', 'disclaimer': DISCLAIMER,
                'whatif_scenario': None, 'whatif_params': None,
            })

    forecast_meta = get_model_metadata('workload_forecast')
    if forecast_meta:
        result = predict_workload_forecast(employee, save=False)
        if result.get('status') == 'ok' and stats.get('assigned') is not None:
            current_score = WorkloadHistory.objects.filter(employee=employee).order_by('-period').first()
            current_score = current_score.workload_score if current_score else None
            if current_score is not None and result['predicted_workload_score'] > current_score:
                warnings.append({
                    'signal_type': 'ML_WORKLOAD_FORECAST', 'entity_type': 'employee', 'entity_id': employee.id,
                    'entity_name': name, 'severity': 'WATCH',
                    'evidence': [f"Active model {result['model_version']} forecasts next-period workload score "
                                 f"{result['predicted_workload_score']} vs current {current_score}."],
                    'source': 'ML FORECAST', 'disclaimer': DISCLAIMER,
                    'whatif_scenario': 'WORKLOAD_SCENARIO', 'whatif_params': {'entity_type': 'employee', 'entity_id': employee.id},
                })
    return warnings


def _project_warnings(project):
    warnings = []
    stats = _project_task_stats(project)
    evidence, points = [], 0

    if stats['overdue']:
        evidence.append(f"{stats['overdue']} overdue task(s) out of {stats['total']}.")
        points += 2
    if stats['completion_rate'] is not None and stats['completion_rate'] < 0.5 and project.deadline:
        days_left = (project.deadline - date.today()).days
        if days_left <= 14:
            evidence.append(f"Only {round(stats['completion_rate']*100,1)}% complete with {days_left} day(s) until deadline.")
            points += 2

    if evidence:
        severity = 'CRITICAL' if points >= 4 else ('WARNING' if points >= 2 else 'WATCH')
        warnings.append({
            'signal_type': 'PROJECT_DELIVERY_PRESSURE', 'entity_type': 'project', 'entity_id': project.id,
            'entity_name': project.name, 'severity': severity, 'evidence': evidence,
            'source': 'RULE-BASED SIGNAL', 'disclaimer': DISCLAIMER,
            'whatif_scenario': 'PROJECT_MEMBERSHIP_CHANGE', 'whatif_params': {'project_id': project.id},
        })

    outcome_meta = get_model_metadata('project_outcome')
    if outcome_meta:
        pred = Prediction.objects.filter(project=project, prediction_type='PROJECT_OUTCOME').order_by('-prediction_date').first()
        if pred and pred.risk_level == 'High':
            warnings.append({
                'signal_type': 'ML_PROJECT_OUTCOME_FORECAST', 'entity_type': 'project', 'entity_id': project.id,
                'entity_name': project.name, 'severity': 'CRITICAL',
                'evidence': [f"Active model {pred.model_version} predicts '{pred.predicted_outcome}' with confidence {pred.confidence}."],
                'source': 'ML FORECAST', 'disclaimer': DISCLAIMER,
                'whatif_scenario': None, 'whatif_params': None,
            })
    return warnings


_SEVERITY_ORDER = {'CRITICAL': 0, 'WARNING': 1, 'WATCH': 2, 'INFO': 3}


def generate_early_warnings(employee=None, project=None):
    """
    - employee=<Employee>: warnings for just that employee (My Prevention)
    - project=<Project>: warnings for just that project
    - neither: full organization scan (Prevention Center)
    """
    if employee is not None:
        warnings = _employee_warnings(employee)
    elif project is not None:
        warnings = _project_warnings(project)
    else:
        warnings = []
        anomaly_summary = detect_workforce_anomalies()  # computed ONCE for the whole org scan
        for emp in Employee.objects.all():
            warnings.extend(_employee_warnings(emp, anomaly_summary=anomaly_summary))
        for proj in Project.objects.exclude(status__in=["Completed", "Cancelled"]):
            warnings.extend(_project_warnings(proj))

    warnings.sort(key=lambda w: _SEVERITY_ORDER.get(w['severity'], 4))
    return warnings
