"""
Skill Intelligence (Prompt 4)
===============================
IMPORTANT LIMITATION (stated up front, not hidden):
This schema has NO dedicated skills table or field anywhere — not on
Employee, not on Task, not on Project. There is therefore no way to
report a validated, employee-declared skill list, and this module never
invents one.

What IS real and used here:
  - Employee.designation (a stated job title/role)
  - Employee.dept (their department)
  - ProjectMember.role (the role they've actually been assigned on real
    projects — "Developer", "Lead", "Analyst", "Tester", etc.)
  - Project.dept / ProjectMember.role for the roles a project's roster
    actually needs

Every value below is read straight from the database. "Skill profile" and
"requirement profile" here mean a role/domain proxy built from that real
evidence — not a certified skill assessment. That distinction is kept
explicit in every function's output.
"""
from Employee.models import Employee, Project, ProjectMember


def build_employee_skill_profile(employee_id):
    try:
        employee = Employee.objects.get(id=employee_id)
    except Employee.DoesNotExist:
        return {'error': 'employee_not_found', 'employee_id': employee_id}

    memberships = ProjectMember.objects.filter(employee=employee).select_related('project')
    roles_held = sorted({m.role for m in memberships if m.role})

    return {
        'employee_id': employee.id,
        'name': employee.user.first_name if employee.user else employee.empid,
        'designation': employee.designation,
        'department': employee.dept.name if employee.dept else None,
        'roles_held': roles_held,
        'projects_worked_on': [m.project.name for m in memberships],
        'evidence_basis': 'designation field + project-membership role history (real DB records)',
        'limitation': 'No dedicated skills taxonomy exists in this schema — this is a role/domain '
                      'proxy, not a validated skill list.',
    }


def build_project_requirement_profile(project_id):
    try:
        project = Project.objects.get(id=project_id)
    except Project.DoesNotExist:
        return {'error': 'project_not_found', 'project_id': project_id}

    memberships = ProjectMember.objects.filter(project=project).select_related('employee')
    roles_needed = sorted({m.role for m in memberships if m.role})

    return {
        'project_id': project.id,
        'name': project.name,
        'department': project.dept.name if project.dept else None,
        'roles_needed': roles_needed,
        'current_roster_size': memberships.count(),
        'evidence_basis': 'roles currently recorded on this project\'s ProjectMember roster (real DB records)',
        'limitation': 'No explicit skill/requirement field exists on Project or Task — roles '
                      'needed are inferred only from who is currently staffed on the project, '
                      'not from a stated requirements list.',
    }


def match_employee_to_project(employee_id, project_id):
    """
    Rule-based, fully transparent overlap check — NOT a trained model and
    NOT a fabricated confidence score. Every number here is a literal count
    over real, retrieved sets.
    """
    emp_profile = build_employee_skill_profile(employee_id)
    if 'error' in emp_profile:
        return emp_profile
    proj_profile = build_project_requirement_profile(project_id)
    if 'error' in proj_profile:
        return proj_profile

    emp_roles = set(emp_profile['roles_held'])
    proj_roles = set(proj_profile['roles_needed'])

    matched_roles = sorted(emp_roles & proj_roles)
    gap_roles = sorted(proj_roles - emp_roles)  # project needs, employee has never held
    extra_roles = sorted(emp_roles - proj_roles)  # employee has, project doesn't currently need

    already_member = ProjectMember.objects.filter(employee_id=employee_id, project_id=project_id).exists()

    return {
        'employee_id': employee_id,
        'project_id': project_id,
        'already_assigned_to_project': already_member,
        'matched_roles': matched_roles,
        'gap_roles': gap_roles,
        'extra_roles_not_needed_here': extra_roles,
        'match_type': 'rule_based_role_overlap',
        'note': 'This is a transparent set-overlap count over recorded ProjectMember roles, '
                'not an ML confidence score and not a validated skills assessment.',
    }


def workforce_skill_coverage():
    """
    Org-wide view: for each role that has EVER been recorded on a
    ProjectMember row, how many distinct employees have held it. A role
    held by zero or very few employees is a real, database-backed coverage
    gap — not a guess.
    """
    all_roles = ProjectMember.objects.exclude(role__isnull=True).exclude(role='').values_list('role', flat=True).distinct()

    coverage = []
    for role in sorted(set(all_roles)):
        employee_ids = ProjectMember.objects.filter(role=role).values_list('employee_id', flat=True).distinct()
        coverage.append({'role': role, 'employee_count': len(set(employee_ids))})

    coverage.sort(key=lambda r: r['employee_count'])

    return {
        'total_roles_seen': len(coverage),
        'coverage': coverage,
        'note': 'Roles are those actually recorded in ProjectMember history — a role with a '
                'low employee_count is a real staffing-depth gap for that role, not a skill test result.',
    }
