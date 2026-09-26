"""
What-If Decision Simulator (Prompt 5)
========================================
A reusable simulation engine that projects the OPERATIONAL effect of a
hypothetical change using REAL current database values, and — only where
an ACTIVE persisted ML model exists — asks that SAME model (via
prediction_service.load_model/prepare_features; never a retrain, never a
new formula) what it would predict under the hypothetical feature values.

Status labels used throughout, never blurred together:
  REAL DATA         -> read straight from the database, unchanged
  SIMULATED DATA    -> a real DB value with a stated, deterministic
                       arithmetic change applied (e.g. team_size - 1)
  MODEL_NOT_READY   -> no active ModelVersion exists for this prediction
                       type; the operational (non-ML) analysis is still
                       returned in full
  INSUFFICIENT_DATA -> an active model exists but this specific entity
                       lacks the history needed to build its features

Reuses, never duplicates:
  - Employee/ml/workforce_digital_twin.py  (_employee_task_stats, _project_task_stats)
  - Employee/ml/prediction_service.py      (load_model, prepare_features,
                                             get_model_metadata, whatif_project_outcome)
  - Employee/ml/feature_engineering.py     (build_employee_risk_features)
"""
from datetime import date

from Employee.models import Employee, Project, ProjectMember, Task
from .workforce_digital_twin import _employee_task_stats, _project_task_stats
from .prediction_service import load_model, prepare_features, get_model_metadata, whatif_project_outcome
from .feature_engineering import build_employee_risk_features


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _pct_change(before, after):
    """Real math only. None where a percentage is not mathematically valid
    (before is 0/None) — never a divide-by-zero guess."""
    if before in (None, 0) or after is None:
        return None
    return round(((after - before) / before) * 100, 1)


def _diff(before, after):
    if before is None or after is None:
        return None
    return round(after - before, 3)


def _name(employee):
    return employee.user.first_name if employee and employee.user else (employee.empid if employee else None)


def _whatif_employee_risk(employee, override_features):
    """Mirrors whatif_project_outcome()'s exact pattern for employee_risk —
    reuses load_model/prepare_features, never a new scoring formula."""
    pipeline, feature_columns, mv = load_model('employee_risk')
    if pipeline is None:
        return {'status': 'MODEL_NOT_READY', 'message': 'No active employee_risk model.'}

    base_features = build_employee_risk_features(employee)
    if base_features is None:
        return {'status': 'INSUFFICIENT_DATA',
                'message': 'Employee has no PerformanceHistory/WorkloadHistory to build a baseline from.'}

    base_features.update(override_features)
    X = prepare_features(base_features, feature_columns)
    prediction = pipeline.predict(X)[0]
    proba = pipeline.predict_proba(X)[0]
    class_labels = list(pipeline.named_steps['clf'].classes_)
    prob_dict = {label: round(float(p), 3) for label, p in zip(class_labels, proba)}
    return {
        'status': 'OK',
        'predicted_outcome': prediction,
        'probabilities': prob_dict,
        'used_features': base_features,
        'model_version': mv.version,
    }


def _project_risk_impact(project, current_override, simulated_override):
    metadata = get_model_metadata('project_outcome')
    if not metadata:
        return {'status': 'MODEL_NOT_READY', 'active_model': None}
    current_result = whatif_project_outcome(project, current_override)
    simulated_result = whatif_project_outcome(project, simulated_override)
    ok = current_result.get('status') == 'ok' and simulated_result.get('status') == 'ok'
    return {
        'status': 'OK' if ok else 'MODEL_NOT_READY',
        'active_model': metadata,
        'current_prediction': current_result,
        'simulated_prediction': simulated_result,
    }


