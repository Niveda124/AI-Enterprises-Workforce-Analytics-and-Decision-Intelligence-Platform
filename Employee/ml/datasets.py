from Employee.models import Project, PerformanceHistory, WorkloadHistory
from .feature_engineering import (
    build_project_features,
    build_employee_performance_features,
)


def build_project_outcome_dataset():
    """
    REAL_ML dataset. Target derived only from real, already-stored
    Project.status values: Completed -> Success, Cancelled -> Failure Risk.
    Projects still Planning/Active/On Hold have no resolved outcome and
    are excluded (their true label is unknown, not zero-risk).
    No feature here is generated after the outcome is known — all features
    come from current task/team state, available at prediction time too.
    """
    rows, labels = [], []
    for p in Project.objects.filter(status="Completed"):
        rows.append(build_project_features(p))
        labels.append("Success")
    for p in Project.objects.filter(status="Cancelled"):
        rows.append(build_project_features(p))
        labels.append("Failure Risk")
    return rows, labels


def build_employee_performance_dataset():
    """
    REAL_ML dataset, leakage-corrected (Prompt 4), same temporal pattern as
    the Prompt 1 employee_risk fix.

    FEATURE PERIOD: T   -> tasks_assigned, tasks_completed, tasks_overdue,
                            completion_rate, on_time_rate, avg_delay_days,
                            workload_score  (from PerformanceHistory at T)
    TARGET PERIOD:  T+1 -> performance_score bucketed High/>=75, Medium/>=40,
                            Low/<40  (from PerformanceHistory at T+1)

    Period T's own performance_score is NEVER used as a feature — only
    period T's task/workload counts, which do not by themselves reveal T's
    own bucket the way they trivially reveal it for the SAME period. This
    does not eliminate every leakage concern (T's completion_rate is still
    likely correlated with T's own performance, and T and T+1 buckets may
    correlate simply because behavior is often consistent period-to-period)
    but it removes the direct arithmetic construction of the label from its
    same-period inputs. Only genuine, already-recorded consecutive periods
    are used; no synthetic periods are created here.
    """
    from Employee.models import Employee

    rows, labels = [], []
    for emp in Employee.objects.all():
        perf_records = list(PerformanceHistory.objects.filter(employee=emp).order_by('period'))
        for i in range(len(perf_records) - 1):
            current = perf_records[i]
            next_perf = perf_records[i + 1]

            rows.append(build_employee_performance_features(current))

            if next_perf.performance_score >= 75:
                labels.append("High")
            elif next_perf.performance_score >= 40:
                labels.append("Medium")
            else:
                labels.append("Low")
    return rows, labels


def build_employee_risk_dataset():
    """
    REAL_ML dataset — temporal design to avoid target leakage.

    LEAKAGE FOUND (corrected here): the previous version used period t's
    WorkloadHistory.overdue_count as BOTH a feature and the direct basis of
    that same period's label (label = overdue_count / assigned_count for
    period t). That made the label a near-deterministic function of an
    input feature, inflating held-out metrics without genuine predictive
    signal.

    FIX: features are now drawn from an employee's period t, while the
    label is drawn from that SAME employee's period t+1 — i.e. current/past
    workload and performance data predicting a later, not-yet-observed
    overdue outcome. This uses only real, already-recorded PerformanceHistory/
    WorkloadHistory pairs; no synthetic periods are invented, and employees
    with fewer than 2 recorded periods contribute no rows (there is no
    "next period" to label from).
    """
    from Employee.models import Employee

    rows, labels = [], []
    for emp in Employee.objects.all():
        perf_records = list(PerformanceHistory.objects.filter(employee=emp).order_by('period'))
        for i in range(len(perf_records) - 1):
            current = perf_records[i]
            next_perf = perf_records[i + 1]

            current_load = WorkloadHistory.objects.filter(employee=emp, period=current.period).first()
            next_load = WorkloadHistory.objects.filter(employee=emp, period=next_perf.period).first()
            if not current_load or not next_load:
                continue

            rows.append({
                'completion_rate': current.completion_rate,
                'on_time_rate': current.on_time_rate,
                'avg_delay_days': current.avg_delay_days,
                'tasks_overdue': current.tasks_overdue,
                'workload_score': current_load.workload_score,
                'pending_count': current_load.pending_count,
                'overdue_count': current_load.overdue_count,
            })

            ratio = (next_load.overdue_count / next_load.assigned_count) if next_load.assigned_count else 0
            if ratio >= 0.5:
                labels.append("High")
            elif ratio >= 0.2:
                labels.append("Medium")
            else:
                labels.append("Low")
    return rows, labels

def build_workload_forecast_dataset():
    """
    Machine-learning regression dataset for workload forecasting, trained
    and evaluated using historically recorded WorkloadHistory data available
    in the system. This project's WorkloadHistory records are synthetic/demo
    data generated by seed_ai_data.py, not independently observed real-world
    company history — disclosed here per academic transparency requirement.

    FEATURE PERIOD: T (and T-1 where available, as a lag feature)
    TARGET PERIOD:  T+1 -> workload_score (regression target, continuous)

    Only genuine, already-recorded consecutive periods are used per
    employee, ordered chronologically by the real `period` DateField
    (not auto_now). No synthetic periods are created here. Employees with
    fewer than 2 recorded periods contribute no rows.

    Returns a list of (feature_dict, target_value, target_period) tuples so
    callers can perform a genuine chronological train/test split (sorted by
    target_period) instead of a random split, which would otherwise mix
    future and past observations across employees.
    """
    from Employee.models import Employee, WorkloadHistory

    records = []
    for emp in Employee.objects.all():
        history = list(WorkloadHistory.objects.filter(employee=emp).order_by('period'))
        for i in range(len(history) - 1):
            current = history[i]
            next_period = history[i + 1]
            prev = history[i - 1] if i >= 1 else None

            feature_row = {
                'assigned_count': current.assigned_count,
                'completed_count': current.completed_count,
                'pending_count': current.pending_count,
                'overdue_count': current.overdue_count,
                'workload_score': current.workload_score,
                'prev_workload_score': prev.workload_score if prev else current.workload_score,
                'prev_assigned_count': prev.assigned_count if prev else current.assigned_count,
            }
            records.append((feature_row, next_period.workload_score, next_period.period))

    return records