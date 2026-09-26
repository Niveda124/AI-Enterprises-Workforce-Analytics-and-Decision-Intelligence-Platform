"""
Organizational Brain (Prompt 11)
===================================
A composition/query layer over EXISTING records — no new "decision" or
"intervention" table was created. Per the prompt's explicit instruction
("the objective is organizational memory, not model proliferation"),
this module normalizes what already exists into a traceable memory:

  Decisions      -> AIRecommendation status changes + WorkforceInteraction
                    admin responses (both already ARE admin decisions,
                    just not previously labeled as such)
  Interventions  -> WorkforceEvent rows caused by an admin actor
                    (is_staff=True) — a real action, never a simulation
  Simulations    -> WhatIfScenario (never conflated with an intervention)
  Predictions    -> Prediction + Prediction.actual_outcome (both currently
                    real-but-mostly-empty — see Part 8: actual_outcome has
                    never been populated anywhere in this app, so the
                    outcome-evaluation functions here honestly return
                    INSUFFICIENT_OUTCOME_DATA rather than inventing rows)

Every function returns plain dicts/lists built directly from queries —
nothing here fabricates a decision, an outcome, a timestamp, or a causal
claim. Where evidence is thin, the functions say so explicitly.
"""
import json
import ast

from django.db.models import Count

from Employee.models import (
    Employee, Project, Task, WorkforceEvent, WorkforceInteraction,
    Notification, AIRecommendation, Prediction, WhatIfScenario,
    WorkloadHistory,
)
from .early_warning import generate_early_warnings
from .prediction_service import get_model_metadata

# WorkforceEvent types that represent a genuine ADMIN ACTION (an
# intervention), as opposed to a routine employee action or a passive
# system log entry. Deliberately conservative — when in doubt, an event
# is NOT counted as an intervention here.
INTERVENTION_EVENT_TYPES = {
    'TASK_ASSIGNED', 'TASK_REOPENED', 'AI_ANALYSIS_REFRESHED',
    'INTERACTION_ACKNOWLEDGED', 'INTERACTION_RESOLVED', 'INTERACTION_RESPONSE',
}