def _employee_risk_impact(employee, current_override, simulated_override):
    metadata = get_model_metadata('employee_risk')
    if not metadata:
        return {'status': 'MODEL_NOT_READY', 'active_model': None}
    current_result = _whatif_employee_risk(employee, current_override)
    simulated_result = _whatif_employee_risk(employee, simulated_override)
    if current_result.get('status') == 'OK' and simulated_result.get('status') == 'OK':
        status = 'OK'
    else:
        status = current_result.get('status', 'MODEL_NOT_READY')
    return {
        'status': status,
        'active_model': metadata,
        'current_prediction': current_result,
        'simulated_prediction': simulated_result,
    }


def _task_is_overdue(task):
    if task.status == "Completed" or not task.endDate:
        return False
    try:
        return task.endDate.date() < date.today()
    except AttributeError:
        return task.endDate < date.today()


def _base_result(scenario_type, description):
    return {
        'scenario_type': scenario_type,
        'description': description,
        'current_state': {},
        'simulated_state': {},
        'absolute_difference': {},
        'percentage_difference': {},
        'affected_employees': [],
        'affected_projects': [],
        'affected_tasks': [],
        'workload_impact': {},
        'performance_impact': {'status': 'REAL DATA'},
        'risk_impact': {'status': 'MODEL_NOT_READY'},
        'warnings': [],
        'recommendations': [],
        'explanation': [],
    }


# ---------------------------------------------------------------------------
# A. Employee reassignment — Project A -> Project B
# ---------------------------------------------------------------------------

def simulate_employee_reassignment(employee_id, from_project_id, to_project_id):
    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return {'error': 'employee_not_found', 'employee_id': employee_id}
    try:
        from_project = Project.objects.get(id=from_project_id)
    except Project.DoesNotExist:
        return {'error': 'project_not_found', 'project_id': from_project_id}
    try:
        to_project = Project.objects.get(id=to_project_id)
    except Project.DoesNotExist:
        return {'error': 'project_not_found', 'project_id': to_project_id}
    if from_project_id == to_project_id:
        return {'error': 'invalid_scenario', 'message': 'from_project and to_project must differ.'}

    result = _base_result(
        'EMPLOYEE_REASSIGNMENT',
        f"Move {_name(employee)} from \"{from_project.name}\" to \"{to_project.name}\".",
    )

    is_member_from = ProjectMember.objects.filter(employee=employee, project=from_project, is_active=True).exists()
    is_member_to = ProjectMember.objects.filter(employee=employee, project=to_project, is_active=True).exists()
    if not is_member_from:
        result['warnings'].append(f"{employee.empid} is not currently an active member of \"{from_project.name}\".")
    if is_member_to:
        result['warnings'].append(f"{employee.empid} is already an active member of \"{to_project.name}\".")

    from_team = ProjectMember.objects.filter(project=from_project, is_active=True).count()
    to_team = ProjectMember.objects.filter(project=to_project, is_active=True).count()
    emp_stats = _employee_task_stats(employee)
    emp_open_tasks_from = Task.objects.filter(project=from_project, emp=employee).exclude(status="Completed")

    sim_from_team = max(from_team - 1, 0) if is_member_from else from_team
    sim_to_team = to_team + 1 if not is_member_to else to_team

    result['current_state'] = {
        'from_project': {'name': from_project.name, 'team_size': from_team, 'task_stats': _project_task_stats(from_project)},
        'to_project': {'name': to_project.name, 'team_size': to_team, 'task_stats': _project_task_stats(to_project)},
        'employee_workload': emp_stats,
    }
    result['simulated_state'] = {
        'from_project': {'team_size': sim_from_team},
        'to_project': {'team_size': sim_to_team},
    }
    result['absolute_difference'] = {
        'from_project_team_size': _diff(from_team, sim_from_team),
        'to_project_team_size': _diff(to_team, sim_to_team),
    }
    result['percentage_difference'] = {
        'from_project_team_size_pct': _pct_change(from_team, sim_from_team),
        'to_project_team_size_pct': _pct_change(to_team, sim_to_team),
    }
    result['affected_employees'] = [{'employee_id': employee.id, 'name': _name(employee)}]
    result['affected_projects'] = [
        {'project_id': from_project.id, 'name': from_project.name, 'change': 'loses member'},
        {'project_id': to_project.id, 'name': to_project.name, 'change': 'gains member'},
    ]
    if emp_open_tasks_from.exists():
        result['affected_tasks'] = list(emp_open_tasks_from.values('id', 'title', 'status'))
        result['warnings'].append(
            f"{employee.empid} has {emp_open_tasks_from.count()} open task(s) still tied to \"{from_project.name}\" — "
            f"moving project membership does NOT automatically reassign those Task records in this schema."
        )
        result['recommendations'].append(
            f"Reassign or close {employee.empid}'s open task(s) on \"{from_project.name}\" before moving them."
        )

    result['workload_impact'] = {
        'from_project_team_size': {'before': from_team, 'after': sim_from_team, 'label': 'SIMULATED DATA'},
        'to_project_team_size': {'before': to_team, 'after': sim_to_team, 'label': 'SIMULATED DATA'},
        'employee_current_task_load': {'value': emp_stats, 'label': 'REAL DATA'},
    }
    result['risk_impact'] = {
        'from_project': _project_risk_impact(from_project, {'team_size': from_team}, {'team_size': sim_from_team}),
        'to_project': _project_risk_impact(to_project, {'team_size': to_team}, {'team_size': sim_to_team}),
    }

    result['explanation'] = [
        (f"\"{from_project.name}\" loses one assigned employee, reducing its active team from {from_team} to {sim_from_team}."
         if is_member_from else f"{employee.empid} was not an active member of \"{from_project.name}\", so its team size is unaffected."),
        (f"\"{to_project.name}\" gains one assigned employee, increasing its active team from {to_team} to {sim_to_team}."
         if not is_member_to else f"{employee.empid} is already on \"{to_project.name}\", so its team size is unaffected."),
    ]
    if emp_stats['overdue']:
        result['explanation'].append(
            f"{employee.empid} currently has {emp_stats['overdue']} overdue task(s) — these follow the employee regardless of project reassignment."
        )
    if sim_from_team == 0:
        result['recommendations'].append(f"\"{from_project.name}\" would have zero active team members after this move.")

    return result


