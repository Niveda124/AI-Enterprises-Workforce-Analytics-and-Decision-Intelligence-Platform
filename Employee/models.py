from django.contrib.auth.models import User
from django.db import models


# Create your models here.
class Department(models.Model):
    name = models.CharField(max_length=100, null=True)
    create_date=models.DateTimeField(auto_now=True,null=True)
    def __str__(self):
        return self.name

class Employee(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    dept = models.ForeignKey(Department, on_delete=models.CASCADE, null=True)
    contact = models.CharField(max_length=100, null=True)
    empid = models.CharField(max_length=100, null=True)
    designation = models.CharField(max_length=100, null=True)
    dob = models.DateField(null=True)
    doj = models.DateField(null=True)
    address = models.CharField(max_length=100, null=True)
    description = models.CharField(max_length=100, null=True)
    image = models.FileField(null=True)
    on_leave = models.BooleanField(default=False)
    leave_return_date = models.DateField(null=True, blank=True)
    create_date=models.DateTimeField(auto_now=True,null=True)
    def __str__(self):
        return self.user.first_name
class Task(models.Model):
    dept = models.ForeignKey(Department, on_delete=models.CASCADE, null=True)
    emp = models.ForeignKey(Employee, on_delete=models.CASCADE, null=True)
    project = models.ForeignKey('Project', on_delete=models.SET_NULL, null=True, blank=True)
    priority = models.CharField(max_length=100, null=True)
    title = models.CharField(max_length=100, null=True)
    description = models.CharField(max_length=100, null=True)
    status = models.CharField(max_length=100, null=True)
    work = models.CharField(max_length=100, null=True)
    remark = models.CharField(max_length=100, null=True)
    assignDate=models.DateTimeField(auto_now=True,null=True)
    endDate=models.DateTimeField(null=True)
    completedDate = models.DateTimeField(null=True, blank=True)  # set only when status actually becomes 'Completed'
    def __str__(self):
        return self.title


class TaskTracking(models.Model):
    taskId = models.ForeignKey(Task, on_delete=models.CASCADE, null=True)
    remark = models.CharField(max_length=100, null=True)
    status = models.CharField(max_length=100, null=True)
    workCompleted = models.CharField(max_length=100, null=True)
    updationDate = models.DateTimeField(auto_now=True,null=True)

    def __str__(self):
        return self.taskId.title+" "+self.taskId


# ==================================================
# PROJECT MANAGEMENT FOUNDATION
# ==================================================

class Project(models.Model):
    STATUS_CHOICES = [
        ('Planning', 'Planning'),
        ('Active', 'Active'),
        ('On Hold', 'On Hold'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
        ('Critical', 'Critical'),
    ]
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    dept = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    manager = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_projects')
    start_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Planning')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Medium')
    progress = models.IntegerField(default=0)  # 0-100
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    updated_date = models.DateTimeField(auto_now=True, null=True)

    def __str__(self):
        return self.name


class ProjectMember(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    role = models.CharField(max_length=100, null=True, blank=True)
    joined_date = models.DateField(auto_now_add=True, null=True)
    responsibility = models.CharField(max_length=200, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.employee} on {self.project}"


# ==================================================
# PERFORMANCE & WORKLOAD HISTORY FOUNDATION
# ==================================================

class PerformanceHistory(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    period = models.DateField()  # e.g. first day of the month this record covers
    tasks_assigned = models.IntegerField(default=0)
    tasks_completed = models.IntegerField(default=0)
    tasks_overdue = models.IntegerField(default=0)
    completion_rate = models.FloatField(default=0)
    on_time_rate = models.FloatField(default=0)
    avg_delay_days = models.FloatField(default=0)
    workload_score = models.FloatField(default=0)
    performance_score = models.FloatField(default=0)
    created_date = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.employee} - {self.period}"


class WorkloadHistory(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    dept = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    period = models.DateField()
    assigned_count = models.IntegerField(default=0)
    completed_count = models.IntegerField(default=0)
    pending_count = models.IntegerField(default=0)
    overdue_count = models.IntegerField(default=0)
    workload_score = models.FloatField(default=0)
    created_date = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return f"{self.employee} workload - {self.period}"


# ==================================================
# FEEDBACK FOUNDATION
# ==================================================

class LeaveStatus(models.Model):
    REASON_CHOICES = [
        ('Leave', 'On Leave'),
        ('Sick', 'Sick / Not Feeling Well'),
        ('Other', 'Other'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    note = models.CharField(max_length=200, null=True, blank=True)
    date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.employee} - {self.reason} on {self.date}"


class Feedback(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)
    feedback_text = models.TextField()
    rating = models.IntegerField(null=True, blank=True)  # 1-5
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Feedback for {self.employee}"


# ==================================================
# AI PREDICTION / RECOMMENDATION / MODEL VERSION FOUNDATION
# (structure only — no ML logic yet, per Prompt 1 scope)
# ==================================================

class Prediction(models.Model):
    TYPE_CHOICES = [
        ('PROJECT_OUTCOME', 'Project Outcome'),
        ('EMPLOYEE_PERFORMANCE', 'Employee Performance'),
        ('EMPLOYEE_RISK', 'Employee Risk'),
        ('WORKLOAD_FORECAST', 'Workload Forecast'),
    ]
    prediction_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True)
    predicted_outcome = models.CharField(max_length=100, null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    risk_level = models.CharField(max_length=20, null=True, blank=True)
    prediction_date = models.DateTimeField(auto_now_add=True, null=True)
    model_version = models.CharField(max_length=50, null=True, blank=True)
    input_reference = models.TextField(null=True, blank=True)
    probabilities = models.TextField(null=True, blank=True)  # JSON: {"Success": 0.7, "Failure Risk": 0.3}
    explanation = models.TextField(null=True, blank=True)    # JSON: feature importance list
    actual_outcome = models.CharField(max_length=100, null=True, blank=True)  # ground truth, filled in later — NEVER fabricated

    def __str__(self):
        return f"{self.prediction_type} - {self.prediction_date}"


class AIRecommendation(models.Model):
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Acknowledged', 'Acknowledged'),
        ('Resolved', 'Resolved'),
    ]
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True)
    recommendation_type = models.CharField(max_length=100, null=True, blank=True)
    recommendation_text = models.TextField()
    priority = models.CharField(max_length=20, null=True, blank=True)
    related_prediction = models.ForeignKey(Prediction, on_delete=models.SET_NULL, null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')

    def __str__(self):
        return self.recommendation_text[:50]


class ModelVersion(models.Model):
    model_name = models.CharField(max_length=100)
    version = models.CharField(max_length=20)
    algorithm = models.CharField(max_length=100, null=True, blank=True)
    training_date = models.DateTimeField(null=True, blank=True)
    metrics = models.TextField(null=True, blank=True)  # store as JSON string
    model_file_path = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.model_name} v{self.version}"


# ==================================================
# NOTIFICATION FOUNDATION
# (created only from real system events — see views.py hooks)
# ==================================================

class Notification(models.Model):
    CATEGORY_CHOICES = [
        ('LEAVE_STATUS', 'Employee Leave/Status Report'),
        ('TASK_ASSIGNED', 'Task Assigned'),
        ('TASK_OVERDUE', 'Task Overdue'),
        ('PROJECT_RISK', 'Project Risk'),
        ('EMPLOYEE_RISK', 'Employee Risk'),
        ('GENERAL', 'General'),
    ]
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='GENERAL')
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    is_read = models.BooleanField(default=False)
    # optional links back to the real event that generated this notification
    related_employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    related_project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    related_task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f"[{self.category}] {self.title} -> {self.recipient}"


class WhatIfScenario(models.Model):
    """Minimal history record for the What-If Simulator (Prompt 5). No
    existing model can safely hold this — it is genuinely new information
    (a hypothetical run, not a real event or a stored prediction)."""
    scenario_type = models.CharField(max_length=50)
    input_parameters = models.TextField()   # JSON
    result_summary = models.TextField()     # JSON — condensed result, not the full payload
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_date = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f"{self.scenario_type} @ {self.created_date}"


class WorkforceEvent(models.Model):
    """
    Real workforce activity log (Prompt 8). Created ONLY from actual
    application actions (see Employee/ml/workforce_events.py and its call
    sites in views.py) — never generated speculatively, never backfilled
    for historical rows that predate this model.
    """
    EVENT_TYPES = [
        ('TASK_CREATED', 'Task Created'),
        ('TASK_ASSIGNED', 'Task Assigned'),
        ('TASK_UPDATED', 'Task Updated'),
        ('TASK_COMPLETED', 'Task Completed'),
        ('TASK_REOPENED', 'Task Reopened'),
        ('TASK_OVERDUE', 'Task Overdue'),
        ('PROJECT_UPDATED', 'Project Updated'),
        ('PROJECT_MEMBER_ADDED', 'Project Member Added'),
        ('PROJECT_MEMBER_REMOVED', 'Project Member Removed'),
        ('EMPLOYEE_STATUS_CHANGED', 'Employee Status Changed'),
        ('LEAVE_STATUS_CHANGED', 'Leave/Status Reported'),
        ('FEEDBACK_ADDED', 'Feedback Added'),
        ('NOTIFICATION_CREATED', 'Notification Created'),
        ('AI_WARNING_CREATED', 'AI Warning Created'),
        ('AI_ANALYSIS_REFRESHED', 'AI Analysis Refreshed'),
        ('WHATIF_SIMULATION_RUN', 'What-If Simulation Run'),
        ('INTERACTION_CREATED', 'Interaction Created'),
        ('INTERACTION_ACKNOWLEDGED', 'Interaction Acknowledged'),
        ('INTERACTION_RESPONSE', 'Interaction Response'),
        ('INTERACTION_RESOLVED', 'Interaction Resolved'),
    ]
    SEVERITY_CHOICES = [('info', 'Info'), ('warning', 'Warning'), ('critical', 'Critical')]

    event_type = models.CharField(max_length=40, choices=EVENT_TYPES)
    description = models.CharField(max_length=300)
    created_date = models.DateTimeField(auto_now_add=True, null=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='workforce_events_caused')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)
    interaction = models.ForeignKey('WorkforceInteraction', on_delete=models.SET_NULL, null=True, blank=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='info')
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-created_date']
        indexes = [
            models.Index(fields=['-created_date']),
            models.Index(fields=['employee', '-created_date']),
            models.Index(fields=['project', '-created_date']),
            models.Index(fields=['event_type']),
        ]

    def __str__(self):
        return f"[{self.event_type}] {self.description}"


