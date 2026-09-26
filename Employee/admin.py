from django.contrib import admin

# Register your models here.
from Employee.models import *

admin.site.register(Department)
admin.site.register(Employee)
admin.site.register(Task)
admin.site.register(TaskTracking)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'dept', 'manager', 'status', 'priority', 'progress', 'deadline')
    list_filter = ('status', 'priority', 'dept')
    search_fields = ('name', 'code')
    ordering = ('-created_date',)


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ('project', 'employee', 'role', 'is_active', 'joined_date')
    list_filter = ('is_active', 'role')
    search_fields = ('project__name', 'employee__empid')


@admin.register(PerformanceHistory)
class PerformanceHistoryAdmin(admin.ModelAdmin):
    list_display = ('employee', 'period', 'tasks_assigned', 'tasks_completed', 'completion_rate', 'performance_score')
    list_filter = ('period',)
    search_fields = ('employee__empid',)
    ordering = ('-period',)


@admin.register(WorkloadHistory)
class WorkloadHistoryAdmin(admin.ModelAdmin):
    list_display = ('employee', 'dept', 'period', 'assigned_count', 'pending_count', 'overdue_count', 'workload_score')
    list_filter = ('period', 'dept')
    search_fields = ('employee__empid',)
    ordering = ('-period',)


@admin.register(LeaveStatus)
class LeaveStatusAdmin(admin.ModelAdmin):
    list_display = ('employee', 'reason', 'date', 'is_active')
    list_filter = ('reason', 'is_active')
    search_fields = ('employee__empid',)
    ordering = ('-date',)


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('employee', 'project', 'task', 'rating', 'created_date')
    list_filter = ('rating',)
    search_fields = ('employee__empid', 'feedback_text')
    ordering = ('-created_date',)


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ('prediction_type', 'employee', 'project', 'predicted_outcome', 'risk_level',
                     'confidence', 'model_version', 'actual_outcome', 'prediction_date')
    list_filter = ('prediction_type', 'risk_level', 'model_version')
    search_fields = ('employee__empid', 'project__name')
    ordering = ('-prediction_date',)


@admin.register(AIRecommendation)
class AIRecommendationAdmin(admin.ModelAdmin):
    list_display = ('recommendation_type', 'employee', 'project', 'priority', 'status', 'created_date')
    list_filter = ('status', 'priority', 'recommendation_type')
    search_fields = ('employee__empid', 'project__name', 'recommendation_text')
    ordering = ('-created_date',)


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'version', 'algorithm', 'is_active', 'training_date')
    list_filter = ('is_active', 'model_name')
    ordering = ('model_name', '-training_date')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'category', 'is_read', 'created_date')
    list_filter = ('category', 'is_read')
    search_fields = ('recipient__username', 'title', 'message')
    ordering = ('-created_date',)


@admin.register(WhatIfScenario)
class WhatIfScenarioAdmin(admin.ModelAdmin):
    list_display = ('scenario_type', 'created_by', 'created_date')
    list_filter = ('scenario_type',)
    ordering = ('-created_date',)


@admin.register(WorkforceEvent)
class WorkforceEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'description', 'employee', 'project', 'task', 'severity', 'created_date')
    list_filter = ('event_type', 'severity')
    search_fields = ('description', 'employee__empid', 'project__name')
    ordering = ('-created_date',)


@admin.register(WorkforceInteraction)
class WorkforceInteractionAdmin(admin.ModelAdmin):
    list_display = ('subject', 'employee', 'interaction_type', 'ai_category', 'priority', 'status', 'admin', 'created_date')
    list_filter = ('interaction_type', 'status', 'priority')
    search_fields = ('subject', 'message', 'employee__empid')
    ordering = ('-created_date',)