# ---------------------------------------------------------------------------
# B. Task reassignment — Employee A -> Employee B
# ---------------------------------------------------------------------------

def simulate_task_reassignment(task_id, to_employee_id):
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return {'error': 'task_not_found', 'task_id': task_id}
    try:
        to_employee = Employee.objects.get(id=to_employee_id)
    except Employee.DoesNotExist:
        return {'error': 'employee_not_found', 'employee_id': to_employee_id}

    from_employee = task.emp
    if from_employee and from_employee.id == to_employee_id:
        return {'error': 'invalid_scenario', 'message': 'Task is already assigned to this employee.'}

    result = _base_result(
        'TASK_REASSIGNMENT',
        f"Reassign task \"{task.title}\" from {_name(from_employee) or 'Unassigned'} to {_name(to_employee)}.",
    )

    from_stats = _employee_task_stats(from_employee) if from_employee else None
    to_stats = _employee_task_stats(to_employee)
    is_overdue = _task_is_overdue(task)
    task_completed = task.status == "Completed"

    def _simulate(stats, d_assigned, d_completed, d_overdue):
        if stats is None:
            return None
        assigned = max(stats['assigned'] + d_assigned, 0)
        completed = max(stats['completed'] + d_completed, 0)
        overdue = max(stats['overdue'] + d_overdue, 0)
        pending = max(assigned - completed, 0)
        return {
            'assigned': assigned, 'completed': completed, 'pending': pending, 'overdue': overdue,
            'completion_rate': round(completed / assigned, 3) if assigned else None,
            'overdue_ratio': round(overdue / assigned, 3) if assigned else None,
        }

    sim_from_stats = _simulate(from_stats, -1, -1 if task_completed else 0, -1 if is_overdue else 0)
    sim_to_stats = _simulate(to_stats, +1, +1 if task_completed else 0, +1 if is_overdue else 0)

    result['current_state'] = {
        'from_employee_workload': from_stats, 'to_employee_workload': to_stats,
        'task': {'id': task.id, 'title': task.title, 'status': task.status, 'is_overdue': is_overdue},
    }
    result['simulated_state'] = {'from_employee_workload': sim_from_stats, 'to_employee_workload': sim_to_stats}
    result['absolute_difference'] = {
        'from_employee_assigned': _diff(from_stats['assigned'], sim_from_stats['assigned']) if from_stats else None,
        'to_employee_assigned': _diff(to_stats['assigned'], sim_to_stats['assigned']),
    }
    result['percentage_difference'] = {
        'from_employee_assigned_pct': _pct_change(from_stats['assigned'], sim_from_stats['assigned']) if from_stats else None,
        'to_employee_assigned_pct': _pct_change(to_stats['assigned'], sim_to_stats['assigned']),
    }
    result['affected_employees'] = [e for e in [
        {'employee_id': from_employee.id, 'name': _name(from_employee)} if from_employee else None,
        {'employee_id': to_employee.id, 'name': _name(to_employee)},
    ] if e]
    result['affected_tasks'] = [{'task_id': task.id, 'title': task.title, 'status': task.status}]
    result['affected_projects'] = [{'project_id': task.project.id, 'name': task.project.name}] if task.project else []

    result['workload_impact'] = {
        'from_employee': ({'before': from_stats, 'after': sim_from_stats, 'label': 'SIMULATED DATA'}
                           if from_stats else {'label': 'REAL DATA', 'note': 'Task was unassigned.'}),
        'to_employee': {'before': to_stats, 'after': sim_to_stats, 'label': 'SIMULATED DATA'},
    }

    result['explanation'] = [
        f"\"{task.title}\" moves to {to_employee.empid}, increasing their assigned task count from {to_stats['assigned']} to {sim_to_stats['assigned']}.",
    ]
    if from_stats:
        result['explanation'].append(
            f"{from_employee.empid}'s assigned task count decreases from {from_stats['assigned']} to {sim_from_stats['assigned']}."
        )
    if is_overdue:
        result['explanation'].append(
            f"This task is currently overdue — it will count toward {to_employee.empid}'s overdue total after reassignment."
        )

    if sim_to_stats['overdue_ratio'] is not None and to_stats['overdue_ratio'] is not None \
            and sim_to_stats['overdue_ratio'] > to_stats['overdue_ratio']:
        result['warnings'].append(f"{to_employee.empid}'s overdue ratio would increase after taking on this task.")
    if to_stats['assigned'] >= 5:
        result['warnings'].append(f"{to_employee.empid} already has {to_stats['assigned']} assigned task(s) — this adds to an already high load.")
    if from_stats and from_stats['assigned'] > 0 and sim_from_stats['assigned'] == 0:
        result['recommendations'].append(f"{from_employee.empid} would have zero remaining assigned tasks after this change.")

    result['risk_impact'] = {
        'to_employee': _employee_risk_impact(
            to_employee, {},
            {'pending_count': (to_stats['pending'] or 0) + (0 if task_completed else 1)},
        ),
    }
    if from_employee:
        result['risk_impact']['from_employee'] = _employee_risk_impact(
            from_employee, {},
            {'pending_count': max((from_stats['pending'] or 0) - (0 if task_completed else 1), 0)},
        )

    return result