class WorkforceInteraction(models.Model):
    """
    Human-AI Workforce Interaction (Prompt 10). Genuinely new — no
    existing model supports a structured, stateful employee<->admin
    exchange with AI-assisted triage. Notification/WorkforceEvent are
    reused for alerting and timeline history rather than duplicated here.
    """
    INTERACTION_TYPES = [
        ('BLOCKER', 'Blocker'),
        ('CLARIFICATION', 'Clarification'),
        ('ASSISTANCE', 'Assistance'),
        ('DEADLINE_CONCERN', 'Deadline Concern'),
        ('TASK_ISSUE', 'Task Issue'),
        ('PROJECT_ISSUE', 'Project Issue'),
        ('GENERAL', 'General'),
    ]
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('ACKNOWLEDGED', 'Acknowledged'),
        ('IN_PROGRESS', 'In Progress'),
        ('WAITING_FOR_EMPLOYEE', 'Waiting for Employee'),
        ('RESOLVED', 'Resolved'),
        ('CLOSED', 'Closed'),
    ]
    PRIORITY_CHOICES = [
        ('NORMAL', 'Normal'),
        ('ATTENTION', 'Attention'),
        ('URGENT', 'Urgent'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='interactions')
    admin = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='handled_interactions')
    interaction_type = models.CharField(max_length=30, choices=INTERACTION_TYPES)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='OPEN')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='NORMAL')

    # AI/rule-based triage — see Employee/ml/interaction_intelligence.py.
    # ai_confidence is intentionally nullable: this project has no
    # calibrated-probability method for this, so it is never fabricated.
    ai_category = models.CharField(max_length=50, null=True, blank=True)
    ai_summary = models.TextField(null=True, blank=True)
    ai_confidence = models.FloatField(null=True, blank=True)

    related_project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    related_task = models.ForeignKey(Task, on_delete=models.SET_NULL, null=True, blank=True)

    created_date = models.DateTimeField(auto_now_add=True, null=True)
    updated_date = models.DateTimeField(auto_now=True, null=True)
    employee_response = models.TextField(null=True, blank=True)
    admin_response = models.TextField(null=True, blank=True)
    resolved_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_date']
        indexes = [
            models.Index(fields=['-created_date']),
            models.Index(fields=['status']),
            models.Index(fields=['employee', '-created_date']),
        ]

    def __str__(self):
        return f"[{self.interaction_type}] {self.subject} ({self.employee})"









