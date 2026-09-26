"""
Anomaly Detection (Prompt 4)
=============================
Detects employees whose CURRENT performance/workload snapshot is a
statistical outlier relative to the rest of the current workforce, using
scikit-learn's IsolationForest — a real unsupervised model, not a
rule-based score dressed up as "AI".

Never fabricates an anomaly: if there isn't enough data to fit a
meaningful model, this returns an explicit INSUFFICIENT_DATA state,
exactly like the supervised models in train_models.py do — no lowering
of that bar to force a result.
"""
import numpy as np
from sklearn.ensemble import IsolationForest

from Employee.models import Employee, PerformanceHistory, WorkloadHistory

# Consistent with validate_regression_dataset()'s min_rows=10 convention
# elsewhere in this project — an IsolationForest fit on fewer points than
# this is not a meaningful model, so we refuse rather than fake a result.
MIN_EMPLOYEES_FOR_ANOMALY_DETECTION = 10

FEATURE_NAMES = [
    'completion_rate', 'on_time_rate', 'avg_delay_days', 'perf_workload_score',
    'performance_score', 'pending_count', 'overdue_count', 'load_workload_score',
]


def _latest_snapshot(employee):
    """
    One real feature row for an employee, from their MOST RECENT
    PerformanceHistory + WorkloadHistory record. Returns None (not a
    guessed/zero-filled row) if either history is missing.
    """
    perf = PerformanceHistory.objects.filter(employee=employee).order_by('-period').first()
    load = WorkloadHistory.objects.filter(employee=employee).order_by('-period').first()
    if not perf or not load:
        return None
    return {
        'completion_rate': perf.completion_rate,
        'on_time_rate': perf.on_time_rate,
        'avg_delay_days': perf.avg_delay_days,
        'perf_workload_score': perf.workload_score,
        'performance_score': perf.performance_score,
        'pending_count': load.pending_count,
        'overdue_count': load.overdue_count,
        'load_workload_score': load.workload_score,
    }


def detect_workforce_anomalies(contamination='auto'):
    """
    Fits IsolationForest across every employee's CURRENT snapshot and
    flags statistical outliers.

    Returns either:
      {'status': 'OK', 'evaluated_count': N, 'anomaly_count': K, 'anomalies': [...]}
    or:
      {'status': 'INSUFFICIENT_DATA', 'reason': ..., 'evaluated_count': N}
    """
    rows, employees = [], []
    for emp in Employee.objects.all():
        snap = _latest_snapshot(emp)
        if snap:
            rows.append([snap[f] for f in FEATURE_NAMES])
            employees.append((emp, snap))

    if len(rows) < MIN_EMPLOYEES_FOR_ANOMALY_DETECTION:
        return {
            'status': 'INSUFFICIENT_DATA',
            'reason': (
                f'Only {len(rows)} employee(s) currently have both a PerformanceHistory '
                f'and a WorkloadHistory record; at least {MIN_EMPLOYEES_FOR_ANOMALY_DETECTION} '
                f'are needed to fit a meaningful IsolationForest model.'
            ),
            'evaluated_count': len(rows),
        }

    X = np.array(rows, dtype=float)
    model = IsolationForest(contamination=contamination, random_state=42)
    model.fit(X)
    predictions = model.predict(X)        # -1 = anomaly, 1 = normal
    scores = model.decision_function(X)   # lower/negative = more anomalous

    anomalies = []
    for (emp, snap), pred, score in zip(employees, predictions, scores):
        if pred == -1:
            anomalies.append({
                'employee_id': emp.id,
                'name': emp.user.first_name if emp.user else emp.empid,
                'anomaly_score': round(float(score), 4),
                'snapshot': snap,
            })
    anomalies.sort(key=lambda a: a['anomaly_score'])  # most anomalous first

    return {
        'status': 'OK',
        'algorithm': 'IsolationForest',
        'contamination': contamination,
        'evaluated_count': len(rows),
        'anomaly_count': len(anomalies),
        'anomalies': anomalies,
    }


def get_employee_anomaly_status(employee_id):
    """Convenience wrapper: is THIS employee flagged, in the context of the
    current workforce-wide run? Re-fits on every call (cheap at this data
    volume, and always reflects current data — same pattern as the
    dept_workload rollup already computed fresh on each admin page load)."""
    result = detect_workforce_anomalies()
    if result['status'] != 'OK':
        return result
    for a in result['anomalies']:
        if a['employee_id'] == employee_id:
            return {'status': 'OK', 'is_anomaly': True, **a}
    return {'status': 'OK', 'is_anomaly': False, 'employee_id': employee_id}