# ---------------------------------------------------------------------------
# C. Workload scenario — increase/decrease workload for an employee or project
# ---------------------------------------------------------------------------

def simulate_workload_scenario(entity_type, entity_id, delta_tasks):
    if entity_type not in ('employee', 'project'):
        return {'error': 'invalid_entity_type', 'entity_type': entity_type}

    if entity_type == 'employee':
        try:
            employee = Employee.objects.get(id=entity_id)
        except Employee.DoesNotExist:
            return {'error': 'employee_not_found', 'employee_id': entity_id}
        current = _employee_task_stats(employee)
        label = _name(employee)
    else:
        try:
            project = Project.objects.get(id=entity_id)
        except Project.DoesNotExist:
            return {'error': 'project_not_found', 'project_id': entity_id}
        stats = _project_task_stats(project)
        current = {'assigned': stats['total'], 'completed': stats['completed'], 'pending': stats['pending'],
                   'overdue': stats['overdue'], 'completion_rate': stats['completion_rate'], 'overdue_ratio': stats['overdue_ratio']}
        label = project.name

    result = _base_result(
        'WORKLOAD_SCENARIO',
        f"{'Increase' if delta_tasks >= 0 else 'Decrease'} workload for {entity_type} \"{label}\" by {abs(delta_tasks)} task(s).",
    )

    new_assigned = max(current['assigned'] + delta_tasks, 0)
    projected_overdue_ratio = current['overdue_ratio'] if current['overdue_ratio'] is not None else 0
    projected_overdue = round(new_assigned * projected_overdue_ratio)
    new_pending = max(new_assigned - current['completed'], 0)
    simulated = {
        'assigned': new_assigned, 'completed': current['completed'], 'pending': new_pending,
        'overdue': projected_overdue,
        'completion_rate': round(current['completed'] / new_assigned, 3) if new_assigned else None,
        'overdue_ratio': projected_overdue_ratio,
    }

    result['current_state'] = {'entity_type': entity_type, 'entity': label, 'stats': current}
    result['simulated_state'] = {'stats': simulated}
    result['absolute_difference'] = {'assigned': _diff(current['assigned'], new_assigned), 'pending': _diff(current['pending'], new_pending)}
    result['percentage_difference'] = {'assigned_pct': _pct_change(current['assigned'], new_assigned)}
    result['workload_impact'] = {
        'assigned': {'before': current['assigned'], 'after': new_assigned, 'label': 'SIMULATED DATA'},
        'assumption': 'Overdue ratio is projected to hold at its current real value — a stated planning '
                       'assumption, not a model prediction.',
    }

    if entity_type == 'employee':
        result['affected_employees'] = [{'employee_id': employee.id, 'name': label}]
        result['risk_impact'] = {'employee': _employee_risk_impact(
            employee, {}, {'pending_count': new_pending, 'overdue_count': projected_overdue})}
    else:
        result['affected_projects'] = [{'project_id': project.id, 'name': label}]
        result['risk_impact'] = {'project': _project_risk_impact(project, {}, {})}

    result['explanation'] = [
        f"Assigned task count moves from {current['assigned']} to {new_assigned} ({'+' if delta_tasks >= 0 else ''}{delta_tasks}).",
        f"Projected overdue count assumes the current overdue ratio ({round(projected_overdue_ratio * 100, 1)}%) holds.",
    ]
    if new_assigned > current['assigned'] and current['overdue_ratio'] and current['overdue_ratio'] > 0.3:
        result['warnings'].append(f"Overdue ratio is already {round(current['overdue_ratio'] * 100, 1)}% — adding more workload compounds an existing risk.")

    return result


