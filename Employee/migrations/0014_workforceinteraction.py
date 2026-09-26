# Generated for Prompt 10 — Human-AI Workforce Interaction

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Employee', '0013_workforceevent'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkforceInteraction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('interaction_type', models.CharField(choices=[
                    ('BLOCKER', 'Blocker'), ('CLARIFICATION', 'Clarification'), ('ASSISTANCE', 'Assistance'),
                    ('DEADLINE_CONCERN', 'Deadline Concern'), ('TASK_ISSUE', 'Task Issue'),
                    ('PROJECT_ISSUE', 'Project Issue'), ('GENERAL', 'General'),
                ], max_length=30)),
                ('subject', models.CharField(max_length=200)),
                ('message', models.TextField()),
                ('status', models.CharField(choices=[
                    ('OPEN', 'Open'), ('ACKNOWLEDGED', 'Acknowledged'), ('IN_PROGRESS', 'In Progress'),
                    ('WAITING_FOR_EMPLOYEE', 'Waiting for Employee'), ('RESOLVED', 'Resolved'), ('CLOSED', 'Closed'),
                ], default='OPEN', max_length=30)),
                ('priority', models.CharField(choices=[
                    ('NORMAL', 'Normal'), ('ATTENTION', 'Attention'), ('URGENT', 'Urgent'),
                ], default='NORMAL', max_length=20)),
                ('ai_category', models.CharField(blank=True, max_length=50, null=True)),
                ('ai_summary', models.TextField(blank=True, null=True)),
                ('ai_confidence', models.FloatField(blank=True, null=True)),
                ('created_date', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_date', models.DateTimeField(auto_now=True, null=True)),
                ('employee_response', models.TextField(blank=True, null=True)),
                ('admin_response', models.TextField(blank=True, null=True)),
                ('resolved_date', models.DateTimeField(blank=True, null=True)),
                ('admin', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='handled_interactions', to=settings.AUTH_USER_MODEL)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='interactions', to='Employee.employee')),
                ('related_project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='Employee.project')),
                ('related_task', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='Employee.task')),
            ],
            options={
                'ordering': ['-created_date'],
            },
        ),
        migrations.AddIndex(
            model_name='workforceinteraction',
            index=models.Index(fields=['-created_date'], name='Employee_wi_created_1a2b3c_idx'),
        ),
        migrations.AddIndex(
            model_name='workforceinteraction',
            index=models.Index(fields=['status'], name='Employee_wi_status_4d5e6f_idx'),
        ),
        migrations.AddIndex(
            model_name='workforceinteraction',
            index=models.Index(fields=['employee', '-created_date'], name='Employee_wi_employe_7a8b9c_idx'),
        ),
        migrations.AddField(
            model_name='workforceevent',
            name='interaction',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='Employee.workforceinteraction'),
        ),
        migrations.AlterField(
            model_name='workforceevent',
            name='event_type',
            field=models.CharField(choices=[
                ('TASK_CREATED', 'Task Created'), ('TASK_ASSIGNED', 'Task Assigned'),
                ('TASK_UPDATED', 'Task Updated'), ('TASK_COMPLETED', 'Task Completed'),
                ('TASK_REOPENED', 'Task Reopened'), ('TASK_OVERDUE', 'Task Overdue'),
                ('PROJECT_UPDATED', 'Project Updated'), ('PROJECT_MEMBER_ADDED', 'Project Member Added'),
                ('PROJECT_MEMBER_REMOVED', 'Project Member Removed'),
                ('EMPLOYEE_STATUS_CHANGED', 'Employee Status Changed'),
                ('LEAVE_STATUS_CHANGED', 'Leave/Status Reported'), ('FEEDBACK_ADDED', 'Feedback Added'),
                ('NOTIFICATION_CREATED', 'Notification Created'), ('AI_WARNING_CREATED', 'AI Warning Created'),
                ('AI_ANALYSIS_REFRESHED', 'AI Analysis Refreshed'), ('WHATIF_SIMULATION_RUN', 'What-If Simulation Run'),
                ('INTERACTION_CREATED', 'Interaction Created'), ('INTERACTION_ACKNOWLEDGED', 'Interaction Acknowledged'),
                ('INTERACTION_RESPONSE', 'Interaction Response'), ('INTERACTION_RESOLVED', 'Interaction Resolved'),
            ], max_length=40),
        ),
    ]