def _safe_json(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        try:
            return ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return None


# ---------------------------------------------------------------------------
# Decision memory
# ---------------------------------------------------------------------------

def build_decision_history(limit=50):
    """
    Normalizes two REAL sources of admin decisions into one timeline:
      - AIRecommendation rows that have moved past 'Open' (an admin looked
        at it and made a call)
      - WorkforceInteraction rows with a stored admin_response
    Nothing is invented; a 'decision' here always traces back to an actual
    stored row with a real created/updated date.
    """
    decisions = []

    for rec in AIRecommendation.objects.exclude(status='Open').select_related('employee', 'project', 'related_prediction').order_by('-created_date')[:limit]:
        decisions.append({
            'source': 'AIRecommendation', 'source_id': rec.id,
            'title': rec.recommendation_text[:120],
            'decision_type': rec.recommendation_type or 'GENERAL',
            'status': rec.status,
            'entity_type': 'employee' if rec.employee_id else ('project' if rec.project_id else None),
            'entity_id': rec.employee_id or rec.project_id,
            'entity_name': (rec.employee.user.first_name if rec.employee and rec.employee.user else (rec.employee.empid if rec.employee else None)) or (rec.project.name if rec.project else None),
            'evidence': {'prediction_id': rec.related_prediction_id} if rec.related_prediction_id else None,
            'created_date': rec.created_date,
        })

    for interaction in WorkforceInteraction.objects.exclude(admin_response__isnull=True).exclude(admin_response='').select_related('employee', 'related_project').order_by('-created_date')[:limit]:
        decisions.append({
            'source': 'WorkforceInteraction', 'source_id': interaction.id,
            'title': interaction.subject,
            'decision_type': interaction.interaction_type,
            'status': interaction.status,
            'entity_type': 'employee', 'entity_id': interaction.employee_id,
            'entity_name': interaction.employee.user.first_name if interaction.employee.user else interaction.employee.empid,
            'evidence': {'ai_category': interaction.ai_category} if interaction.ai_category else None,
            'chosen_action': interaction.admin_response,
            'created_date': interaction.updated_date or interaction.created_date,
        })

    decisions.sort(key=lambda d: d['created_date'] or 0, reverse=True)
    return decisions[:limit]


# ---------------------------------------------------------------------------
# Intervention tracking
# ---------------------------------------------------------------------------

def build_intervention_history(limit=50):
    """
    A real ADMIN action, never a simulation. Sourced from WorkforceEvent
    rows whose actor is a staff user and whose event_type is in
    INTERVENTION_EVENT_TYPES.
    """
    events = (
        WorkforceEvent.objects.filter(event_type__in=INTERVENTION_EVENT_TYPES, actor__is_staff=True)
        .select_related('employee', 'project', 'task', 'actor')
        .order_by('-created_date')[:limit]
    )
    interventions = []
    for e in events:
        interventions.append({
            'event_id': e.id, 'action_type': e.event_type, 'description': e.description,
            'admin': e.actor.username if e.actor else None,
            'employee': e.employee.empid if e.employee else None,
            'employee_id': e.employee_id,
            'project': e.project.name if e.project else None,
            'project_id': e.project_id,
            'task': e.task.title if e.task else None,
            'timestamp': e.created_date,
        })
    return interventions


def _workload_before_after(employee, timestamp):
    """Real before/after WorkloadHistory snapshot around a real timestamp.
    Returns None fields where there isn't a period on that side — never
    interpolates or guesses a value."""
    if not employee or not timestamp:
        return None
    before = WorkloadHistory.objects.filter(employee=employee, period__lt=timestamp).order_by('-period').first()
    after = WorkloadHistory.objects.filter(employee=employee, period__gte=timestamp).order_by('period').first()
    return {
        'before_score': before.workload_score if before else None,
        'before_period': before.period if before else None,
        'after_score': after.workload_score if after else None,
        'after_period': after.period if after else None,
    }


# ---------------------------------------------------------------------------
# Prediction vs actual outcome
# ---------------------------------------------------------------------------

def build_prediction_outcome_history():
    """
    Uses Prediction.actual_outcome exactly as instructed. As of this
    prompt, NOTHING in the application ever writes to actual_outcome (it
    was added in Prompt 2 for future use and remains NULL on every row —
    verified, not assumed). So this honestly reports INSUFFICIENT_OUTCOME_DATA
    rather than fabricating an evaluation.
    """
    evaluated = Prediction.objects.exclude(actual_outcome__isnull=True).exclude(actual_outcome='')
    total_predictions = Prediction.objects.count()

    if not evaluated.exists():
        return {
            'status': 'INSUFFICIENT_OUTCOME_DATA',
            'total_predictions_made': total_predictions,
            'predictions_with_recorded_outcome': 0,
            'reason': 'Prediction.actual_outcome has not been populated for any stored prediction yet — '
                      'there is no ground-truth recording step in the current application flow.',
            'rows': [],
        }

    rows, correct, incorrect = [], 0, 0
    for p in evaluated.select_related('employee', 'project'):
        is_correct = (p.predicted_outcome == p.actual_outcome)
        correct += 1 if is_correct else 0
        incorrect += 0 if is_correct else 1
        rows.append({
            'prediction_id': p.id, 'prediction_type': p.prediction_type,
            'predicted_outcome': p.predicted_outcome, 'actual_outcome': p.actual_outcome,
            'correct': is_correct, 'prediction_date': p.prediction_date,
            'model_version': p.model_version,
            'entity': p.employee.empid if p.employee else (p.project.name if p.project else None),
        })
    return {
        'status': 'OK', 'total_predictions_made': total_predictions,
        'predictions_with_recorded_outcome': len(rows), 'correct': correct, 'incorrect': incorrect,
        'accuracy': round(correct / len(rows), 3) if rows else None,
        'rows': rows,
        'sample_size_note': f'Based on {len(rows)} recorded outcome(s) — treat as directional, not statistically conclusive, at this sample size.',
    }


# ---------------------------------------------------------------------------
# Learning signals & repeated patterns (RULE-BASED, observations only)
# ---------------------------------------------------------------------------

def build_learning_signals():
    signals = []

    for field, label in (('related_employee', 'employee'), ('related_project', 'project')):
        qs = (
            Notification.objects.filter(category__in=['EMPLOYEE_RISK', 'PROJECT_RISK'])
            .exclude(**{f'{field}__isnull': True})
            .values(field)
            .distinct()
        )
        for row in qs:
            entity_id = row[field]
            count = Notification.objects.filter(category__in=['EMPLOYEE_RISK', 'PROJECT_RISK'], **{field: entity_id}).count()
            if count >= 2:
                entity = Employee.objects.filter(id=entity_id).first() if label == 'employee' else Project.objects.filter(id=entity_id).first()
                if not entity:
                    continue
                name = (entity.user.first_name if label == 'employee' and entity.user else getattr(entity, 'empid', None)) or getattr(entity, 'name', None)
                signals.append({
                    'pattern': 'REPEATED_WARNING_NOTIFICATIONS', 'entity_type': label, 'entity_id': entity_id,
                    'entity_name': name, 'observation': f"Observed: {count} risk-warning notification(s) recorded for {name} over the observed period.",
                    'evidence_count': count, 'source': 'RULE-BASED ORGANIZATIONAL PATTERN',
                    'limitation': 'This is a count of past notifications, not proof that the underlying risk is worsening.',
                })

    for row in WorkforceInteraction.objects.filter(interaction_type='BLOCKER').values('employee').annotate(n=Count('id')).filter(n__gte=2):
        emp = Employee.objects.filter(id=row['employee']).first()
        if not emp:
            continue
        name = emp.user.first_name if emp.user else emp.empid
        signals.append({
            'pattern': 'REPEATED_BLOCKERS', 'entity_type': 'employee', 'entity_id': emp.id,
            'entity_name': name, 'observation': f"Observed: {row['n']} blocker(s) reported by {name}.",
            'evidence_count': row['n'], 'source': 'RULE-BASED ORGANIZATIONAL PATTERN',
            'limitation': 'A count of reported blockers — does not by itself identify their root cause.',
        })

    for iv in build_intervention_history(limit=20):
        if not iv['employee_id']:
            continue
        emp = Employee.objects.filter(id=iv['employee_id']).first()
        if not emp:
            continue
        wa = _workload_before_after(emp, iv['timestamp'])
        if wa and wa['before_score'] is not None and wa['after_score'] is not None:
            direction = 'decreased' if wa['after_score'] < wa['before_score'] else ('increased' if wa['after_score'] > wa['before_score'] else 'stayed the same')
            signals.append({
                'pattern': 'INTERVENTION_FOLLOWED_BY_WORKLOAD_CHANGE', 'entity_type': 'employee', 'entity_id': emp.id,
                'entity_name': emp.user.first_name if emp.user else emp.empid,
                'observation': f"Observed: workload score {direction} from {wa['before_score']} to {wa['after_score']} "
                               f"around the time of an admin intervention ({iv['action_type']}) on {iv['timestamp']}.",
                'source': 'OBSERVATION', 'limitation': 'Occurred after the intervention — this is not proven causation.',
            })

    outcome_history = build_prediction_outcome_history()
    if outcome_history['status'] != 'OK':
        signals.append({
            'pattern': 'PREDICTION_ACCURACY_TREND', 'entity_type': None, 'entity_id': None, 'entity_name': None,
            'observation': 'INSUFFICIENT_OUTCOME_DATA — no predictions have a recorded actual outcome yet.',
            'source': 'INSUFFICIENT DATA', 'limitation': outcome_history['reason'],
        })

    return signals


def build_repeated_patterns():
    """Part 10 — rule-based recurring-issue detection using ONLY current
    real data. Explicitly labeled as a snapshot where no time-series
    exists (e.g. overdue status and anomaly detection are not persisted
    historically in this app)."""
    from .workforce_digital_twin import _employee_task_stats, _project_task_stats

    patterns = []
    for emp in Employee.objects.all():
        stats = _employee_task_stats(emp)
        if stats['overdue'] and stats['overdue'] >= 2:
            patterns.append({
                'pattern': 'RECURRING_OVERDUE_TASKS', 'entity_type': 'employee', 'entity_id': emp.id,
                'entity_name': emp.user.first_name if emp.user else emp.empid,
                'observation': f"{stats['overdue']} tasks currently overdue for this employee.",
                'source': 'RULE-BASED ORGANIZATIONAL PATTERN',
                'limitation': 'Current snapshot only — overdue status is not tracked historically, so true recurrence over time cannot be confirmed.',
            })
    for proj in Project.objects.exclude(status__in=['Completed', 'Cancelled']):
        stats = _project_task_stats(proj)
        if stats['overdue'] and stats['overdue'] >= 2:
            patterns.append({
                'pattern': 'RECURRING_PROJECT_DELIVERY_PRESSURE', 'entity_type': 'project', 'entity_id': proj.id,
                'entity_name': proj.name,
                'observation': f"{stats['overdue']} overdue tasks currently on this project.",
                'source': 'RULE-BASED ORGANIZATIONAL PATTERN',
                'limitation': 'Current snapshot only — not a confirmed multi-period trend.',
            })

    patterns.extend(build_learning_signals())  # reuse rather than duplicate the notification/blocker counts
    return patterns


# ---------------------------------------------------------------------------
# AI Impact Chain
# ---------------------------------------------------------------------------

def build_impact_chain(entity_type, entity_id):
    """
    Builds the Signal -> Evidence -> Prediction -> Simulation -> Decision
    -> Action -> Outcome -> Learning chain for ONE entity. Any stage with
    no real record is explicitly 'NOT AVAILABLE' — no stage is invented.
    """
    chain = {'entity_type': entity_type, 'entity_id': entity_id}

    if entity_type == 'employee':
        entity = Employee.objects.filter(id=entity_id).first()
        if not entity:
            return {'error': 'employee_not_found'}
        chain['entity_name'] = entity.user.first_name if entity.user else entity.empid
        warnings = generate_early_warnings(employee=entity)
        prediction = Prediction.objects.filter(employee=entity).order_by('-prediction_date').first()
        simulations = [s for s in WhatIfScenario.objects.order_by('-created_date')[:200]
                       if (_safe_json(s.input_parameters) or {}).get('employee_id') == entity_id
                       or (_safe_json(s.input_parameters) or {}).get('entity_id') == entity_id]
        decisions = [d for d in build_decision_history(limit=200) if d['entity_type'] == 'employee' and d['entity_id'] == entity_id]
        actions = [a for a in build_intervention_history(limit=200) if a['employee_id'] == entity_id]
    elif entity_type == 'project':
        entity = Project.objects.filter(id=entity_id).first()
        if not entity:
            return {'error': 'project_not_found'}
        chain['entity_name'] = entity.name
        warnings = generate_early_warnings(project=entity)
        prediction = Prediction.objects.filter(project=entity).order_by('-prediction_date').first()
        simulations = [s for s in WhatIfScenario.objects.order_by('-created_date')[:200]
                       if (_safe_json(s.input_parameters) or {}).get('project_id') == entity_id]
        decisions = [d for d in build_decision_history(limit=200) if d['entity_type'] == 'project' and d['entity_id'] == entity_id]
        actions = [a for a in build_intervention_history(limit=200) if a['project_id'] == entity_id]
    else:
        return {'error': 'unknown_entity_type'}

    chain['signal'] = warnings[0] if warnings else 'NOT AVAILABLE'
    chain['evidence'] = warnings[0]['evidence'] if warnings else 'NOT AVAILABLE'
    if prediction:
        model_name_map = {'PROJECT_OUTCOME': 'project_outcome', 'EMPLOYEE_RISK': 'employee_risk', 'EMPLOYEE_PERFORMANCE': 'employee_performance'}
        model_active = bool(get_model_metadata(model_name_map.get(prediction.prediction_type, '')))
        chain['prediction'] = {
            'predicted_outcome': prediction.predicted_outcome, 'confidence': prediction.confidence,
            'model_version': prediction.model_version, 'model_currently_active': model_active,
            'actual_outcome': prediction.actual_outcome,
        }
    else:
        chain['prediction'] = 'NOT AVAILABLE'
    chain['simulation'] = [{'scenario_type': s.scenario_type, 'created_date': s.created_date} for s in simulations] or 'NOT AVAILABLE'
    chain['decision'] = decisions[0] if decisions else 'NOT AVAILABLE'
    chain['action'] = actions[0] if actions else 'NOT AVAILABLE'

    if entity_type == 'employee' and actions:
        chain['outcome'] = _workload_before_after(entity, actions[0]['timestamp'])
    else:
        chain['outcome'] = 'NOT AVAILABLE'
    chain['learning'] = 'Related evidence only — no causal proof is established by this chain.'
    return chain


# ---------------------------------------------------------------------------
# Entity history / evidence explorer support
# ---------------------------------------------------------------------------

def build_entity_history(entity_type, entity_id):
    """All real records touching one entity, for the Evidence Explorer."""
    if entity_type == 'employee':
        entity = Employee.objects.filter(id=entity_id).first()
        if not entity:
            return {'error': 'employee_not_found'}
        events = WorkforceEvent.objects.filter(employee=entity).order_by('-created_date')[:50]
        predictions = Prediction.objects.filter(employee=entity).order_by('-prediction_date')[:20]
        interactions = WorkforceInteraction.objects.filter(employee=entity).order_by('-created_date')[:20]
        recommendations = AIRecommendation.objects.filter(employee=entity).order_by('-created_date')[:20]
    elif entity_type == 'project':
        entity = Project.objects.filter(id=entity_id).first()
        if not entity:
            return {'error': 'project_not_found'}
        events = WorkforceEvent.objects.filter(project=entity).order_by('-created_date')[:50]
        predictions = Prediction.objects.filter(project=entity).order_by('-prediction_date')[:20]
        interactions = WorkforceInteraction.objects.filter(related_project=entity).order_by('-created_date')[:20]
        recommendations = AIRecommendation.objects.filter(project=entity).order_by('-created_date')[:20]
    elif entity_type == 'task':
        entity = Task.objects.filter(id=entity_id).first()
        if not entity:
            return {'error': 'task_not_found'}
        events = WorkforceEvent.objects.filter(task=entity).order_by('-created_date')[:50]
        predictions = Prediction.objects.none()
        interactions = WorkforceInteraction.objects.filter(related_task=entity).order_by('-created_date')[:20]
        recommendations = AIRecommendation.objects.none()
    else:
        return {'error': 'unknown_entity_type'}

    return {
        'entity_type': entity_type, 'entity_id': entity_id,
        'events': list(events), 'predictions': list(predictions),
        'interactions': list(interactions), 'recommendations': list(recommendations),
    }


# ---------------------------------------------------------------------------
# Top-level organizational memory
# ---------------------------------------------------------------------------

def build_organizational_memory():
    decisions = build_decision_history(limit=20)
    interventions = build_intervention_history(limit=20)
    outcome_history = build_prediction_outcome_history()
    learning_signals = build_learning_signals()
    patterns = build_repeated_patterns()

    return {
        'decisions': decisions,
        'unresolved_decisions': [d for d in decisions if d['status'] in ('Open', 'ACKNOWLEDGED', 'OPEN', 'IN_PROGRESS', 'WAITING_FOR_EMPLOYEE')],
        'interventions': interventions,
        'prediction_outcome_history': outcome_history,
        'learning_signals': learning_signals,
        'repeated_patterns': patterns,
        'evaluation_summary': {
            'decisions_recorded': len(decisions),
            'interventions_recorded': len(interventions),
            'predictions_evaluated': outcome_history.get('predictions_with_recorded_outcome', 0),
            'learning_signals_detected': len(learning_signals),
        },
    }