# ---------------------------------------------------------------------------
# D. Project scenario — add/remove an employee from a project
# ---------------------------------------------------------------------------

def simulate_project_membership_change(project_id, employee_id, action):
    if action not in ('add', 'remove'):
        return {'error': 'invalid_action', 'action': action}
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {'error': 'project_not_found', 'project_id': project_id}
    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return {'error': 'employee_not_found', 'employee_id': employee_id}

    is_member = ProjectMember.objects.filter(project=project, employee=employee, is_active=True).exists()
    if action == 'add' and is_member:
        return {'error': 'invalid_scenario', 'message': f'{employee.empid} is already an active member of {project.name}.'}
    if action == 'remove' and not is_member:
        return {'error': 'invalid_scenario', 'message': f'{employee.empid} is not currently an active member of {project.name}.'}

    result = _base_result(
        'PROJECT_MEMBERSHIP_CHANGE',
        f"{'Add' if action == 'add' else 'Remove'} {employee.empid} {'to' if action == 'add' else 'from'} \"{project.name}\".",
    )

    team_size = ProjectMember.objects.filter(project=project, is_active=True).count()
    sim_team_size = team_size + 1 if action == 'add' else max(team_size - 1, 0)
    task_stats = _project_task_stats(project)
    emp_stats = _employee_task_stats(employee)

    result['current_state'] = {'project_team_size': team_size, 'project_task_stats': task_stats, 'employee_workload': emp_stats}
    result['simulated_state'] = {'project_team_size': sim_team_size}
    result['absolute_difference'] = {'team_size': _diff(team_size, sim_team_size)}
    result['percentage_difference'] = {'team_size_pct': _pct_change(team_size, sim_team_size)}
    result['affected_employees'] = [{'employee_id': employee.id, 'name': _name(employee)}]
    result['affected_projects'] = [{'project_id': project.id, 'name': project.name}]
    result['workload_impact'] = {
        'project_team_size': {'before': team_size, 'after': sim_team_size, 'label': 'SIMULATED DATA'},
        'per_member_task_load_est': {
            'before': round(task_stats['total'] / team_size, 2) if team_size else None,
            'after': round(task_stats['total'] / sim_team_size, 2) if sim_team_size else None,
            'label': 'SIMULATED DATA',
            'note': 'Even-distribution estimate for illustration only — actual task assignment is manual.',
        },
    }
    result['risk_impact'] = {'project': _project_risk_impact(project, {'team_size': team_size}, {'team_size': sim_team_size})}

    if action == 'remove':
        proj_open_tasks = Task.objects.filter(project=project, emp=employee).exclude(status="Completed")
        if proj_open_tasks.exists():
            result['affected_tasks'] = list(proj_open_tasks.values('id', 'title', 'status'))
            result['warnings'].append(f"{employee.empid} has {proj_open_tasks.count()} open task(s) on \"{project.name}\" that would need reassignment.")

    result['explanation'] = [f"\"{project.name}\"'s active team size moves from {team_size} to {sim_team_size}."]
    if sim_team_size == 0:
        result['recommendations'].append(f"\"{project.name}\" would have zero active team members — high risk of stalling.")

    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

