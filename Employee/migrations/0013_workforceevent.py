# Generated for Prompt 8 — Workforce Event Engine

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Employee', '0012_whatifscenario'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkforceEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[
                    ('TASK_CREATED', 'Task Created'), ('TASK_ASSIGNED', 'Task Assigned'),
                    ('TASK_UPDATED', 'Task Updated'), ('TASK_COMPLETED', 'Task Completed'),
                    ('TASK_REOPENED', 'Task Reopened'), ('TASK_OVERDUE', 'Task Overdue'),
                    ('PROJECT_UPDATED', 'Project Updated'), ('PROJECT_MEMBER_ADDED', 'Project Member Added'),
                    ('PROJECT_MEMBER_REMOVED', 'Project Member Removed'),
                    ('EMPLOYEE_STATUS_CHANGED', 'Employee Status Changed'),
                    ('LEAVE_STATUS_CHANGED', 'Leave/Status Reported'), ('FEEDBACK_ADDED', 'Feedback Added'),
                    ('NOTIFICATION_CREATED', 'Notification Created'), ('AI_WARNING_CREATED', 'AI Warning Created'),
                    ('AI_ANALYSIS_REFRESHED', 'AI Analysis Refreshed'), ('WHATIF_SIMULATION_RUN', 'What-If Simulation Run'),
                ], max_length=40)),
                ('description', models.CharField(max_length=300)),
                ('created_date', models.DateTimeField(auto_now_add=True, null=True)),
                ('severity', models.CharField(choices=[('info', 'Info'), ('warning', 'Warning'), ('critical', 'Critical')], default='info', max_length=10)),
                ('metadata', models.JSONField(blank=True, null=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='workforce_events_caused', to=settings.AUTH_USER_MODEL)),
                ('employee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='Employee.employee')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='Employee.project')),
                ('task', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='Employee.task')),
            ],
            options={
                'ordering': ['-created_date'],
            },
        ),
        migrations.AddIndex(
            model_name='workforceevent',
            index=models.Index(fields=['-created_date'], name='Employee_wo_created_8f1a01_idx'),
        ),
        migrations.AddIndex(
            model_name='workforceevent',
            index=models.Index(fields=['employee', '-created_date'], name='Employee_wo_employe_2c9b41_idx'),
        ),
        migrations.AddIndex(
            model_name='workforceevent',
            index=models.Index(fields=['project', '-created_date'], name='Employee_wo_project_5e6d71_idx'),
        ),
        migrations.AddIndex(
            model_name='workforceevent',
            index=models.Index(fields=['event_type'], name='Employee_wo_event_t_a13c91_idx'),
        ),
    ]
