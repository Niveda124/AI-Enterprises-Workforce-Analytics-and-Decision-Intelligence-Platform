"""
Workforce Event Engine (Prompt 8)
====================================
A thin, reusable layer over WorkforceEvent. Every call site is an actual
application action (see the call sites in views.py) — this module never
invents an event, backdates a timestamp, or fabricates a value. It does
not duplicate any existing intelligence calculation; it only records
that a real action happened and lets Digital Twin / anomaly / prediction
services (already built in Prompts 3-6) be queried fresh whenever an
event page wants current intelligence.
"""
from Employee.models import WorkforceEvent

EVENT_TYPES = [t[0] for t in WorkforceEvent.EVENT_TYPES]


def record_event(event_type, description, actor=None, employee=None, project=None,
                  task=None, interaction=None, severity='info', metadata=None,
                  employee_id=None, project_id=None, task_id=None):
    """Records ONE real event. Raises if event_type isn't a known type —
    callers should not be able to silently invent a new category.
    Accepts either model instances (employee=<Employee>) or raw primary
    keys (employee_id=<int>) for callers that only have an id on hand."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown workforce event_type: {event_type}")
    create_kwargs = dict(event_type=event_type, description=description[:300], actor=actor,
                          severity=severity, metadata=metadata or {}, interaction=interaction)
    if employee_id is not None:
        create_kwargs['employee_id'] = employee_id
    else:
        create_kwargs['employee'] = employee
    if project_id is not None:
        create_kwargs['project_id'] = project_id
    else:
        create_kwargs['project'] = project
    if task_id is not None:
        create_kwargs['task_id'] = task_id
    else:
        create_kwargs['task'] = task
    return WorkforceEvent.objects.create(**create_kwargs)


def recent_events(limit=30, employee=None, project=None, event_type=None):
    qs = WorkforceEvent.objects.all()
    if employee is not None:
        qs = qs.filter(employee=employee)
    if project is not None:
        qs = qs.filter(project=project)
    if event_type:
        qs = qs.filter(event_type=event_type)
    return list(qs.order_by('-created_date')[:limit])


def events_since(since_id=None, since_time=None, employee=None, limit=50):
    """Used by the polling APIs. Returns events strictly after the given
    marker, oldest-first, so the frontend can append them in order."""
    qs = WorkforceEvent.objects.all()
    if since_id is not None:
        qs = qs.filter(id__gt=since_id)
    elif since_time is not None:
        qs = qs.filter(created_date__gt=since_time)
    if employee is not None:
        qs = qs.filter(employee=employee)
    return list(qs.order_by('id')[:limit])
