"""employeeManagement URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from django.conf.urls.static import static
from Employee.views import *
from django.conf import settings
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', Home, name='home'),
    path('login_admin/', Login_admin, name='login_admin'),
    path('login_emp/', Login_Employee, name='login_emp'),
    path('emp_Change_Password/', Emp_Change_Password, name='emp_Change_Password'),
    path('admin_Change_Password/', Admin_Change_Password, name='admin_Change_Password'),
    path('logout/', Logout, name='logout'),
    path('admin_home/', admin_home, name='admin_home'),
    path('workforce_analytics/', workforce_analytics, name='workforce_analytics'),
    path('download_report/', download_report, name='download_report'),
    path('admin_projects/', admin_projects, name='admin_projects'),
    path('project_detail/<int:pid>/', project_detail, name='project_detail'),
    path('project_intelligence_report/<int:pid>/', project_intelligence_report, name='project_intelligence_report'),
    path('admin_employee_detail/<int:pid>/', admin_employee_detail, name='admin_employee_detail'),
    path('project_employee_intelligence/<int:pid>/<int:eid>/', project_employee_intelligence, name='project_employee_intelligence'),
    path('admin_workload_intelligence/', admin_workload_intelligence, name='admin_workload_intelligence'),
    path('smart_allocation/', smart_allocation, name='smart_allocation'),
    path('decision_center/', decision_center, name='decision_center'),
    path('refresh_ai_analysis/', refresh_ai_analysis, name='refresh_ai_analysis'),
    path('api/digital_twin/employee/<int:eid>/', api_employee_digital_twin, name='api_employee_digital_twin'),
    path('api/digital_twin/project/<int:pid>/', api_project_digital_twin, name='api_project_digital_twin'),
    path('api/digital_twin/workforce/', api_workforce_digital_twin, name='api_workforce_digital_twin'),
    path('api/notifications/<int:notif_id>/read/', api_mark_notification_read, name='api_mark_notification_read'),
    path('api/intelligence/anomalies/', api_workforce_anomalies, name='api_workforce_anomalies'),
    path('api/intelligence/skill_profile/<int:eid>/', api_employee_skill_profile, name='api_employee_skill_profile'),
    path('api/intelligence/project_requirements/<int:pid>/', api_project_requirement_profile, name='api_project_requirement_profile'),
    path('api/intelligence/skill_match/<int:eid>/<int:pid>/', api_skill_match, name='api_skill_match'),
    path('api/intelligence/skill_coverage/', api_workforce_skill_coverage, name='api_workforce_skill_coverage'),
    path('api/intelligence/explain/employee/<int:eid>/', api_explain_employee_risk, name='api_explain_employee_risk'),
    path('api/intelligence/explain/project/<int:pid>/', api_explain_project_outcome, name='api_explain_project_outcome'),
    path('what_if_simulator/', what_if_simulator_page, name='what_if_simulator'),
    path('api/decision/what-if/', api_whatif_simulate, name='api_whatif_simulate'),
    # Prompt 8 — Living Workforce Intelligence
    path('workforce_observatory/', workforce_observatory, name='workforce_observatory'),
    path('api/workforce/pulse/', api_workforce_pulse, name='api_workforce_pulse'),
    path('api/workforce/events/', api_workforce_events, name='api_workforce_events'),
    path('project_intelligence/<int:pid>/', project_intelligence, name='project_intelligence'),
    path('employee_intelligence/<int:eid>/', employee_intelligence, name='employee_intelligence'),
    path('task_intelligence/<int:task_id>/', task_intelligence, name='task_intelligence'),
    path('my_work_pulse/', my_work_pulse, name='my_work_pulse'),
    path('my_changes/', my_changes, name='my_changes'),
    path('my_activity/', my_activity, name='my_activity'),
    path('api/my/activity/', api_my_activity, name='api_my_activity'),
    # Prompt 9 — Future Protection & Prevention Intelligence
    path('what_changed/', admin_what_changed, name='admin_what_changed'),
    path('prevention_center/', prevention_center, name='prevention_center'),
    path('future_scenario/<str:entity_type>/<int:entity_id>/', future_scenario, name='future_scenario'),
    path('my_prevention/', my_prevention, name='my_prevention'),
    path('my_future/', my_future, name='my_future'),
    # Prompt 10 — Human-AI Workforce Interaction
    path('report_blocker/', report_blocker, name='report_blocker'),
    path('request_clarification/', request_clarification, name='request_clarification'),
    path('request_assistance/', request_assistance, name='request_assistance'),
    path('my_interactions/', my_interactions, name='my_interactions'),
    path('my_interaction/<int:interaction_id>/', my_interaction_detail, name='my_interaction_detail'),
    path('workforce_interactions/', workforce_interactions, name='workforce_interactions'),
    path('workforce_interaction/<int:interaction_id>/', workforce_interaction_detail, name='workforce_interaction_detail'),
    # Prompt 11 — Organizational Brain / Closed Decision Loop
    path('organizational_brain/', organizational_brain_page, name='organizational_brain'),
    path('evidence_explorer/', evidence_explorer, name='evidence_explorer'),
    path('my_decisions/', my_decisions, name='my_decisions'),
    path('emp_report_status/', emp_report_status, name='emp_report_status'),
    path('update_recommendation_status/<int:rid>/', update_recommendation_status, name='update_recommendation_status'),
    path('whatif_analysis/', whatif_analysis, name='whatif_analysis'),
    path('emp_my_projects/', emp_my_projects, name='emp_my_projects'),
    path('emp_my_intelligence/', emp_my_intelligence, name='emp_my_intelligence'),
    path('admin_ai_intelligence/', admin_ai_intelligence, name='admin_ai_intelligence'),
    path('generate_predictions/', generate_predictions, name='generate_predictions'),
    path('reports/', reports, name='reports'),
    path('emp_reports/', emp_reports, name='emp_reports'),
    path('emp_home/', emp_home, name='emp_home'),
    path('add_department/', add_department, name='add_department'),
    path('view_department/', view_department, name='view_department'),
    path('update_department/<int:pid>', update_department, name='update_department'),
    path('delete_department/<int:pid>', delete_department, name='delete_department'),
    path('add_employee/', add_employee, name='add_employee'),
    path('edit_employee/<int:pid>', edit_employee, name='edit_employee'),
    path('delete_employee/<int:pid>', delete_employee, name='delete_employee'),
    path('toggle_employee_leave/<int:pid>', toggle_employee_leave, name='toggle_employee_leave'),
    path('view_employee/', view_employee, name='view_employee'),
    path('checkid/', checkid, name='checkid'),
    path('add_task/', add_task, name='add_task'),
    path('dropdown/', dropdown, name='dropdown'),
    path('emp_new_task/', emp_new_task, name='emp_new_task'),
    path('emp_inprogress_task/', emp_inprogress_task, name='emp_inprogress_task'),
    path('emp_completed_task/', emp_completed_task, name='emp_completed_task'),
    path('emp_all_task/', emp_all_task, name='emp_all_task'),
    path('emp_edit_employee/', emp_edit_employee, name='emp_edit_employee'),
    path('new_task_detail/<int:pid>', new_task_detail, name='new_task_detail'),
    path('update_task_tracker/<int:pid>', updateTaskTracker, name='update_task_tracker'),
    path('admin_view_new_task/', admin_view_new_task, name='admin_view_new_task'),
    path('admin_view_inprogress_task/', admin_view_inprogress_task, name='admin_view_inprogress_task'),
    path('admin_view_completed_task/', admin_view_completed_task, name='admin_view_completed_task'),
    path('admin_view_task_detail/<int:pid>', admin_view_task_detail, name='admin_view_task_detail'),
    path('find_by_date/', find_by_date, name='find_by_date'),
    path('search_employee/', search_employee, name='search_employee'),
    path('view_emp_task/<int:pid>', view_emp_task, name='view_emp_task'),
]+static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