SCENARIO_DISPATCH = {
    'EMPLOYEE_REASSIGNMENT': lambda p: simulate_employee_reassignment(
        int(p['employee_id']), int(p['from_project_id']), int(p['to_project_id'])),
    'TASK_REASSIGNMENT': lambda p: simulate_task_reassignment(
        int(p['task_id']), int(p['to_employee_id'])),
    'WORKLOAD_SCENARIO': lambda p: simulate_workload_scenario(
        p['entity_type'], int(p['entity_id']), int(p['delta_tasks'])),
    'PROJECT_MEMBERSHIP_CHANGE': lambda p: simulate_project_membership_change(
        int(p['project_id']), int(p['employee_id']), p['action']),
}


def run_simulation(scenario_type, params):
    """Single entry point used by the API view. Validates the scenario
    type and required parameters before dispatching; never lets a bad
    request reach the database layer as a raw exception."""
    handler = SCENARIO_DISPATCH.get(scenario_type)
    if not handler:
        return {'error': 'unknown_scenario_type', 'scenario_type': scenario_type,
                'supported': list(SCENARIO_DISPATCH.keys())}
    try:
        return handler(params)
    except KeyError as e:
        return {'error': 'missing_parameter', 'missing': str(e)}
    except (TypeError, ValueError) as e:
        return {'error': 'invalid_parameter', 'message': str(e)}
