from datetime import date
from Employee.models import Task, ProjectMember


def build_project_features(project):
    """
    Leakage-safe project feature set (Prompt 2 correction).

    REMOVED vs. the earlier version: total_tasks, completed_tasks,
    pending_tasks, overdue_tasks, completion_rate, overdue_rate, progress.
    These were read from Task.objects.filter(project=project) with NO status
    filter — meaning for an already-resolved (Completed/Cancelled) project
    they reflect the FINAL task state, computed AFTER the outcome was known,
    not a mid-project snapshot. No historical task-count snapshot exists in
    this schema (no dated TaskSnapshot table), so an early/mid-project
    completion or overdue rate cannot be honestly reconstructed — only
    "current state" is available, and for resolved projects "current state"
    IS the aftermath of the label. Using it would mean the model partly
    predicts the outcome from evidence of the outcome having already
    happened. Same reasoning for `progress`: it is admin-entered and, per
    audit, is set to 100 at/near the same time status becomes "Completed",
    making it a near-restatement of the label rather than an independent
    signal.

    KEPT / USED instead — genuinely knowable at a meaningful prediction
    point (project start, or "today" for an in-flight project), independent
    of how tasks were later executed:
      - team_size: current active roster size (a staffing/planning fact)
      - priority_encoded: set at project creation, not outcome-dependent
      - planned_duration_days: deadline - start_date, fixed at planning time
      - elapsed_duration_days: time since start_date, a scheduling fact
      - elapsed_fraction: elapsed / planned duration (0 if planned <= 0)
      - days_remaining: deadline - today, a scheduling fact

    FURTHER REMOVED (second correction): high_priority_tasks. Although task
    priority itself is not an outcome label, this count is read from
    CURRENT Task records with no creation-time or historical snapshot tied
    to a specific prediction point. Tasks may have been added after project
    start, or after the outcome became apparent, so "current high-priority
    task count" can still mismatch between training time (resolved project,
    task list frozen at whatever point tasks stopped being added) and
    inference time (an in-flight project, task list still growing). Removed
    entirely rather than kept as a "weaker" signal, per correction.

    LIMITATION (documented, not worked around): without a dated task-history
    table, no task-derived feature can be safely included at all under this
    schema. The final feature set is therefore project-level scheduling/
    staffing facts only (team size, priority, planned/elapsed duration,
    days remaining) — genuinely knowable at a meaningful prediction point,
    with zero task-count-derived signal.
    """
    team_size = ProjectMember.objects.filter(project=project, is_active=True).count()

    planned_duration_days = None
    if project.start_date and project.deadline:
        planned_duration_days = (project.deadline - project.start_date).days

    elapsed_duration_days = None
    if project.start_date:
        elapsed_duration_days = (date.today() - project.start_date).days

    elapsed_fraction = 0
    if planned_duration_days and planned_duration_days > 0 and elapsed_duration_days is not None:
        elapsed_fraction = round(elapsed_duration_days / planned_duration_days, 3)

    days_remaining = None
    if project.deadline:
        days_remaining = (project.deadline - date.today()).days

    return {
        'team_size': team_size,
        'priority_encoded': {'Low': 0, 'Medium': 1, 'High': 2, 'Critical': 3}.get(project.priority, 1),
        'planned_duration_days': planned_duration_days if planned_duration_days is not None else 0,
        'elapsed_duration_days': elapsed_duration_days if elapsed_duration_days is not None else 0,
        'elapsed_fraction': elapsed_fraction,
        'days_remaining': days_remaining if days_remaining is not None else 0,
    }


def build_employee_performance_features(perf_record):
    return {
        'tasks_assigned': perf_record.tasks_assigned,
        'tasks_completed': perf_record.tasks_completed,
        'tasks_overdue': perf_record.tasks_overdue,
        'completion_rate': perf_record.completion_rate,
        'on_time_rate': perf_record.on_time_rate,
        'avg_delay_days': perf_record.avg_delay_days,
        'workload_score': perf_record.workload_score,
    }


def build_employee_risk_features(employee):
    from Employee.models import PerformanceHistory, WorkloadHistory
    perf = PerformanceHistory.objects.filter(employee=employee).order_by('-period').first()
    load = WorkloadHistory.objects.filter(employee=employee).order_by('-period').first()

    if not perf or not load:
        return None

    return {
        'completion_rate': perf.completion_rate,
        'on_time_rate': perf.on_time_rate,
        'avg_delay_days': perf.avg_delay_days,
        'tasks_overdue': perf.tasks_overdue,
        'workload_score': load.workload_score,
        'pending_count': load.pending_count,
        'overdue_count': load.overdue_count,
    }