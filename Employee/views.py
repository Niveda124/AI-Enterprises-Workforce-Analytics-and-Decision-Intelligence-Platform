from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from .models import *
from django.db.models import Q
import json
import calendar
from functools import wraps
from datetime import date, timedelta
from django.db.models import Count
from django.utils import timezone


def admin_required(view_func):
    """
    Replaces the bare @login_required(login_url='/login_admin/') pattern
    used throughout this file. login_required() only checks
    is_authenticated — it does NOT check is_staff, so an authenticated
    Employee could previously reach any admin_* view or admin API
    endpoint directly by URL. This wrapper closes that gap while keeping
    the exact same call-site syntax (@admin_required) and the same
    redirect-to-login behavior the rest of the app already uses.
    """
    @wraps(view_func)
    @login_required(login_url='/login_admin/')
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect('/login_admin/')
        return view_func(request, *args, **kwargs)
    return _wrapped


def employee_required(view_func):
    """
    Replaces the bare @login_required(login_url='/login_emp/') pattern.
    Also closes the reverse gap: previously an authenticated Admin/staff
    account (or any user without an Employee profile) could reach
    Employee-only views directly by URL.
    """
    @wraps(view_func)
    @login_required(login_url='/login_emp/')
    def _wrapped(request, *args, **kwargs):
        if request.user.is_staff or not Employee.objects.filter(user=request.user).exists():
            return redirect('/login_emp/')
        return view_func(request, *args, **kwargs)
    return _wrapped
# Create your views here.


def Home(request):
    return render(request,'index.html')
def Login_admin(request):
    if request.method == "POST":
        u = request.POST['uname']
        p = request.POST['pwd']
        user = authenticate(username=u, password=p)
        if user is not None and user.is_staff:
            login(request, user)
            messages.success(request, "Logged in Successfully")
            return redirect('admin_home')
        messages.error(request, "Invalid admin credentials.")
    return render(request, 'admin_login.html')
@admin_required
def admin_home(request):
    Emp = Employee.objects.all()
    Dept = Department.objects.all()
    task = Task.objects.all()
    newtask = Task.objects.filter(status="Not Updated Yet")
    inprogresstask = Task.objects.filter(status="Inprogress")
    completedtask = Task.objects.filter(status="Completed")

    Emp_count = Emp.count()
    Dept_count = Dept.count()
    task_count = task.count()
    newtask_count = newtask.count()
    inprogresstask_count = inprogresstask.count()
    completedtask_count = completedtask.count()
    completion_rate = round((completedtask_count / task_count) * 100, 1) if task_count else 0

    dept_data = Department.objects.annotate(emp_count=Count('employee'))
    dept_labels = [d.name for d in dept_data]
    dept_counts = [d.emp_count for d in dept_data]

    status_labels = ["New", "In Progress", "Completed"]
    status_counts = [newtask_count, inprogresstask_count, completedtask_count]

    monthly_labels = []
    monthly_total = []
    monthly_completed = []
    today = date.today()
    for i in range(5, -1, -1):
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        monthly_labels.append(f"{calendar.month_abbr[month]} {year}")
        qs = Task.objects.filter(assignDate__year=year, assignDate__month=month)
        monthly_total.append(qs.count())
        monthly_completed.append(qs.filter(status="Completed").count())

    # Project Health Score: average risk of all non-completed tasks (inverted)
    active_tasks = Task.objects.exclude(status="Completed")
    if active_tasks.count():
        total_risk = sum(calculate_task_risk(t)[1] for t in active_tasks)
        avg_risk = total_risk / active_tasks.count()
        project_health = round(100 - avg_risk, 1)
    else:
        project_health = 100

    high_risk_count = sum(1 for t in active_tasks if calculate_task_risk(t)[0] == "High")

 # ---- AI Decision Intelligence: rule-based recommendations ----
    recommendations = []

    # Rule 1: Department overload (avg tasks per employee too high)
    for d in Department.objects.all():
        emp_count_d = Employee.objects.filter(dept=d).count()
        task_count_d = Task.objects.filter(dept=d).exclude(status="Completed").count()
        if emp_count_d > 0:
            avg = task_count_d / emp_count_d
            if avg >= 4:
                recommendations.append({
                    'level': 'danger',
                    'icon': 'fa-exclamation-triangle',
                    'text': f"{d.name} department is overloaded — {round(avg,1)} active tasks per employee on average. Consider redistributing tasks or hiring."
                })
            elif avg >= 2.5:
                recommendations.append({
                    'level': 'warning',
                    'icon': 'fa-exclamation-circle',
                    'text': f"{d.name} department workload is trending high ({round(avg,1)} tasks/employee). Monitor closely."
                })

    # Rule 2: High-risk tasks needing attention
    high_risk_tasks = [t for t in Task.objects.exclude(status="Completed") if calculate_task_risk(t)[0] == "High"]
    if len(high_risk_tasks) >= 3:
        recommendations.append({
            'level': 'danger',
            'icon': 'fa-fire',
            'text': f"{len(high_risk_tasks)} tasks are at High Risk of missing their deadline. Review the Task list and reassign or extend deadlines where needed."
        })
    elif len(high_risk_tasks) > 0:
        recommendations.append({
            'level': 'warning',
            'icon': 'fa-clock-o',
            'text': f"{len(high_risk_tasks)} task(s) flagged High Risk. Keep an eye on these."
        })

    # Rule 3: Employees with poor completion rate (possible burnout/attrition risk)
    for e in Employee.objects.all():
        emp_tasks = Task.objects.filter(emp=e)
        total_e = emp_tasks.count()
        if total_e >= 3:
            completed_e = emp_tasks.filter(status="Completed").count()
            rate = completed_e / total_e
            if rate < 0.4:
                name = e.user.first_name if e.user else e.empid
                recommendations.append({
                    'level': 'warning',
                    'icon': 'fa-user-times',
                    'text': f"{name} has a low task completion rate ({round(rate*100)}%). May indicate overload or need for support."
                })

    # Rule 4: Employees on leave with active tasks — real deadline-risk detection
    on_leave_emps = Employee.objects.filter(on_leave=True)
    for e in on_leave_emps:
        active_tasks_e = Task.objects.filter(emp=e).exclude(status="Completed")
        active_count = active_tasks_e.count()
        if active_count > 0:
            name = e.user.first_name if e.user else e.empid
            due_soon = [t for t in active_tasks_e if t.endDate and t.endDate.date() <= date.today() + timedelta(days=3)]
            if due_soon:
                recommendations.append({
                    'level': 'danger',
                    'icon': 'fa-user-times',
                    'text': f"{name} is on leave and has {active_count} active task(s), including {len(due_soon)} due within 3 days. These are at high risk of missing deadline — reassign now or notify the client/stakeholder."
                })
            else:
                recommendations.append({
                    'level': 'warning',
                    'icon': 'fa-suitcase',
                    'text': f"{name} is currently on leave with {active_count} active task(s) still assigned. Consider temporary reassignment to keep timelines on track."
                })

    # Rule 4b: All clear
    if not recommendations:
        recommendations.append({
            'level': 'success',
            'icon': 'fa-check-circle',
            'text': "All departments and tasks are within healthy limits. No immediate action needed."
        })

    
    # Top performers — ranked by real completion rate
    top_performers = []
    for e in Employee.objects.all():
        e_tasks = Task.objects.filter(emp=e)
        e_total = e_tasks.count()
        e_completed = e_tasks.filter(status="Completed").count()
        if e_total > 0:
            top_performers.append({
                'name': e.user.first_name if e.user else e.empid,
                'dept': e.dept.name if e.dept else "-",
                'rate': round((e_completed / e_total) * 100, 1),
            })
    top_performers.sort(key=lambda x: x['rate'], reverse=True)
    top_performers = top_performers[:5]

    # Department performance — real completion rate per department
    dept_performance = []
    for d in Department.objects.all():
        d_tasks = Task.objects.filter(dept=d)
        d_total = d_tasks.count()
        d_completed = d_tasks.filter(status="Completed").count()
        dept_performance.append({
            'name': d.name,
            'rate': round((d_completed / d_total) * 100, 1) if d_total else 0,
        })

    # Recent activity — real latest tasks
    recent_tasks = Task.objects.all().order_by('-assignDate')[:5]

    context = {
        'Emp': Emp_count,
        'Dept': Dept_count,
        'task': task_count,
        'newtask': newtask_count,
        'inprogresstask': inprogresstask_count,
        'completedtask': completedtask_count,
        'completion_rate': completion_rate,
        'dept_labels': json.dumps(dept_labels),
        'dept_counts': json.dumps(dept_counts),
        'status_labels': json.dumps(status_labels),
        'status_counts': json.dumps(status_counts),
        'monthly_labels': json.dumps(monthly_labels),
        'monthly_total': json.dumps(monthly_total),
        'monthly_completed': json.dumps(monthly_completed),
        'project_health': project_health,
        'health_remainder': round(100 - project_health, 1),
        'high_risk_count': high_risk_count,   
                'recommendations': recommendations,
        'top_performers': top_performers,
        'dept_performance': dept_performance,
        'recent_tasks': recent_tasks,
    }
    return render(request, 'admin_home.html', context)
@employee_required
def emp_home(request):
    emp = Employee.objects.get(user=request.user)
    all_tasks = Task.objects.filter(emp=emp)
    newtask_qs = all_tasks.filter(status="Not Updated Yet")
    inprogresstask_qs = all_tasks.filter(status="Inprogress")
    completedtask_qs = all_tasks.filter(status="Completed")

    task = all_tasks.count()
    newtask = newtask_qs.count()
    inprogresstask = inprogresstask_qs.count()
    completedtask = completedtask_qs.count()
    completion_rate = round((completedtask / task) * 100, 1) if task else 0

    # Priority breakdown (for donut chart)
    priority_labels = ["High", "Medium", "Low"]
    priority_counts = [
        all_tasks.filter(priority__iexact="High").count(),
        all_tasks.filter(priority__iexact="Medium").count(),
        all_tasks.filter(priority__iexact="Low").count(),
    ]

    # Last 6 months: assigned vs completed (personal trend)
    monthly_labels = []
    monthly_total = []
    monthly_completed = []
    today = date.today()
    for i in range(5, -1, -1):
        month = today.month - i
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        monthly_labels.append(f"{calendar.month_abbr[month]} {year}")
        qs = all_tasks.filter(assignDate__year=year, assignDate__month=month)
        monthly_total.append(qs.count())
        monthly_completed.append(qs.filter(status="Completed").count())

    # Personal risk tasks (uses the same AI risk engine from Phase 3)
    my_risk_tasks = [t for t in all_tasks.exclude(status="Completed")]
    for t in my_risk_tasks:
        t.risk_label, t.risk_score = calculate_task_risk(t)
    high_risk_my = sum(1 for t in my_risk_tasks if t.risk_label == "High")

    context = {
        'task': task,
        'newtask': newtask,
        'inprogresstask': inprogresstask,
        'completedtask': completedtask,
        'completion_rate': completion_rate,
        'priority_labels': json.dumps(priority_labels),
        'priority_counts': json.dumps(priority_counts),
        'monthly_labels': json.dumps(monthly_labels),
        'monthly_total': json.dumps(monthly_total),
        'monthly_completed': json.dumps(monthly_completed),
        'high_risk_my': high_risk_my,
        'emp_name': emp.user.first_name if emp.user else emp.empid,
    }
    return render(request, 'emp_home.html', context)

@admin_required
def add_department(request):
    if request.method == 'POST':
        d = request.POST['department']
        Department.objects.create(name=d)
        messages.success(request, "Registration Successful")
        return redirect('view_department')
    return render(request,'add_department.html')

    
@admin_required
def workforce_analytics(request):
    depts = Department.objects.all()
    dept_labels = []
    avg_tasks_per_emp = []
    completion_pct = []

    for d in depts:
        emp_count = Employee.objects.filter(dept=d).count()
        dept_tasks = Task.objects.filter(dept=d)
        total_tasks = dept_tasks.count()
        completed = dept_tasks.filter(status="Completed").count()

        dept_labels.append(d.name)
        avg_tasks_per_emp.append(round(total_tasks / emp_count, 1) if emp_count else 0)
        completion_pct.append(round((completed / total_tasks) * 100, 1) if total_tasks else 0)

    employees = Employee.objects.all()
    workload_labels = []
    workload_counts = []
    risk_employees = []

    for e in employees:
        name = e.user.first_name if e.user else e.empid
        assigned = Task.objects.filter(emp=e)
        total = assigned.count()
        completed = assigned.filter(status="Completed").count()
        overdue = assigned.exclude(status="Completed").filter(endDate__lt=date.today()).count()

        workload_labels.append(name)
        workload_counts.append(total)

        if total > 0:
            overdue_ratio = overdue / total
            if overdue_ratio >= 0.5:
                risk_level = "High"
            elif overdue_ratio >= 0.2:
                risk_level = "Medium"
            else:
                risk_level = "Low"
        else:
            risk_level = "Low"

        risk_employees.append({
            "name": name,
            "empid": e.empid,
            "dept": e.dept.name if e.dept else "-",
            "total_tasks": total,
            "completed": completed,
            "overdue": overdue,
            "risk": risk_level,
        })

    tenure_buckets = {"<1 yr": 0, "1-2 yrs": 0, "2-4 yrs": 0, "4+ yrs": 0}
    for e in employees:
        if e.doj:
            years = (date.today() - e.doj).days / 365
            if years < 1:
                tenure_buckets["<1 yr"] += 1
            elif years < 2:
                tenure_buckets["1-2 yrs"] += 1
            elif years < 4:
                tenure_buckets["2-4 yrs"] += 1
            else:
                tenure_buckets["4+ yrs"] += 1

    context = {
        'dept_labels': json.dumps(dept_labels),
        'avg_tasks_per_emp': json.dumps(avg_tasks_per_emp),
        'completion_pct': json.dumps(completion_pct),
        'workload_labels': json.dumps(workload_labels),
        'workload_counts': json.dumps(workload_counts),
        'tenure_labels': json.dumps(list(tenure_buckets.keys())),
        'tenure_counts': json.dumps(list(tenure_buckets.values())),
        'risk_employees': risk_employees,
    }
    return render(request, 'workforce_analytics.html', context)




@admin_required
def update_department(request,pid):
    data=Department.objects.get(id=pid)
    if request.method == 'POST':
        d = request.POST['department']
        data.name=d
        data.save()
        messages.success(request, "Updation Successful")
        return redirect('view_department')
    return render(request,'update_department.html',{'data':data})
@admin_required
def delete_department(request,pid):
    data=Department.objects.get(id=pid)
    data.delete()
    messages.success(request, "delete Successful")
    return redirect('view_department')
@admin_required
def view_department(request):
    data=Department.objects.all()
    return render(request,'view_department.html',{'data':data})
@admin_required
def add_employee(request):
    deptdata=Department.objects.all()
    emp=Employee.objects.all()
    empid = Employee.objects.filter().last()
    if empid:
        empmainid=int(empid.empid)+1
    else:
        empmainid=1000

    if request.method == 'POST':
        d = request.POST['departmentid']
        eid = request.POST['eid']
        en = request.POST['name']
        e = request.POST['email']
        c = request.POST['contact']
        ed = request.POST['designation']
        dob = request.POST['dob']
        add = request.POST['address']
        doj = request.POST['doj']
        des= request.POST['description']
        pas= request.POST['password']
        img= request.FILES['img']
        dept=Department.objects.get(id=d)
        user=User.objects.create_user(username=eid,email=e,password=pas,first_name=en)
        Employee.objects.create(user=user,dept=dept,empid=eid,contact=c,designation=ed,dob=dob,doj=doj,description=des,address=add,image=img)
        messages.success(request, "Registration Successful")
        return redirect('view_employee')
    return render(request,'add_employee.html',locals())
@admin_required
def edit_employee(request,pid):
    deptdata=Department.objects.all()
    emp=Employee.objects.get(id=pid)
    if request.method == 'POST':
        d = request.POST['departmentid']
        eid = request.POST['eid']
        en = request.POST['name']
        e = request.POST['email']
        c = request.POST['contact']
        ed = request.POST['designation']
        dob = request.POST['dob']
        add = request.POST['address']
        doj = request.POST['doj']
        des= request.POST['description']
        dept=Department.objects.get(id=d)
        emp.dept=dept
        emp.empid=eid
        emp.user.first_name=en
        emp.user.email=e
        emp.contact=c
        emp.designation=ed
        emp.dob=dob
        emp.doj=doj
        emp.address=add
        emp.description=des
        try:
            im = request.FILES['img']
            emp.image = im
            emp.save()
        except:
            pass
        emp.user.save()
        emp.save()
        messages.success(request, "Updetation Successful")
        return redirect('view_employee')
    return render(request,'edit_employee.html',locals())
@employee_required
def emp_edit_employee(request):
    deptdata=Department.objects.all()
    emp=Employee.objects.get(user=request.user)
    if request.method == 'POST':
        en = request.POST['name']
        e = request.POST['email']
        c = request.POST['contact']
        ed = request.POST['designation']
        dob = request.POST['dob']
        add = request.POST['address']
        doj = request.POST['doj']
        des= request.POST['description']
        emp.user.first_name=en
        emp.user.email=e
        emp.contact=c
        emp.designation=ed
        emp.dob=dob
        emp.doj=doj
        emp.address=add
        emp.description=des
        try:
            im = request.FILES['img']
            emp.image = im
            emp.save()
        except:
            pass
        emp.user.save()
        emp.save()
        messages.success(request, "Updetation Successful")
        return redirect('emp_home')
    return render(request,'emp_edit_employee.html',locals())

def checkid(request):
    try:
        data=Employee.objects.get(user__email=request.GET['mainid'])
        dict = {'status':False, 'message':"Email is already Exist"}
    except:
        dict = {'status':True ,'message': "Unique Email"}
    return JsonResponse(dict)
@admin_required
def view_employee(request):
    data=Employee.objects.all()
    return render(request,'view_employee.html',{'data':data})
@admin_required
def delete_employee(request,pid):
    pat = User.objects.get(id=pid)
    pat.delete()
    messages.success(request,'Employee Deleted Successfully')
    return redirect('view_employee')
@admin_required
def toggle_employee_leave(request,pid):
    emp = Employee.objects.get(id=pid)
    emp.on_leave = not emp.on_leave
    if not emp.on_leave:
        emp.leave_return_date = None
    emp.save()
    if emp.on_leave:
        messages.success(request, f"{emp.user.first_name} marked as On Leave")
    else:
        messages.success(request, f"{emp.user.first_name} marked as Available")
    return redirect('view_employee')
@admin_required
def add_task(request):
    deptdata=Department.objects.all()
    emp=Employee.objects.all()
    if request.method == 'POST':
        d = request.POST['departmentid']
        eid = request.POST['empid']
        p = request.POST['priority']
        t = request.POST['title']
        td = request.POST['description']
        eod = request.POST['eod']
        dept=Department.objects.get(id=d)
        em=Employee.objects.get(id=eid)
        new_task = Task.objects.create(dept=dept,emp=em,priority=p,title=t,description=td,endDate=eod,status='Not Updated Yet')
        if em.user:
            Notification.objects.create(
                recipient=em.user, category='TASK_ASSIGNED', related_task=new_task,
                related_employee=em,
                title="New task assigned",
                message=f'You have been assigned a new task: "{t}" (priority: {p}).',
            )
        from .ml.workforce_events import record_event
        record_event('TASK_CREATED', f'Task "{t}" created for {em.empid}.',
                     actor=request.user, employee=em, task=new_task)
        record_event('TASK_ASSIGNED', f'Task "{t}" assigned to {em.empid}.',
                     actor=request.user, employee=em, task=new_task)
        messages.success(request, "Task Assign Successful")
        return redirect('admin_view_new_task')
    return render(request,'assign_task.html',locals())

@admin_required
def admin_projects(request):
    q = request.GET.get('q', '')
    projects = Project.objects.all()
    if q:
        projects = projects.filter(name__icontains=q)

    chart_labels = []
    chart_outcomes = []
    chart_ids = []
    for p in projects:
        latest = Prediction.objects.filter(project=p, prediction_type='PROJECT_OUTCOME').order_by('-prediction_date').first()
        chart_labels.append(p.name)
        chart_outcomes.append(latest.predicted_outcome if latest else "No Prediction")
        chart_ids.append(p.id)

    return render(request, 'admin_projects.html', {
        'projects': projects, 'q': q,
        'chart_labels': json.dumps(chart_labels),
        'chart_outcomes': json.dumps(chart_outcomes),
        'chart_ids': json.dumps(chart_ids),
    })


@admin_required
def project_detail(request, pid):
    import json as _json
    project = Project.objects.get(id=pid)
    memberships = ProjectMember.objects.filter(project=project)
    tasks = Task.objects.filter(project=project)

    # ---- Team Intelligence: real per-member stats ----
    team_rows = []
    for m in memberships:
        emp_tasks = tasks.filter(emp=m.employee)
        assigned = emp_tasks.count()
        completed = emp_tasks.filter(status="Completed").count()
        pending = emp_tasks.exclude(status="Completed").count()
        overdue = emp_tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
        completion_rate = round((completed / assigned) * 100, 1) if assigned else None
        latest_perf = PerformanceHistory.objects.filter(employee=m.employee).order_by('-period').first()
        latest_workload = WorkloadHistory.objects.filter(employee=m.employee).order_by('-period').first()
        team_rows.append({
            'member': m, 'assigned': assigned, 'completed': completed,
            'pending': pending, 'overdue': overdue, 'completion_rate': completion_rate,
            'performance_score': latest_perf.performance_score if latest_perf else None,
            'workload_score': latest_workload.workload_score if latest_workload else None,
            'workload_status': calculate_workload_status(pending, overdue),
        })

    # ---- Live Task Intelligence ----
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status="Completed").count()
    pending_tasks = tasks.exclude(status="Completed").count()
    overdue_tasks = tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
    high_priority_tasks = tasks.filter(priority__iexact="High").count()
    completion_rate = round((completed_tasks / total_tasks) * 100, 1) if total_tasks else None
    overdue_rate = round((overdue_tasks / total_tasks) * 100, 1) if total_tasks else None

    days_remaining = (project.deadline - date.today()).days if project.deadline else None

    # ---- Real ML Prediction (Prompt 3/4's trained model, unchanged) ----
    prediction = Prediction.objects.filter(project=project, prediction_type='PROJECT_OUTCOME').order_by('-prediction_date').first()
    prediction_history = Prediction.objects.filter(project=project, prediction_type='PROJECT_OUTCOME').order_by('-prediction_date')[1:6]

    prob_data = None
    explanation_data = None
    if prediction:
        if prediction.probabilities:
            prob_data = _json.loads(prediction.probabilities)
        if prediction.explanation:
            explanation_data = _json.loads(prediction.explanation)

    # ---- Prediction Drivers (real model feature importances, human-labelled) ----
    feature_labels = {
        'total_tasks': 'Total task count', 'completed_tasks': 'Completed tasks',
        'pending_tasks': 'Pending tasks', 'overdue_tasks': 'Overdue tasks',
        'high_priority_tasks': 'High priority task load', 'team_size': 'Team size',
        'completion_rate': 'Task completion rate', 'overdue_rate': 'Overdue task rate',
        'progress': 'Recorded project progress', 'days_remaining': 'Days remaining to deadline',
        'priority_encoded': 'Project priority level',
    }
    prediction_drivers = None
    if explanation_data:
        prediction_drivers = []
        for e in explanation_data:
            prediction_drivers.append({
                'label': feature_labels.get(e['feature'], e['feature']),
                'importance': e['importance'],
                'value': e['value'],
            })

    # ---- Live Recommendations: generated from THIS project's real numbers, with evidence ----
    recommendations = []
    if total_tasks == 0:
        recommendations.append({
            'priority': 'Info', 'issue': 'No tasks recorded yet',
            'evidence': 'This project has 0 linked tasks.',
            'action': 'Assign tasks to this project so risk and workload can be evaluated.',
        })
    else:
        if overdue_tasks > 0:
            recommendations.append({
                'priority': 'High' if overdue_tasks >= max(2, total_tasks * 0.25) else 'Medium',
                'issue': 'Overdue task concentration',
                'evidence': f"{overdue_tasks} of {total_tasks} project tasks are overdue ({overdue_rate}%).",
                'action': 'Review overdue assignments and rebalance workload among available team members.',
            })
        if days_remaining is not None and days_remaining <= 7 and project.status not in ["Completed", "Cancelled"]:
            recommendations.append({
                'priority': 'High' if days_remaining < 0 else 'Medium',
                'issue': 'Deadline pressure' if days_remaining >= 0 else 'Deadline passed',
                'evidence': f"{days_remaining} day(s) remaining to deadline with {pending_tasks} task(s) still pending.",
                'action': 'Reassess deadline feasibility or reprioritize remaining tasks.',
            })
        if high_priority_tasks > 0 and completion_rate is not None and completion_rate < 50:
            recommendations.append({
                'priority': 'Medium',
                'issue': 'High-priority tasks at risk',
                'evidence': f"{high_priority_tasks} High-priority task(s) exist while overall completion rate is {completion_rate}%.",
                'action': 'Prioritize High-priority tasks in the next work cycle.',
            })
        for row in team_rows:
            if row['workload_status'] in ['High', 'Critical']:
                recommendations.append({
                    'priority': 'High' if row['workload_status'] == 'Critical' else 'Medium',
                    'issue': f"{row['member'].employee.user.first_name if row['member'].employee.user else row['member'].employee.empid} workload is {row['workload_status']}",
                    'evidence': f"{row['pending']} pending and {row['overdue']} overdue task(s) currently assigned to this member.",
                    'action': 'Consider redistributing some of this member\'s pending tasks to others on the team.',
                })
        if not recommendations:
            recommendations.append({
                'priority': 'Info', 'issue': 'No active risk factors detected',
                'evidence': f"Completion rate {completion_rate}%, 0 overdue tasks, workload within normal range.",
                'action': 'No action required at this time.',
            })

    # ---- Health score: real ML confidence if available, else transparent data-driven fallback ----
    if prediction and prediction.confidence is not None:
        health_score = round(prediction.confidence * 100, 1)
        health_source = "ml"
    elif total_tasks > 0:
        health_score = round(max(0, min(100, completion_rate - (overdue_rate or 0))), 1)
        health_source = "rule"
    else:
        health_score = None
        health_source = "none"

    context = {
        'project': project, 'team_rows': team_rows, 'tasks': tasks,
        'total_tasks': total_tasks, 'completed_tasks': completed_tasks,
        'pending_tasks': pending_tasks, 'overdue_tasks': overdue_tasks,
        'high_priority_tasks': high_priority_tasks,
        'completion_rate': completion_rate, 'overdue_rate': overdue_rate,
        'days_remaining': days_remaining,
        'prediction': prediction, 'prediction_history': prediction_history,
        'prob_data': prob_data, 'prediction_drivers': prediction_drivers,
        'recommendations': recommendations,
        'health_score': health_score, 'health_source': health_source,
        'task_status_labels': json.dumps(["Completed", "Pending", "Overdue"]),
        'task_status_counts': json.dumps([completed_tasks, pending_tasks - overdue_tasks if pending_tasks >= overdue_tasks else 0, overdue_tasks]),
    }
    return render(request, 'project_detail.html', context)
    memberships = ProjectMember.objects.filter(project=project)
    tasks = Task.objects.filter(project=project)

    team_rows = []
    for m in memberships:
        emp_tasks = tasks.filter(emp=m.employee)
        latest_perf = PerformanceHistory.objects.filter(employee=m.employee).order_by('-period').first()
        latest_workload = WorkloadHistory.objects.filter(employee=m.employee).order_by('-period').first()
        team_rows.append({
            'member': m,
            'assigned': emp_tasks.count(),
            'completed': emp_tasks.filter(status="Completed").count(),
            'pending': emp_tasks.exclude(status="Completed").count(),
            'overdue': emp_tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count(),
            'performance_score': latest_perf.performance_score if latest_perf else None,
            'workload_score': latest_workload.workload_score if latest_workload else None,
        })

    total_tasks = tasks.count()
    completed_tasks = tasks.filter(status="Completed").count()
    pending_tasks = tasks.exclude(status="Completed").count()
    overdue_tasks = tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
    completion_rate = round((completed_tasks / total_tasks) * 100, 1) if total_tasks else 0

    days_remaining = (project.deadline - date.today()).days if project.deadline else None

    prediction = Prediction.objects.filter(project=project, prediction_type='PROJECT_OUTCOME').order_by('-prediction_date').first()
    prediction_history = Prediction.objects.filter(project=project, prediction_type='PROJECT_OUTCOME').order_by('-prediction_date')[1:6]
    recommendations = AIRecommendation.objects.filter(project=project).order_by('-created_date')

    prob_data = None
    explanation_data = None
    if prediction:
        if prediction.probabilities:
            prob_data = _json.loads(prediction.probabilities)
        if prediction.explanation:
            explanation_data = _json.loads(prediction.explanation)

    context = {
        'project': project, 'team_rows': team_rows, 'tasks': tasks,
        'total_tasks': total_tasks, 'completed_tasks': completed_tasks,
        'pending_tasks': pending_tasks, 'overdue_tasks': overdue_tasks,
        'completion_rate': completion_rate, 'days_remaining': days_remaining,
        'prediction': prediction, 'prediction_history': prediction_history,
        'prob_data': prob_data, 'explanation_data': explanation_data,
        'recommendations': recommendations,
    }
    return render(request, 'project_detail.html', context)


@admin_required
def project_intelligence_report(request, pid):
    from django.template.loader import get_template
    from xhtml2pdf import pisa
    from io import BytesIO
    import json as _json

    project = Project.objects.get(id=pid)
    memberships = ProjectMember.objects.filter(project=project)
    tasks = Task.objects.filter(project=project)
    prediction = Prediction.objects.filter(project=project, prediction_type='PROJECT_OUTCOME').order_by('-prediction_date').first()
    recommendations = AIRecommendation.objects.filter(project=project).order_by('-created_date')

    prob_data = _json.loads(prediction.probabilities) if prediction and prediction.probabilities else None
    explanation_data = _json.loads(prediction.explanation) if prediction and prediction.explanation else None

    context = {
        'project': project,
        'team': memberships,
        'total_tasks': tasks.count(),
        'completed_tasks': tasks.filter(status="Completed").count(),
        'pending_tasks': tasks.exclude(status="Completed").count(),
        'overdue_tasks': tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count(),
        'prediction': prediction,
        'prob_data': prob_data,
        'explanation_data': explanation_data,
        'recommendations': recommendations,
        'generated_on': date.today().strftime("%d-%m-%Y"),
    }
    template = get_template('project_intelligence_report_pdf.html')
    html = template.render(context)
    result = BytesIO()
    pisa.CreatePDF(html, dest=result)
    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="project_{project.id}_intelligence_report.pdf"'
    return response


@admin_required
def project_employee_intelligence(request, pid, eid):
    import json as _json
    project = Project.objects.get(id=pid)
    emp = Employee.objects.get(id=eid)
    membership = ProjectMember.objects.filter(project=project, employee=emp).first()

    project_tasks = Task.objects.filter(project=project, emp=emp)
    assigned = project_tasks.count()
    completed = project_tasks.filter(status="Completed").count()
    pending = project_tasks.exclude(status="Completed").count()
    overdue = project_tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
    completion_rate = round((completed / assigned) * 100, 1) if assigned else 0

    latest_workload = WorkloadHistory.objects.filter(employee=emp).order_by('-period').first()
    latest_perf = PerformanceHistory.objects.filter(employee=emp).order_by('-period').first()
    performance_history = PerformanceHistory.objects.filter(employee=emp).order_by('period')

    workload_status = calculate_workload_status(pending, overdue)

    perf_prediction = Prediction.objects.filter(employee=emp, prediction_type='EMPLOYEE_PERFORMANCE').order_by('-prediction_date').first()
    risk_prediction = Prediction.objects.filter(employee=emp, prediction_type='EMPLOYEE_RISK').order_by('-prediction_date').first()
    risk_prob = _json.loads(risk_prediction.probabilities) if risk_prediction and risk_prediction.probabilities else None
    risk_explanation = _json.loads(risk_prediction.explanation) if risk_prediction and risk_prediction.explanation else None

    # Project impact — only claims supported by actual current data
    impact_notes = []
    if overdue > 0:
        impact_notes.append(f"{overdue} overdue task(s) on this project may delay the project deadline.")
    if pending >= 3:
        impact_notes.append(f"{pending} pending task(s) on this project — a notable share of this employee's current load.")
    if assigned > 0 and completion_rate < 50:
        impact_notes.append(f"Completion rate on this project is {completion_rate}%, below half of assigned tasks.")
    if risk_prediction and risk_prediction.predicted_outcome == "High":
        impact_notes.append("Employee's overall ML risk prediction is High — relevant to this project's outcome risk.")
    if not impact_notes:
        impact_notes.append("No specific risk factors detected from this employee's current data on this project.")

    # Recommendations — data-driven, not automatic reassignment
    recommendations = []
    if overdue > 0:
        recommendations.append("Review and prioritize this employee's overdue tasks on this project.")
    if latest_workload and latest_workload.workload_score and latest_workload.workload_score > 7:
        recommendations.append("Consider workload balancing — recorded workload score is high.")
    if not recommendations:
        recommendations.append("No specific action recommended at this time based on current data.")

    context = {
        'project': project, 'emp': emp, 'membership': membership,
        'assigned': assigned, 'completed': completed, 'pending': pending, 'overdue': overdue,
        'completion_rate': completion_rate, 'workload_status': workload_status,
        'latest_workload': latest_workload, 'latest_perf': latest_perf, 'performance_history': performance_history,
        'perf_prediction': perf_prediction, 'risk_prediction': risk_prediction,
        'risk_prob': risk_prob, 'risk_explanation': risk_explanation,
        'impact_notes': impact_notes, 'recommendations': recommendations,
    }
    return render(request, 'project_employee_intelligence.html', context)


@admin_required
def admin_employee_detail(request, pid):
    import json as _json
    emp = Employee.objects.get(id=pid)
    performance = PerformanceHistory.objects.filter(employee=emp).order_by('period')
    workload = WorkloadHistory.objects.filter(employee=emp).order_by('period')
    perf_prediction = Prediction.objects.filter(employee=emp, prediction_type='EMPLOYEE_PERFORMANCE').order_by('-prediction_date').first()
    risk_prediction = Prediction.objects.filter(employee=emp, prediction_type='EMPLOYEE_RISK').order_by('-prediction_date').first()
    recommendations = AIRecommendation.objects.filter(employee=emp).order_by('-created_date')

    risk_prob = _json.loads(risk_prediction.probabilities) if risk_prediction and risk_prediction.probabilities else None
    risk_explanation = _json.loads(risk_prediction.explanation) if risk_prediction and risk_prediction.explanation else None
    perf_prob = _json.loads(perf_prediction.probabilities) if perf_prediction and perf_prediction.probabilities else None

    context = {
        'emp': emp, 'performance': performance, 'workload': workload,
        'perf_prediction': perf_prediction, 'risk_prediction': risk_prediction,
        'risk_prob': risk_prob, 'risk_explanation': risk_explanation, 'perf_prob': perf_prob,
        'recommendations': recommendations,
    }
    return render(request, 'admin_employee_detail.html', context)


@employee_required
def emp_my_projects(request):
    emp = Employee.objects.get(user=request.user)
    memberships = ProjectMember.objects.filter(employee=emp, is_active=True)
    project_rows = []
    for m in memberships:
        team = ProjectMember.objects.filter(project=m.project)
        my_tasks = Task.objects.filter(project=m.project, emp=emp)
        project_rows.append({
            'project': m.project,
            'role': m.role,
            'responsibility': m.responsibility,
            'team': team,
            'my_tasks': my_tasks,
        })
    return render(request, 'emp_my_projects.html', {'project_rows': project_rows})


@employee_required
def emp_my_intelligence(request):
    import json as _json
    emp = Employee.objects.get(user=request.user)
    my_tasks = Task.objects.filter(emp=emp)
    my_pending = my_tasks.exclude(status="Completed").count()
    my_overdue = my_tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
    my_completed = my_tasks.filter(status="Completed").count()
    my_workload_status = calculate_workload_status(my_pending, my_overdue)
    performance = PerformanceHistory.objects.filter(employee=emp).order_by('period')
    workload = WorkloadHistory.objects.filter(employee=emp).order_by('period')
    perf_prediction = Prediction.objects.filter(employee=emp, prediction_type='EMPLOYEE_PERFORMANCE').order_by('-prediction_date').first()
    risk_prediction = Prediction.objects.filter(employee=emp, prediction_type='EMPLOYEE_RISK').order_by('-prediction_date').first()
    recommendations = AIRecommendation.objects.filter(employee=emp).order_by('-created_date')

    risk_prob = _json.loads(risk_prediction.probabilities) if risk_prediction and risk_prediction.probabilities else None
    risk_explanation = _json.loads(risk_prediction.explanation) if risk_prediction and risk_prediction.explanation else None
    perf_prob = _json.loads(perf_prediction.probabilities) if perf_prediction and perf_prediction.probabilities else None

    context = {
        'performance': performance,
        'workload': workload,
        'my_pending': my_pending,
        'my_overdue': my_overdue,
        'my_completed': my_completed,
        'my_workload_status': my_workload_status,
        'perf_prediction': perf_prediction,
        'risk_prediction': risk_prediction,
        'risk_prob': risk_prob,
        'risk_explanation': risk_explanation,
        'perf_prob': perf_prob,
        'recommendations': recommendations,
        'perf_periods': json.dumps([p.period.strftime('%b %Y') for p in performance]),
        'perf_scores': json.dumps([p.performance_score for p in performance]),
        'workload_periods': json.dumps([w.period.strftime('%b %Y') for w in workload]),
        'workload_assigned': json.dumps([w.assigned_count for w in workload]),
        'workload_completed': json.dumps([w.completed_count for w in workload]),
        'workload_pending': json.dumps([w.pending_count for w in workload]),
        'workload_overdue': json.dumps([w.overdue_count for w in workload]),
    }
    return render(request, 'emp_my_intelligence.html', context)


@admin_required
def generate_predictions(request):
    from .ml.prediction_service import predict_project_outcome, predict_employee_risk, predict_employee_performance
    results = []
    for p in Project.objects.all():
        results.append(predict_project_outcome(p))
    for e in Employee.objects.all():
        results.append(predict_employee_risk(e))
        results.append(predict_employee_performance(e))
    messages.success(request, "Prediction run complete.")
    return redirect('admin_ai_intelligence')


@admin_required
def admin_ai_intelligence(request):
    predictions = Prediction.objects.all().order_by('-prediction_date')
    recommendations = AIRecommendation.objects.all().order_by('-created_date')
    context = {'predictions': predictions, 'recommendations': recommendations}
    return render(request, 'admin_ai_intelligence.html', context)


@admin_required
def reports(request):
    dept_rows = []
    for d in Department.objects.all():
        dept_rows.append({'dept': d.name, 'emp_count': Employee.objects.filter(dept=d).count()})

    project_rows = list(Project.objects.all().values('name', 'status', 'priority', 'progress'))
    for pr in project_rows:
        proj = Project.objects.get(name=pr['name'])
        tasks = Task.objects.filter(project=proj)
        pr['total_tasks'] = tasks.count()
        pr['completed_tasks'] = tasks.filter(status="Completed").count()

    performance_rows = list(PerformanceHistory.objects.all().order_by('-period')[:50])
    ai_rows = list(Prediction.objects.all().order_by('-prediction_date')[:50])

    context = {
        'is_admin_view': True,
        'dept_count': Department.objects.count(),
        'emp_count': Employee.objects.count(),
        'project_count': Project.objects.count(),
        'task_count': Task.objects.count(),
        'dept_rows': dept_rows,
        'project_rows': project_rows,
        'performance_rows': performance_rows,
        'ai_rows': ai_rows,
    }
    return render(request, 'reports.html', context)


@employee_required
def emp_reports(request):
    emp = Employee.objects.get(user=request.user)
    memberships = ProjectMember.objects.filter(employee=emp, is_active=True)
    my_project_rows = []
    for m in memberships:
        my_project_rows.append({
            'project': m.project.name,
            'progress': m.project.progress,
            'role': m.role,
            'my_tasks': Task.objects.filter(project=m.project, emp=emp).count(),
        })

    context = {
        'is_admin_view': False,
        'my_tasks': Task.objects.filter(emp=emp).count(),
        'my_completed': Task.objects.filter(emp=emp, status="Completed").count(),
        'my_projects': memberships.count(),
        'my_performance_rows': PerformanceHistory.objects.filter(employee=emp).order_by('-period'),
        'my_workload_rows': WorkloadHistory.objects.filter(employee=emp).order_by('-period'),
        'my_project_rows': my_project_rows,
        'my_predictions': Prediction.objects.filter(employee=emp).order_by('-prediction_date'),
        'my_recommendations': AIRecommendation.objects.filter(employee=emp).order_by('-created_date'),
    }
    return render(request, 'reports.html', context)

from django.template.loader import get_template
from xhtml2pdf import pisa
from io import BytesIO

@admin_required
def download_report(request):
    depts = Department.objects.all()
    report_data = []
    for d in depts:
        emp_count = Employee.objects.filter(dept=d).count()
        dept_tasks = Task.objects.filter(dept=d)
        total = dept_tasks.count()
        completed = dept_tasks.filter(status="Completed").count()
        report_data.append({
            'dept': d.name,
            'emp_count': emp_count,
            'total_tasks': total,
            'completed': completed,
            'completion_pct': round((completed / total) * 100, 1) if total else 0,
        })

    employees = Employee.objects.all()
    emp_data = []
    for e in employees:
        tasks = Task.objects.filter(emp=e)
        total = tasks.count()
        completed = tasks.filter(status="Completed").count()
        emp_data.append({
            'name': e.user.first_name if e.user else e.empid,
            'empid': e.empid,
            'dept': e.dept.name if e.dept else "-",
            'total_tasks': total,
            'completed': completed,
        })

    template = get_template('report_pdf.html')
    html = template.render({
        'report_data': report_data,
        'emp_data': emp_data,
        'generated_on': date.today().strftime("%d-%m-%Y"),
    })

    result = BytesIO()
    pisa.CreatePDF(html, dest=result)
    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="workforce_report.pdf"'
    return response


def calculate_workload_status(pending, overdue):
    """Simple data-driven workload status — NOT an ML prediction."""
    if overdue >= 5 or pending >= 10:
        return "Critical"
    elif overdue >= 2 or pending >= 6:
        return "High"
    elif pending >= 3:
        return "Moderate"
    else:
        return "Low"


def calculate_allocation_score(pending, overdue, workload_score, performance_score):
    """
    Transparent, data-driven allocation score — NOT an ML prediction.
    Lower pending/overdue/workload_score and higher performance_score = better score.
    """
    score = 100
    score -= pending * 5
    score -= overdue * 8
    score -= workload_score * 2
    score += performance_score * 0.3
    return round(score, 1)


@admin_required
def admin_workload_intelligence(request):
    employees = Employee.objects.all()
    rows = []
    for e in employees:
        tasks = Task.objects.filter(emp=e)
        pending = tasks.exclude(status="Completed").count()
        overdue = tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
        completed = tasks.filter(status="Completed").count()
        assigned = tasks.count()

        latest_workload = WorkloadHistory.objects.filter(employee=e).order_by('-period').first()
        latest_perf = PerformanceHistory.objects.filter(employee=e).order_by('-period').first()

        rows.append({
            'employee': e,
            'dept': e.dept.name if e.dept else "-",
            'assigned': assigned,
            'completed': completed,
            'pending': pending,
            'overdue': overdue,
            'workload_score': latest_workload.workload_score if latest_workload else None,
            'performance_score': latest_perf.performance_score if latest_perf else None,
            'status': calculate_workload_status(pending, overdue),
        })

    total_employees = employees.count()
    active_employees = sum(1 for r in rows if r['pending'] > 0)
    total_pending = sum(r['pending'] for r in rows)
    total_overdue = sum(r['overdue'] for r in rows)

    status_counts = {'Low': 0, 'Moderate': 0, 'High': 0, 'Critical': 0}
    for r in rows:
        status_counts[r['status']] += 1

    context = {
        'rows': rows,
        'total_employees': total_employees,
        'active_employees': active_employees,
        'total_pending': total_pending,
        'total_overdue': total_overdue,
        'status_labels': json.dumps(list(status_counts.keys())),
        'status_counts': json.dumps(list(status_counts.values())),
    }
    return render(request, 'admin_workload_intelligence.html', context)


@admin_required
def smart_allocation(request):
    deptdata = Department.objects.all()
    suggestions = None
    selected_dept = None

    if request.method == 'POST':
        dept_id = request.POST.get('departmentid')
        selected_dept = Department.objects.get(id=dept_id)
        employees = Employee.objects.filter(dept=selected_dept)

        ranked = []
        for e in employees:
            tasks = Task.objects.filter(emp=e)
            pending = tasks.exclude(status="Completed").count()
            overdue = tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()

            latest_workload = WorkloadHistory.objects.filter(employee=e).order_by('-period').first()
            latest_perf = PerformanceHistory.objects.filter(employee=e).order_by('-period').first()
            workload_score = latest_workload.workload_score if latest_workload else pending
            performance_score = latest_perf.performance_score if latest_perf else 50

            score = calculate_allocation_score(pending, overdue, workload_score, performance_score)

            reasons = []
            if pending <= 2:
                reasons.append("low current pending task count")
            if overdue == 0:
                reasons.append("no overdue tasks")
            if latest_perf and latest_perf.performance_score >= 70:
                reasons.append("strong recent performance score")
            if not reasons:
                reasons.append("relatively balanced current workload compared to peers")

            ranked.append({
                'employee': e,
                'pending': pending,
                'overdue': overdue,
                'workload_score': workload_score,
                'performance_score': performance_score,
                'score': score,
                'reason': ", ".join(reasons).capitalize() + ".",
            })

        ranked.sort(key=lambda x: x['score'], reverse=True)
        suggestions = ranked

    return render(request, 'smart_allocation.html', {
        'deptdata': deptdata, 'suggestions': suggestions, 'selected_dept': selected_dept,
    })

def generate_ai_recommendations():
    """
    Creates real AIRecommendation rows from actual current data:
    overdue project tasks and High-risk ML predictions.
    Avoids duplicate rows for the same underlying issue.
    """
    created = 0

    # Overdue-task-driven recommendations, one per affected project
    for p in Project.objects.exclude(status__in=["Completed", "Cancelled"]):
        p_tasks = Task.objects.filter(project=p)
        overdue = p_tasks.exclude(status="Completed").filter(endDate__lt=date.today()).count()
        if overdue > 0:
            text = f"Project \"{p.name}\" has {overdue} overdue task(s) — review assignments and rebalance workload."
            exists = AIRecommendation.objects.filter(project=p, recommendation_type="Overdue Risk", status="Open").exists()
            if not exists:
                AIRecommendation.objects.create(
                    project=p, recommendation_type="Overdue Risk",
                    recommendation_text=text, priority="High" if overdue >= 3 else "Medium",
                )
                created += 1

    # ML-driven recommendations from real EMPLOYEE_RISK predictions
    high_risk_preds = Prediction.objects.filter(prediction_type="EMPLOYEE_RISK", risk_level="High").order_by('-prediction_date')
    seen_employees = set()
    for pred in high_risk_preds:
        if not pred.employee or pred.employee_id in seen_employees:
            continue
        seen_employees.add(pred.employee_id)
        name = pred.employee.user.first_name if pred.employee.user else pred.employee.empid
        text = f"{name} flagged High risk by the trained employee-risk model (confidence {pred.confidence})."
        exists = AIRecommendation.objects.filter(employee=pred.employee, recommendation_type="ML Employee Risk", status="Open").exists()
        if not exists:
            AIRecommendation.objects.create(
                employee=pred.employee, recommendation_type="ML Employee Risk",
                recommendation_text=text, priority="High", related_prediction=pred,
            )
            created += 1

    # ML-driven recommendations from real PROJECT_OUTCOME predictions
    failure_preds = Prediction.objects.filter(prediction_type="PROJECT_OUTCOME", predicted_outcome="Failure Risk").order_by('-prediction_date')
    seen_projects = set()
    for pred in failure_preds:
        if not pred.project or pred.project_id in seen_projects:
            continue
        seen_projects.add(pred.project_id)
        text = f"Project \"{pred.project.name}\" predicted as Failure Risk by the trained model (confidence {pred.confidence})."
        exists = AIRecommendation.objects.filter(project=pred.project, recommendation_type="ML Project Risk", status="Open").exists()
        if not exists:
            AIRecommendation.objects.create(
                project=pred.project, recommendation_type="ML Project Risk",
                recommendation_text=text, priority="High", related_prediction=pred,
            )
            created += 1

    return created


def _feature_dict_changed(stored_input_reference, current_features):
    """Compares a stored Prediction.input_reference string against a freshly
    built feature dict, using the same str() representation used when saving."""
    if not stored_input_reference:
        return True
    return stored_input_reference != str(current_features)


def _build_project_signal(project):
    """Builds one AI Decision Signal for a project from its LATEST real
    Prediction record (no regeneration here — regeneration only happens via
    the explicit 'Run AI Analysis' action, per the no-retrain-on-load rule)."""
    from .ml.feature_engineering import build_project_features
    from .ml.workforce_digital_twin import _project_task_stats, _employee_task_stats
    import json as _json

    prediction = Prediction.objects.filter(
        project=project, prediction_type='PROJECT_OUTCOME'
    ).order_by('-prediction_date').first()

    if not prediction:
        return None

    current_features = build_project_features(project)
    stale = _feature_dict_changed(prediction.input_reference, current_features)

    prob_data = _json.loads(prediction.probabilities) if prediction.probabilities else None
    explanation_data = _json.loads(prediction.explanation) if prediction.explanation else None

    # PROMPT 4 FIX: build_project_features() no longer returns task-derived
    # counts (removed for leakage reasons — see feature_engineering.py).
    # On-screen operational evidence now comes from the Digital Twin's
    # live task-stats helper instead, so this aggregation isn't duplicated.
    task_stats = _project_task_stats(project)

    members = ProjectMember.objects.filter(project=project)
    team_rows = []
    for m in members:
        m_stats = _employee_task_stats(m.employee)
        risk_pred = Prediction.objects.filter(
            employee=m.employee, prediction_type='EMPLOYEE_RISK'
        ).order_by('-prediction_date').first()
        team_rows.append({
            'employee': m.employee, 'role': m.role,
            'assigned': m_stats['assigned'], 'completed': m_stats['completed'],
            'pending': m_stats['pending'], 'overdue': m_stats['overdue'],
            'risk_prediction': risk_pred.predicted_outcome if risk_pred else None,
            'risk_confidence': risk_pred.confidence if risk_pred else None,
        })

    return {
        'type': 'PROJECT_OUTCOME',
        'entity_type': 'project',
        'entity': project,
        'predicted_outcome': prediction.predicted_outcome,
        'confidence': prediction.confidence,
        'risk_level': prediction.risk_level,
        'probabilities': prob_data,
        'drivers': explanation_data,
        'model_version': prediction.model_version,
        'prediction_date': prediction.prediction_date,
        'stale': stale,
        'current_features': current_features,
        'operational_evidence': {
            'total_tasks': task_stats['total'],
            'completed_tasks': task_stats['completed'],
            'pending_tasks': task_stats['pending'],
            'overdue_tasks': task_stats['overdue'],
            'completion_rate': round((task_stats['completion_rate'] or 0) * 100, 1),
            'team_size': current_features['team_size'],
            'days_remaining': current_features['days_remaining'],
        },
        'team': team_rows,
    }


def _build_employee_signal(employee):
    """Builds one AI Decision Signal for an employee from its LATEST real
    EMPLOYEE_RISK Prediction record."""
    from .ml.feature_engineering import build_employee_risk_features
    import json as _json

    prediction = Prediction.objects.filter(
        employee=employee, prediction_type='EMPLOYEE_RISK'
    ).order_by('-prediction_date').first()

    if not prediction:
        return None

    current_features = build_employee_risk_features(employee)
    stale = _feature_dict_changed(prediction.input_reference, current_features) if current_features else True

    prob_data = _json.loads(prediction.probabilities) if prediction.probabilities else None
    explanation_data = _json.loads(prediction.explanation) if prediction.explanation else None

    memberships = ProjectMember.objects.filter(employee=employee, is_active=True)

    return {
        'type': 'EMPLOYEE_RISK',
        'entity_type': 'employee',
        'entity': employee,
        'predicted_outcome': prediction.predicted_outcome,
        'confidence': prediction.confidence,
        'risk_level': prediction.risk_level,
        'probabilities': prob_data,
        'drivers': explanation_data,
        'model_version': prediction.model_version,
        'prediction_date': prediction.prediction_date,
        'stale': stale,
        'current_features': current_features,
        'projects': [m.project for m in memberships],
    }


def _ensure_recommendation_from_signal(signal):
    """
    Creates a real AIRecommendation row FROM an actual high-risk signal,
    with evidence built from that signal's real numbers — never from a
    hardcoded sentence bank. Skips creation if an open recommendation for
    the same entity+prediction date already exists (no duplicate spam).
    """
    if signal['risk_level'] != 'High':
        return

    if signal['entity_type'] == 'project':
        project, employee = signal['entity'], None
        ev = signal['operational_evidence']
        evidence_text = (
            f"{ev['overdue_tasks']} of {ev['total_tasks']} tasks overdue "
            f"({ev['completion_rate']}% complete), {ev['days_remaining']} day(s) remaining, "
            f"team size {ev['team_size']}."
        )
        rec_type = 'PROJECT_RISK_REVIEW'
    else:
        project, employee = None, signal['entity']
        feats = signal['current_features'] or {}
        evidence_text = (
            f"Completion rate {feats.get('completion_rate')}, on-time rate {feats.get('on_time_rate')}, "
            f"overdue tasks {feats.get('tasks_overdue')}, pending {feats.get('pending_count')}, "
            f"workload score {feats.get('workload_score')}."
        )
        rec_type = 'EMPLOYEE_RISK_REVIEW'

    existing = AIRecommendation.objects.filter(
        project=project, employee=employee, recommendation_type=rec_type, status='Open'
    ).first()
    if existing:
        return

    text = (
        f"Model predicted '{signal['predicted_outcome']}' with {signal['confidence']} confidence "
        f"({signal['model_version']}). Evidence: {evidence_text}"
    )
    AIRecommendation.objects.create(
        project=project, employee=employee, recommendation_type=rec_type,
        recommendation_text=text, priority='High', status='Open',
    )


@admin_required
def decision_center(request):
    import json as _json

    # ---- Executive AI Overview: all real counts ----
    active_projects = Project.objects.exclude(status__in=["Completed", "Cancelled"])
    total_predictions = Prediction.objects.count()
    project_predictions = Prediction.objects.filter(prediction_type='PROJECT_OUTCOME').count()
    employee_predictions = Prediction.objects.filter(prediction_type__in=['EMPLOYEE_PERFORMANCE', 'EMPLOYEE_RISK']).count()
    open_recommendations = AIRecommendation.objects.filter(status='Open').count()

    projects_with_prediction = Project.objects.filter(
        id__in=Prediction.objects.filter(prediction_type='PROJECT_OUTCOME').values_list('project_id', flat=True)
    ).distinct().count()
    employees_with_prediction = Employee.objects.filter(
        id__in=Prediction.objects.filter(prediction_type='EMPLOYEE_RISK').values_list('employee_id', flat=True)
    ).distinct().count()

    active_models = ModelVersion.objects.filter(is_active=True)
    last_training = active_models.order_by('-training_date').first()

    # ---- AI Decision Signals: built from real, currently-existing Prediction rows ----
    project_signals = []
    for p in Project.objects.all():
        sig = _build_project_signal(p)
        if sig:
            project_signals.append(sig)
            _ensure_recommendation_from_signal(sig)

    employee_signals = []
    for e in Employee.objects.all():
        sig = _build_employee_signal(e)
        if sig:
            employee_signals.append(sig)
            _ensure_recommendation_from_signal(sig)

    high_risk_signals = [s for s in project_signals + employee_signals if s['risk_level'] == 'High']

    # ---- Workload Decision Intelligence: real, current data ----
    dept_workload = []
    for d in Department.objects.all():
        d_tasks = Task.objects.filter(dept=d).exclude(status="Completed")
        dept_workload.append({
            'dept': d.name,
            'pending': d_tasks.count(),
            'overdue': d_tasks.filter(endDate__lt=date.today()).count(),
        })
    workload_history_exists = WorkloadHistory.objects.exists()

    # ---- Model Trust Panel ----
    model_trust = []
    for mv in ModelVersion.objects.all().order_by('model_name', '-training_date'):
        metrics = _json.loads(mv.metrics) if mv.metrics else {}
        model_trust.append({'mv': mv, 'metrics': metrics})

    recommendations = AIRecommendation.objects.all().order_by('-created_date')

    from .ml.anomaly_detection import detect_workforce_anomalies
    anomaly_summary = detect_workforce_anomalies()

    from .ml.workforce_digital_twin import get_workforce_digital_twin
    from .ml.skill_intelligence import workforce_skill_coverage
    from .ml.explainability import explain_latest_for_project, explain_latest_for_employee

    workforce_twin = get_workforce_digital_twin()
    skill_coverage = workforce_skill_coverage()

    unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False).order_by('-created_date')[:20]

    from .ml.early_warning import generate_early_warnings
    all_warnings = generate_early_warnings()
    future_warnings = all_warnings[:6]
    future_protection_summary = {
        'critical': sum(1 for w in all_warnings if w['severity'] == 'CRITICAL'),
        'warning': sum(1 for w in all_warnings if w['severity'] == 'WARNING'),
        'watch': sum(1 for w in all_warnings if w['severity'] == 'WATCH'),
        'total': len(all_warnings),
    }

    human_ai_signals = {
        'open_blockers': WorkforceInteraction.objects.filter(interaction_type='BLOCKER').exclude(status__in=['RESOLVED', 'CLOSED']).count(),
        'urgent_requests': WorkforceInteraction.objects.filter(priority='URGENT').exclude(status__in=['RESOLVED', 'CLOSED']).count(),
        'pending_assistance': WorkforceInteraction.objects.filter(interaction_type='ASSISTANCE').exclude(status__in=['RESOLVED', 'CLOSED']).count(),
        'recent_concerns': WorkforceInteraction.objects.exclude(status__in=['RESOLVED', 'CLOSED']).order_by('-created_date')[:5],
        'pending_responses': WorkforceInteraction.objects.filter(status='WAITING_FOR_EMPLOYEE').count(),
    }

    from .ml.organizational_brain import build_organizational_memory
    org_memory = build_organizational_memory()

    # Explainable AI panel: trend-aware explanation for the current top
    # high-risk signals only (reuses explainability.py — no logic duplicated).
    explainable_highlights = []
    for s in high_risk_signals[:5]:
        if s['entity_type'] == 'project':
            exp = explain_latest_for_project(s['entity'].id)
        else:
            exp = explain_latest_for_employee(s['entity'].id)
        explainable_highlights.append({'signal': s, 'explanation': exp})

    context = {
        'active_projects_count': active_projects.count(),
        'employees_count': Employee.objects.count(),
        'high_risk_count': len(high_risk_signals),
        'projects_with_prediction': projects_with_prediction,
        'employees_with_prediction': employees_with_prediction,
        'open_recommendations': open_recommendations,
        'active_models_count': active_models.count(),
        'last_training_date': last_training.training_date if last_training else None,
        'total_predictions': total_predictions,
        'project_predictions': project_predictions,
        'employee_predictions': employee_predictions,
        'project_signals': project_signals,
        'employee_signals': employee_signals,
        'high_risk_signals': high_risk_signals,
        'dept_workload': dept_workload,
        'workload_history_exists': workload_history_exists,
        'model_trust': model_trust,
        'recommendations': recommendations,
        'anomaly_summary': anomaly_summary,
        'workforce_twin': workforce_twin,
        'skill_coverage': skill_coverage,
        'unread_notifications': unread_notifications,
        'unread_notification_count': unread_notifications.count(),
        'explainable_highlights': explainable_highlights,
        'future_warnings': future_warnings,
        'future_protection_summary': future_protection_summary,
        'human_ai_signals': human_ai_signals,
        'org_memory_summary': org_memory['evaluation_summary'],
        'org_recent_decisions': org_memory['decisions'][:5],
        'dept_workload_labels': json.dumps([d['dept'] for d in dept_workload]),
        'dept_workload_pending': json.dumps([d['pending'] for d in dept_workload]),
        'dept_workload_overdue': json.dumps([d['overdue'] for d in dept_workload]),
        'risk_dist_labels': json.dumps(['High', 'Medium', 'Low']),
        'risk_dist_counts': json.dumps([
            sum(1 for s in project_signals + employee_signals if s['risk_level'] == 'High'),
            sum(1 for s in project_signals + employee_signals if s['risk_level'] == 'Medium'),
            sum(1 for s in project_signals + employee_signals if s['risk_level'] not in ['High', 'Medium']),
        ]),
    }
    return render(request, 'decision_center.html', context)


@admin_required
def refresh_ai_analysis(request):
    """
    'Run AI Analysis' action: regenerates predictions from CURRENT database
    state using the existing trained models — does NOT retrain any model.
    Then regenerates real AI recommendations and admin overdue-project
    notifications from that same refreshed data. Both generate_ai_recommendations()
    and the notification loop below are idempotent (they check for an existing
    Open/unread record for the same project/employee before creating a new one),
    so repeated refreshes do not spam duplicates.
    Leave/status alerts are NOT rebuilt here — they are created once, at the
    real moment an employee reports them, in emp_report_status().
    """
    from .ml.prediction_service import predict_project_outcome, predict_employee_risk, predict_employee_performance
    for p in Project.objects.all():
        predict_project_outcome(p, save=True)
    for e in Employee.objects.all():
        predict_employee_risk(e, save=True)
        predict_employee_performance(e, save=True)

    generate_ai_recommendations()

    admin_users = User.objects.filter(is_staff=True)
    overdue_project_count = 0
    for p in Project.objects.exclude(status__in=["Completed", "Cancelled"]):
        overdue = Task.objects.filter(project=p).exclude(status="Completed").filter(endDate__lt=date.today()).count()
        if overdue > 0:
            overdue_project_count += 1
            for admin_user in admin_users:
                Notification.objects.get_or_create(
                    recipient=admin_user, category='PROJECT_RISK',
                    related_project=p, is_read=False,
                    defaults={
                        'title': 'Project at risk',
                        'message': f'Project "{p.name}" has {overdue} overdue task(s) — may miss deadline.',
                    },
                )

    from .ml.workforce_events import record_event
    record_event(
        'AI_ANALYSIS_REFRESHED',
        f'Admin refreshed AI analysis — {Project.objects.count()} projects and {Employee.objects.count()} employees re-scored.',
        actor=request.user, severity='warning' if overdue_project_count else 'info',
        metadata={'overdue_project_count': overdue_project_count},
    )

    # Prompt 9: surface genuinely CRITICAL early warnings as deduplicated
    # notifications. get_or_create on (recipient, category, related_*,
    # is_read=False) means an already-open alert for the same real
    # situation is never duplicated by repeated refreshes.
    from .ml.early_warning import generate_early_warnings
    for w in generate_early_warnings():
        if w['severity'] != 'CRITICAL':
            continue
        category = 'EMPLOYEE_RISK' if w['entity_type'] == 'employee' else 'PROJECT_RISK'
        related_kwargs = {'related_employee_id': w['entity_id']} if w['entity_type'] == 'employee' else {'related_project_id': w['entity_id']}
        for admin_user in admin_users:
            _, created = Notification.objects.get_or_create(
                recipient=admin_user, category=category, is_read=False, **related_kwargs,
                defaults={
                    'title': f"Early warning: {w['signal_type'].replace('_', ' ').title()}",
                    'message': f"{w['entity_name']} — " + " ".join(w['evidence']),
                },
            )
            if created:
                record_event('AI_WARNING_CREATED', f"Early warning generated for {w['entity_name']}: {w['signal_type']}.",
                             actor=request.user, severity='critical',
                             **({'employee_id': w['entity_id']} if w['entity_type'] == 'employee' else {'project_id': w['entity_id']}))

    messages.success(request, "AI analysis refreshed from current data.")
    return redirect('decision_center')


# ==================================================
# WORKFORCE DIGITAL TWIN — read-only JSON endpoints (Prompt 3)
# Admin-only. Reuses Employee/ml/workforce_digital_twin.py — no logic
# duplicated here, this is just the HTTP wrapper.
# ==================================================

@admin_required
def api_employee_digital_twin(request, eid):
    from .ml.workforce_digital_twin import get_employee_digital_twin
    data = get_employee_digital_twin(eid)
    status = 404 if 'error' in data else 200
    return JsonResponse(data, status=status)


@admin_required
def api_project_digital_twin(request, pid):
    from .ml.workforce_digital_twin import get_project_digital_twin
    data = get_project_digital_twin(pid)
    status = 404 if 'error' in data else 200
    return JsonResponse(data, status=status)


@admin_required
def api_workforce_digital_twin(request):
    from .ml.workforce_digital_twin import get_workforce_digital_twin
    return JsonResponse(get_workforce_digital_twin())


@login_required(login_url='/login_admin/')
def api_mark_notification_read(request, notif_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'method_not_allowed'}, status=405)
    try:
        notif = Notification.objects.get(id=notif_id, recipient=request.user)
    except Notification.DoesNotExist:
        return JsonResponse({'error': 'not_found'}, status=404)
    notif.is_read = True
    notif.save()
    return JsonResponse({'status': 'ok', 'notification_id': notif.id})


# ==================================================
# ADVANCED INTELLIGENCE ENGINE — read-only JSON endpoints (Prompt 4)
# Admin-only. Each wraps a reusable Employee/ml/*.py service — no logic
# duplicated here, this is just the HTTP layer.
# ==================================================

@admin_required
def api_workforce_anomalies(request):
    from .ml.anomaly_detection import detect_workforce_anomalies
    return JsonResponse(detect_workforce_anomalies())


@admin_required
def api_employee_skill_profile(request, eid):
    from .ml.skill_intelligence import build_employee_skill_profile
    data = build_employee_skill_profile(eid)
    return JsonResponse(data, status=404 if 'error' in data else 200)


@admin_required
def api_project_requirement_profile(request, pid):
    from .ml.skill_intelligence import build_project_requirement_profile
    data = build_project_requirement_profile(pid)
    return JsonResponse(data, status=404 if 'error' in data else 200)


@admin_required
def api_skill_match(request, eid, pid):
    from .ml.skill_intelligence import match_employee_to_project
    data = match_employee_to_project(eid, pid)
    return JsonResponse(data, status=404 if 'error' in data else 200)


@admin_required
def api_workforce_skill_coverage(request):
    from .ml.skill_intelligence import workforce_skill_coverage
    return JsonResponse(workforce_skill_coverage())


@admin_required
def api_explain_employee_risk(request, eid):
    from .ml.explainability import explain_latest_for_employee
    return JsonResponse(explain_latest_for_employee(eid))


@admin_required
def api_explain_project_outcome(request, pid):
    from .ml.explainability import explain_latest_for_project
    return JsonResponse(explain_latest_for_project(pid))


# ==================================================
# WHAT-IF DECISION SIMULATOR (Prompt 5) — Admin-only
# ==================================================

def _json_safe(obj):
    """Defensive serialization: converts any numpy scalar the reused ML
    pipeline might hand back (e.g. numpy.float64) into a plain Python type
    before JsonResponse encodes it. Does not alter any real value."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, 'item') and callable(getattr(obj, 'item')):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return obj


@admin_required
def what_if_simulator_page(request):
    return render(request, 'what_if_simulator.html', {
        'employees': Employee.objects.select_related('user').all(),
        'projects': Project.objects.all(),
        'tasks': Task.objects.select_related('emp', 'project').exclude(status="Completed"),
    })


@admin_required
def api_whatif_simulate(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'method_not_allowed'}, status=405)

    import json as _json_lib
    try:
        payload = _json_lib.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid_json'}, status=400)

    scenario_type = payload.get('scenario_type')
    params = payload.get('params', {})
    if not scenario_type:
        return JsonResponse({'error': 'missing_scenario_type'}, status=400)

    from .ml.what_if_simulator import run_simulation
    result = run_simulation(scenario_type, params)
    result = _json_safe(result)
    status = 400 if 'error' in result else 200

    # Best-effort scenario history — a storage hiccup must never block the response.
    try:
        WhatIfScenario.objects.create(
            scenario_type=scenario_type,
            input_parameters=_json_lib.dumps(params),
            result_summary=_json_lib.dumps(
                result if 'error' in result else {
                    'description': result.get('description'),
                    'absolute_difference': result.get('absolute_difference'),
                    'percentage_difference': result.get('percentage_difference'),
                    'warnings': result.get('warnings'),
                    'recommendations': result.get('recommendations'),
                }
            ),
            created_by=request.user,
        )
    except Exception:
        pass

    if 'error' not in result:
        try:
            from .ml.workforce_events import record_event
            record_event(
                'WHATIF_SIMULATION_RUN',
                f'Admin ran a {scenario_type} what-if simulation: {result.get("description", "")}'[:300],
                actor=request.user,
            )
        except Exception:
            pass

    return JsonResponse(result, status=status)


@admin_required
def update_recommendation_status(request, rid):
    rec = AIRecommendation.objects.get(id=rid)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ['Open', 'Acknowledged', 'Resolved']:
            rec.status = new_status
            rec.save()
            messages.success(request, "Recommendation status updated.")
    return redirect('decision_center')


# ==================================================
# WORKFORCE OBSERVATORY (Prompt 8) — Admin-only
# Reuses workforce_digital_twin, anomaly_detection, and the new
# workforce_events log. No calculation is duplicated here.
# ==================================================

def _workforce_pulse_data():
    from .ml.workforce_digital_twin import get_workforce_digital_twin
    from .ml.anomaly_detection import detect_workforce_anomalies
    from .ml.workforce_events import recent_events

    twin = get_workforce_digital_twin()
    anomalies = detect_workforce_anomalies()
    events = recent_events(limit=25)
    open_alerts = Notification.objects.filter(is_read=False).count()

    return {
        'workforce_twin': twin,
        'anomaly_summary': anomalies,
        'recent_events': events,
        'open_alerts': open_alerts,
        'active_projects': Project.objects.exclude(status__in=["Completed", "Cancelled"]).count(),
        'active_tasks': Task.objects.exclude(status="Completed").count(),
        'pending_tasks': Task.objects.exclude(status="Completed").filter(endDate__gte=date.today()).count(),
        'overdue_tasks': Task.objects.exclude(status="Completed").filter(endDate__lt=date.today()).count(),
        'completed_tasks': Task.objects.filter(status="Completed").count(),
    }


@admin_required
def workforce_observatory(request):
    data = _workforce_pulse_data()
    projects = Project.objects.exclude(status__in=["Completed", "Cancelled"]).select_related('dept')[:12]
    from .ml.early_warning import generate_early_warnings
    future_warnings = generate_early_warnings()
    from .ml.organizational_brain import build_learning_signals
    learning_signals = build_learning_signals()
    context = {
        **data,
        'projects': projects,
        'last_event_id': data['recent_events'][0].id if data['recent_events'] else 0,
        'active_model_count': sum(1 for v in data['workforce_twin']['active_models'].values() if v),
        'future_warning_count': len(future_warnings),
        'future_workload_signal_count': sum(1 for w in future_warnings if w['signal_type'] in ('WORKLOAD_PRESSURE', 'ML_WORKLOAD_FORECAST')),
        'future_project_warning_count': sum(1 for w in future_warnings if w['entity_type'] == 'project'),
        'new_blockers_count': WorkforceInteraction.objects.filter(interaction_type='BLOCKER', status='OPEN').count(),
        'urgent_request_count': WorkforceInteraction.objects.filter(priority='URGENT').exclude(status__in=['RESOLVED', 'CLOSED']).count(),
        'pending_employee_response_count': WorkforceInteraction.objects.filter(status='WAITING_FOR_EMPLOYEE').count(),
        'learning_signal_count': len(learning_signals),
        'learning_signals_sample': learning_signals[:3],
    }
    return render(request, 'workforce_observatory.html', context)


@admin_required
def api_workforce_pulse(request):
    data = _workforce_pulse_data()
    payload = {
        'current_state': {
            'employees': data['workforce_twin']['employee_count'],
            'active_projects': data['active_projects'],
            'active_tasks': data['active_tasks'],
            'pending_tasks': data['pending_tasks'],
            'overdue_tasks': data['overdue_tasks'],
            'completed_tasks': data['completed_tasks'],
        },
        'recent_events': [
            {'id': e.id, 'type': e.event_type, 'description': e.description,
             'severity': e.severity, 'time': e.created_date.strftime('%H:%M') if e.created_date else None}
            for e in data['recent_events']
        ],
        'alerts': data['open_alerts'],
        'active_models': data['workforce_twin']['active_models'],
        'anomaly_count': data['anomaly_summary'].get('anomaly_count') if data['anomaly_summary']['status'] == 'OK' else None,
        'anomaly_status': data['anomaly_summary']['status'],
    }
    return JsonResponse(_json_safe(payload))


@admin_required
def api_workforce_events(request):
    """Polling endpoint for the Observatory's Live Pulse (Part 14). Accepts
    ?since_id=N and returns only real events created after it."""
    from .ml.workforce_events import events_since
    since_id = request.GET.get('since_id')
    since_id = int(since_id) if since_id and since_id.isdigit() else None
    events = events_since(since_id=since_id, limit=30)
    return JsonResponse({'events': [
        {'id': e.id, 'type': e.event_type, 'description': e.description, 'severity': e.severity,
         'time': e.created_date.strftime('%H:%M') if e.created_date else None}
        for e in events
    ]})


@admin_required
def project_intelligence(request, pid):
    """Distinct from the existing project_detail page: this composes the
    Digital Twin + real event Timeline for investigation, rather than
    re-deriving stats inline (project_detail's own approach, unchanged)."""
    from .ml.workforce_digital_twin import get_project_digital_twin
    from .ml.explainability import explain_latest_for_project
    from .ml.workforce_events import recent_events

    twin = get_project_digital_twin(pid)
    if 'error' in twin:
        messages.error(request, "Project not found.")
        return redirect('admin_projects')

    explanation = explain_latest_for_project(pid)
    timeline = recent_events(limit=40, project=Project.objects.get(id=pid))

    context = {
        'twin': twin,
        'explanation': explanation,
        'timeline': timeline,
        'project_id': pid,
    }
    return render(request, 'project_intelligence.html', context)


@admin_required
def employee_intelligence(request, eid):
    """Distinct from admin_employee_detail: composes Digital Twin + Skill
    Intelligence + Anomaly status + real event Timeline for investigation."""
    from .ml.workforce_digital_twin import get_employee_digital_twin
    from .ml.skill_intelligence import build_employee_skill_profile
    from .ml.anomaly_detection import get_employee_anomaly_status
    from .ml.explainability import explain_latest_for_employee
    from .ml.workforce_events import recent_events

    twin = get_employee_digital_twin(eid)
    if 'error' in twin:
        messages.error(request, "Employee not found.")
        return redirect('view_employee')

    skill_profile = build_employee_skill_profile(eid)
    anomaly_status = get_employee_anomaly_status(eid)
    risk_explanation = explain_latest_for_employee(eid, 'EMPLOYEE_RISK')
    perf_explanation = explain_latest_for_employee(eid, 'EMPLOYEE_PERFORMANCE')
    timeline = recent_events(limit=40, employee=Employee.objects.get(id=eid))

    context = {
        'twin': twin,
        'skill_profile': skill_profile,
        'anomaly_status': anomaly_status,
        'risk_explanation': risk_explanation,
        'perf_explanation': perf_explanation,
        'timeline': timeline,
        'employee_id': eid,
    }
    return render(request, 'employee_intelligence.html', context)


@admin_required
def task_intelligence(request, task_id):
    try:
        task = Task.objects.select_related('emp', 'project', 'dept').get(id=task_id)
    except Task.DoesNotExist:
        messages.error(request, "Task not found.")
        return redirect('admin_view_new_task')

    tracking_history = TaskTracking.objects.filter(taskId=task).order_by('-updationDate')
    timeline = list(WorkforceEvent.objects.filter(task=task).order_by('-created_date')[:30])

    risk_available = False
    risk_label, risk_score = None, None
    if task.status != "Completed":
        risk_label, risk_score = calculate_task_risk(task)
        risk_available = True

    context = {
        'task': task,
        'tracking_history': tracking_history,
        'timeline': timeline,
        'risk_available': risk_available,
        'risk_label': risk_label,
        'risk_score': risk_score,
    }
    return render(request, 'task_intelligence.html', context)


@admin_required
def whatif_analysis(request):
    from .ml.prediction_service import whatif_project_outcome
    projects = Project.objects.all()
    result = None
    selected_project = None

    if request.method == 'POST':
        pid = request.POST.get('project_id')
        selected_project = Project.objects.get(id=pid)
        overrides = {
            'progress': int(request.POST.get('progress', selected_project.progress or 0)),
            'pending_tasks': int(request.POST.get('pending_tasks', 0)),
            'overdue_tasks': int(request.POST.get('overdue_tasks', 0)),
            'completion_rate': float(request.POST.get('completion_rate', 0)),
        }
        result = whatif_project_outcome(selected_project, overrides)

    return render(request, 'whatif_analysis.html', {
        'projects': projects, 'result': result, 'selected_project': selected_project,
    })

@employee_required
def emp_report_status(request):
    emp = Employee.objects.get(user=request.user)
    if request.method == 'POST':
        reason = request.POST['reason']
        note = request.POST.get('note', '')
        ls = LeaveStatus.objects.create(employee=emp, reason=reason, note=note)
        name = emp.user.first_name if emp.user else emp.empid
        msg = f"{name} reported: {ls.get_reason_display()}" + (f' — "{note}"' if note else '')
        for admin_user in User.objects.filter(is_staff=True):
            Notification.objects.create(
                recipient=admin_user, category='LEAVE_STATUS', related_employee=emp,
                title="Employee status report", message=msg,
            )
        from .ml.workforce_events import record_event
        record_event('LEAVE_STATUS_CHANGED', msg, actor=request.user, employee=emp, severity='warning')
        messages.success(request, "Status reported to admin.")
        return redirect('emp_home')
    my_statuses = LeaveStatus.objects.filter(employee=emp).order_by('-date')[:10]
    return render(request, 'emp_report_status.html', {'my_statuses': my_statuses})

def calculate_task_risk(task):
    """AI-style rule-based risk scoring: returns (risk_label, risk_score 0-100)."""
    score = 0

    # Factor 1: Priority weight
    priority = (task.priority or "").lower()
    if priority == "high":
        score += 35
    elif priority == "medium":
        score += 20
    else:
        score += 5

    # Factor 2: Days remaining until deadline
    if task.endDate:
        days_left = (task.endDate.date() - date.today()).days if hasattr(task.endDate, 'date') else (task.endDate - date.today()).days
        if days_left < 0:
            score += 40  # already overdue
        elif days_left <= 2:
            score += 30
        elif days_left <= 7:
            score += 15
        else:
            score += 5
    else:
        score += 15

    # Factor 3: Assigned employee's historical completion rate
    if task.emp:
        emp_tasks = Task.objects.filter(emp=task.emp)
        total = emp_tasks.count()
        completed = emp_tasks.filter(status="Completed").count()
        completion_rate = (completed / total) if total else 1
        score += round((1 - completion_rate) * 25)

    # Factor 4: Current status
    if task.status == "Completed":
        score = 0
    elif task.status == "Inprogress":
        score = max(score - 10, 0)

    score = min(score, 100)

    if score >= 60:
        label = "High"
    elif score >= 30:
        label = "Medium"
    else:
        label = "Low"
    return label, score


def dropdown(request):
    data=Employee.objects.filter(dept__id=request.GET['deptid'])
    dict = {'id':[], 'name':[]}
    for i in data:
        dict['id'].append(i.id)
        dict['name'].append(i.user.first_name)
    return JsonResponse(dict)

def Login_Employee(request):
    if request.method == "POST":
        u = request.POST['uname']
        p = request.POST['pwd']
        user = authenticate(username=u, password=p)
        if user is not None and not user.is_staff and Employee.objects.filter(user=user).exists():
            login(request, user)
            messages.success(request, "Logged in Successfully")
            return redirect('emp_home')
        messages.error(request, "Invalid employee credentials.")
    return render(request, 'emp_login.html')

def Logout(request):
    logout(request)
    return redirect('/')
@employee_required
def emp_new_task(request):
    emp=Employee.objects.get(user=request.user)
    task=Task.objects.filter(emp=emp,status="Not Updated Yet")
    return render(request,'emp_new_task.html',locals())
@employee_required
def emp_inprogress_task(request):
    emp=Employee.objects.get(user=request.user)
    task=Task.objects.filter(emp=emp,status="Inprogress")
    return render(request,'emp_inprogress_task.html',locals())
@employee_required
def emp_completed_task(request):
    emp=Employee.objects.get(user=request.user)
    task=Task.objects.filter(emp=emp,status="Completed")
    return render(request,'emp_completed_task.html',locals())
@employee_required
def emp_all_task(request):
    emp=Employee.objects.get(user=request.user)
    task=Task.objects.filter(emp=emp)
    return render(request,'emp_all_task.html',locals())


# ==================================================
# EMPLOYEE WORKSPACE — Prompt 8, Parts 11-13, 16
# Every employee here is derived strictly from request.user — never from
# a URL/POST-supplied ID, closing the IDOR path explicitly called out
# in Part 21.
# ==================================================

@employee_required
def my_work_pulse(request):
    from .ml.workforce_digital_twin import get_employee_digital_twin
    emp = Employee.objects.get(user=request.user)
    twin = get_employee_digital_twin(emp.id)
    recommendations = AIRecommendation.objects.filter(employee=emp).order_by('-created_date')[:5]
    warnings = Notification.objects.filter(recipient=request.user, is_read=False).order_by('-created_date')[:10]
    return render(request, 'my_work_pulse.html', {
        'twin': twin, 'recommendations': recommendations, 'warnings': warnings,
    })


@employee_required
def my_changes(request):
    """Real change detection: compares against a 'last seen' marker stored
    in this employee's session. First-ever visit has no baseline, so it
    honestly says so rather than guessing."""
    from .ml.workforce_events import events_since
    emp = Employee.objects.get(user=request.user)
    last_seen = request.session.get('my_changes_last_seen')

    changes = []
    has_baseline = bool(last_seen)
    if has_baseline:
        changes = events_since(since_time=last_seen, employee=emp, limit=30)

    request.session['my_changes_last_seen'] = timezone.now().isoformat()
    return render(request, 'my_changes.html', {
        'changes': changes, 'has_baseline': has_baseline,
    })


@employee_required
def my_activity(request):
    from .ml.workforce_events import recent_events
    emp = Employee.objects.get(user=request.user)
    filter_type = request.GET.get('filter', 'all')

    type_groups = {
        'tasks': ['TASK_CREATED', 'TASK_ASSIGNED', 'TASK_UPDATED', 'TASK_COMPLETED', 'TASK_REOPENED', 'TASK_OVERDUE'],
        'projects': ['PROJECT_UPDATED', 'PROJECT_MEMBER_ADDED', 'PROJECT_MEMBER_REMOVED'],
        'ai': ['AI_ANALYSIS_REFRESHED', 'AI_WARNING_CREATED', 'WHATIF_SIMULATION_RUN'],
        'admin': ['EMPLOYEE_STATUS_CHANGED', 'LEAVE_STATUS_CHANGED'],
        'notifications': ['NOTIFICATION_CREATED'],
    }
    events = WorkforceEvent.objects.filter(employee=emp)
    if filter_type in type_groups:
        events = events.filter(event_type__in=type_groups[filter_type])
    events = events.order_by('-created_date')[:100]

    return render(request, 'my_activity.html', {'events': events, 'active_filter': filter_type})


@employee_required
def api_my_activity(request):
    """Employee-only. Identity comes ONLY from request.user — no employee
    ID is ever accepted from the client, by design (Part 16/21)."""
    from .ml.workforce_events import events_since
    emp = Employee.objects.get(user=request.user)
    since_id = request.GET.get('since_id')
    since_id = int(since_id) if since_id and since_id.isdigit() else None
    events = events_since(since_id=since_id, employee=emp, limit=30)
    return JsonResponse({'events': [
        {'id': e.id, 'type': e.event_type, 'description': e.description,
         'time': e.created_date.strftime('%H:%M') if e.created_date else None}
        for e in events
    ]})


# ==================================================
# FUTURE PROTECTION & PREVENTION INTELLIGENCE (Prompt 9)
# Reuses early_warning.py, workforce_digital_twin, anomaly_detection,
# prediction_service, and the existing What-If Simulator. No new model —
# warnings are computed live; Notification is reused for dedup'd alerting.
# ==================================================

@admin_required
def admin_what_changed(request):
    """Org-wide BEFORE -> NOW -> CHANGE view. Reuses generate_early_warnings()
    for the 'change detected' narrative (its evidence strings already state
    real before/after numbers) rather than building a second change-detection
    mechanism."""
    from .ml.early_warning import generate_early_warnings
    from .ml.workforce_events import recent_events
    warnings = generate_early_warnings()
    events = recent_events(limit=40)
    return render(request, 'admin_what_changed.html', {'warnings': warnings, 'events': events})


@admin_required
def prevention_center(request):
    from .ml.early_warning import generate_early_warnings
    warnings = generate_early_warnings()

    situations = {}
    for w in warnings:
        situations.setdefault(w['signal_type'], []).append(w)
    emerging_situations = [{'signal_type': k, 'count': len(v), 'sample': v[0]} for k, v in situations.items()]

    return render(request, 'prevention_center.html', {
        'warnings': warnings,
        'emerging_situations': emerging_situations,
        'critical_count': sum(1 for w in warnings if w['severity'] == 'CRITICAL'),
        'warning_count': sum(1 for w in warnings if w['severity'] == 'WARNING'),
        'watch_count': sum(1 for w in warnings if w['severity'] == 'WATCH'),
    })


@admin_required
def future_scenario(request, entity_type, entity_id):
    from .ml.early_warning import generate_early_warnings
    from .ml.prediction_service import get_model_metadata, predict_workload_forecast
    from .ml.workforce_digital_twin import _employee_task_stats, _project_task_stats

    if entity_type == 'employee':
        try:
            entity = Employee.objects.get(id=entity_id)
        except Employee.DoesNotExist:
            messages.error(request, "Employee not found.")
            return redirect('prevention_center')
        name = entity.user.first_name if entity.user else entity.empid
        past_history = list(WorkloadHistory.objects.filter(employee=entity).order_by('-period')[:5])
        current_stats = _employee_task_stats(entity)
        warnings = generate_early_warnings(employee=entity)

        forecast = {'available': False, 'status': 'MODEL_NOT_READY'}
        meta = get_model_metadata('workload_forecast')
        if meta:
            result = predict_workload_forecast(entity, save=False)
            if result.get('status') == 'ok':
                forecast = {'available': True, 'predicted_workload_score': result['predicted_workload_score'],
                            'model_version': result['model_version'], 'based_on_period': result['based_on_period']}
            else:
                forecast = {'available': False, 'status': 'INSUFFICIENT_DATA', 'message': result.get('message')}
        whatif_link = f"/what_if_simulator/?scenario=WORKLOAD_SCENARIO&entity_type=employee&entity_id={entity.id}"
    elif entity_type == 'project':
        try:
            entity = Project.objects.get(id=entity_id)
        except Project.DoesNotExist:
            messages.error(request, "Project not found.")
            return redirect('prevention_center')
        name = entity.name
        past_history = []
        current_stats = _project_task_stats(entity)
        warnings = generate_early_warnings(project=entity)

        forecast = {'available': False, 'status': 'MODEL_NOT_READY'}
        meta = get_model_metadata('project_outcome')
        if meta:
            pred = Prediction.objects.filter(project=entity, prediction_type='PROJECT_OUTCOME').order_by('-prediction_date').first()
            if pred:
                forecast = {'available': True, 'predicted_outcome': pred.predicted_outcome,
                            'confidence': pred.confidence, 'model_version': pred.model_version}
            else:
                forecast = {'available': False, 'status': 'INSUFFICIENT_DATA'}
        whatif_link = f"/what_if_simulator/?scenario=PROJECT_MEMBERSHIP_CHANGE&project_id={entity.id}"
    else:
        messages.error(request, "Unknown entity type.")
        return redirect('prevention_center')

    return render(request, 'future_scenario.html', {
        'entity_type': entity_type, 'entity_id': entity_id, 'name': name,
        'past_history': past_history, 'current_stats': current_stats,
        'warnings': warnings, 'forecast': forecast, 'whatif_link': whatif_link,
    })


@employee_required
def my_prevention(request):
    from .ml.early_warning import generate_early_warnings
    emp = Employee.objects.get(user=request.user)
    warnings = generate_early_warnings(employee=emp)
    return render(request, 'my_prevention.html', {'warnings': warnings})


@employee_required
def my_future(request):
    """Part 12 — 'What Could Happen?'. Self-scoped only."""
    from .ml.early_warning import generate_early_warnings
    from .ml.prediction_service import get_model_metadata, predict_workload_forecast
    from .ml.workforce_digital_twin import _employee_task_stats
    emp = Employee.objects.get(user=request.user)
    stats = _employee_task_stats(emp)
    upcoming = Task.objects.filter(emp=emp).exclude(status="Completed").filter(
        endDate__gte=date.today(), endDate__lte=date.today() + timedelta(days=7)
    ).order_by('endDate')
    warnings = generate_early_warnings(employee=emp)

    forecast = {'available': False, 'status': 'MODEL_NOT_READY'}
    if get_model_metadata('workload_forecast'):
        result = predict_workload_forecast(emp, save=False)
        if result.get('status') == 'ok':
            forecast = {'available': True, 'predicted_workload_score': result['predicted_workload_score']}
        else:
            forecast = {'available': False, 'status': 'INSUFFICIENT_DATA'}

    return render(request, 'my_future.html', {
        'stats': stats, 'upcoming': upcoming, 'warnings': warnings, 'forecast': forecast,
    })


# ==================================================
# HUMAN-AI WORKFORCE INTERACTION (Prompt 10)
# Reuses Notification + WorkforceEvent for alerting/history; reuses
# interaction_intelligence.py for classification — no duplicated logic.
# ==================================================

VALID_TRANSITIONS = {
    'OPEN': {'ACKNOWLEDGED', 'CLOSED'},
    'ACKNOWLEDGED': {'IN_PROGRESS', 'WAITING_FOR_EMPLOYEE', 'CLOSED'},
    'IN_PROGRESS': {'WAITING_FOR_EMPLOYEE', 'RESOLVED', 'CLOSED'},
    'WAITING_FOR_EMPLOYEE': {'IN_PROGRESS', 'RESOLVED', 'CLOSED'},
    'RESOLVED': {'CLOSED'},
    'CLOSED': set(),
}


def _create_interaction(request, interaction_type, subject, message, related_project_id, related_task_id):
    """Shared creation logic for report_blocker / request_clarification /
    request_assistance. Employee identity comes ONLY from request.user;
    related project/task are validated against what this employee is
    actually permitted to see."""
    from .ml.interaction_intelligence import classify_interaction_text
    from .ml.workforce_events import record_event

    emp = Employee.objects.get(user=request.user)

    related_project = None
    if related_project_id:
        related_project = ProjectMember.objects.filter(
            employee=emp, project_id=related_project_id, is_active=True
        ).select_related('project').first()
        related_project = related_project.project if related_project else None

    related_task = None
    if related_task_id:
        related_task = Task.objects.filter(id=related_task_id, emp=emp).first()

    classification = classify_interaction_text(f"{subject} {message}")

    interaction = WorkforceInteraction.objects.create(
        employee=emp, interaction_type=interaction_type, subject=subject[:200], message=message,
        related_project=related_project, related_task=related_task,
        ai_category=classification['category'], ai_summary=classification['explanation'],
        ai_confidence=classification['confidence'], priority=classification['priority'],
    )

    record_event('INTERACTION_CREATED',
                  f'{emp.empid} submitted a {interaction.get_interaction_type_display()}: "{subject}".',
                  actor=request.user, employee=emp, project=related_project, task=related_task,
                  interaction=interaction,
                  severity='warning' if classification['priority'] != 'NORMAL' else 'info')

    category_label = classification['category'].replace('_', ' ').title()
    for admin_user in User.objects.filter(is_staff=True):
        Notification.objects.create(
            recipient=admin_user, category='GENERAL', related_employee=emp,
            title=f"New {interaction.get_interaction_type_display()}: {subject}",
            message=f"{emp.empid} — AI category: {category_label} ({classification['priority']}). {message[:150]}",
        )
    return interaction


@employee_required
def report_blocker(request):
    emp = Employee.objects.get(user=request.user)
    if request.method == "POST":
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()
        related_project_id = request.POST.get('related_project') or None
        related_task_id = request.POST.get('related_task') or None
        if subject and message:
            _create_interaction(request, 'BLOCKER', subject, message, related_project_id, related_task_id)
            messages.success(request, "Blocker reported to admin.")
            return redirect('my_interactions')
        messages.error(request, "Please provide both a subject and a description.")

    my_projects = Project.objects.filter(projectmember__employee=emp, projectmember__is_active=True).distinct()
    my_tasks = Task.objects.filter(emp=emp).exclude(status="Completed")
    return render(request, 'report_blocker.html', {'my_projects': my_projects, 'my_tasks': my_tasks})


@employee_required
def request_clarification(request):
    emp = Employee.objects.get(user=request.user)
    if request.method == "POST":
        task_ref = request.POST.get('task_reference', '').strip()
        question = request.POST.get('question', '').strip()
        related_task_id = request.POST.get('related_task') or None
        if question:
            subject = f"Clarification: {task_ref}" if task_ref else "Clarification request"
            _create_interaction(request, 'CLARIFICATION', subject, question, None, related_task_id)
            messages.success(request, "Clarification request sent to admin.")
            return redirect('my_interactions')
        messages.error(request, "Please enter your question.")

    my_tasks = Task.objects.filter(emp=emp).exclude(status="Completed")
    return render(request, 'request_clarification.html', {'my_tasks': my_tasks})


@employee_required
def request_assistance(request):
    emp = Employee.objects.get(user=request.user)
    if request.method == "POST":
        category = request.POST.get('category', 'Other')
        description = request.POST.get('description', '').strip()
        related_project_id = request.POST.get('related_project') or None
        related_task_id = request.POST.get('related_task') or None
        if description:
            subject = f"{category} Assistance"
            _create_interaction(request, 'ASSISTANCE', subject, description, related_project_id, related_task_id)
            messages.success(request, "Assistance request sent to admin.")
            return redirect('my_interactions')
        messages.error(request, "Please describe what you need help with.")

    my_projects = Project.objects.filter(projectmember__employee=emp, projectmember__is_active=True).distinct()
    my_tasks = Task.objects.filter(emp=emp).exclude(status="Completed")
    return render(request, 'request_assistance.html', {'my_projects': my_projects, 'my_tasks': my_tasks})


@employee_required
def my_interactions(request):
    emp = Employee.objects.get(user=request.user)
    interactions = WorkforceInteraction.objects.filter(employee=emp)
    groups = {
        'open': interactions.filter(status__in=['OPEN', 'ACKNOWLEDGED']),
        'waiting_for_admin': interactions.filter(status='IN_PROGRESS'),
        'waiting_for_me': interactions.filter(status='WAITING_FOR_EMPLOYEE'),
        'resolved': interactions.filter(status='RESOLVED'),
        'closed': interactions.filter(status='CLOSED'),
    }
    return render(request, 'my_interactions.html', groups)


@employee_required
def my_interaction_detail(request, interaction_id):
    """IDOR-safe: the ownership filter is IN the query itself, so another
    employee's interaction simply does not exist from this user's view."""
    try:
        interaction = WorkforceInteraction.objects.get(id=interaction_id, employee__user=request.user)
    except WorkforceInteraction.DoesNotExist:
        messages.error(request, "Request not found.")
        return redirect('my_interactions')

    if request.method == "POST" and interaction.status not in ('RESOLVED', 'CLOSED'):
        response_text = request.POST.get('employee_response', '').strip()
        if response_text:
            interaction.employee_response = response_text
            interaction.status = 'IN_PROGRESS' if interaction.status == 'WAITING_FOR_EMPLOYEE' else interaction.status
            interaction.save()

            from .ml.workforce_events import record_event
            record_event('INTERACTION_RESPONSE', f'{interaction.employee.empid} responded: "{response_text[:100]}"',
                         actor=request.user, employee=interaction.employee, interaction=interaction)

            if interaction.admin:
                Notification.objects.create(
                    recipient=interaction.admin, category='GENERAL', related_employee=interaction.employee,
                    title=f"Employee responded: {interaction.subject}",
                    message=f"{interaction.employee.empid}: {response_text[:150]}",
                )
            messages.success(request, "Your response has been sent.")
            return redirect('my_interaction_detail', interaction_id=interaction.id)

    timeline = WorkforceEvent.objects.filter(interaction=interaction).order_by('created_date')
    return render(request, 'my_interaction_detail.html', {
        'interaction': interaction, 'timeline': timeline,
        'can_respond': interaction.status not in ('RESOLVED', 'CLOSED'),
    })


@admin_required
def workforce_interactions(request):
    interactions = WorkforceInteraction.objects.select_related('employee', 'related_project', 'related_task').all()
    filter_type = request.GET.get('type', 'all')
    type_map = {
        'blockers': 'BLOCKER', 'clarifications': 'CLARIFICATION', 'assistance': 'ASSISTANCE',
        'deadline': 'DEADLINE_CONCERN', 'task': 'TASK_ISSUE', 'project': 'PROJECT_ISSUE',
    }
    if filter_type in type_map:
        interactions = interactions.filter(interaction_type=type_map[filter_type])

    return render(request, 'workforce_interactions.html', {
        'interactions': interactions.order_by('-created_date'),
        'active_filter': filter_type,
        'open_count': WorkforceInteraction.objects.filter(status='OPEN').count(),
        'attention_count': WorkforceInteraction.objects.filter(priority='ATTENTION').exclude(status__in=['RESOLVED', 'CLOSED']).count(),
        'urgent_count': WorkforceInteraction.objects.filter(priority='URGENT').exclude(status__in=['RESOLVED', 'CLOSED']).count(),
        'waiting_count': WorkforceInteraction.objects.filter(status='WAITING_FOR_EMPLOYEE').count(),
        'resolved_count': WorkforceInteraction.objects.filter(status='RESOLVED').count(),
    })


@admin_required
def workforce_interaction_detail(request, interaction_id):
    try:
        interaction = WorkforceInteraction.objects.get(id=interaction_id)
    except WorkforceInteraction.DoesNotExist:
        messages.error(request, "Interaction not found.")
        return redirect('workforce_interactions')

    from .ml.workforce_events import record_event
    from .ml.interaction_intelligence import possible_impact

    if request.method == "POST":
        action = request.POST.get('action')
        if action == 'set_status':
            new_status = request.POST.get('status')
            if new_status in VALID_TRANSITIONS.get(interaction.status, set()):
                interaction.status = new_status
                interaction.admin = interaction.admin or request.user
                if new_status == 'RESOLVED':
                    interaction.resolved_date = timezone.now()
                interaction.save()
                event_type = 'INTERACTION_RESOLVED' if new_status == 'RESOLVED' else 'INTERACTION_ACKNOWLEDGED'
                record_event(event_type, f'Admin set interaction "{interaction.subject}" to {new_status}.',
                             actor=request.user, employee=interaction.employee, interaction=interaction)
                if interaction.employee.user:
                    Notification.objects.create(
                        recipient=interaction.employee.user, category='GENERAL', related_employee=interaction.employee,
                        title=f"Update on: {interaction.subject}",
                        message=f"Status changed to {interaction.get_status_display()}.",
                    )
                messages.success(request, f"Status updated to {new_status}.")
            else:
                messages.error(request, "That status change isn't valid from the current state.")
        elif action == 'respond':
            response_text = request.POST.get('admin_response', '').strip()
            if response_text:
                interaction.admin_response = response_text
                interaction.admin = interaction.admin or request.user
                if interaction.status == 'OPEN':
                    interaction.status = 'ACKNOWLEDGED'
                interaction.save()
                record_event('INTERACTION_RESPONSE', f'Admin responded to "{interaction.subject}".',
                             actor=request.user, employee=interaction.employee, interaction=interaction)
                if interaction.employee.user:
                    Notification.objects.create(
                        recipient=interaction.employee.user, category='GENERAL', related_employee=interaction.employee,
                        title=f"Admin responded: {interaction.subject}",
                        message=response_text[:200],
                    )
                messages.success(request, "Response sent to employee.")
        return redirect('workforce_interaction_detail', interaction_id=interaction.id)

    timeline = WorkforceEvent.objects.filter(interaction=interaction).order_by('created_date')
    impact = possible_impact(interaction.ai_category, bool(interaction.related_task))
    next_statuses = sorted(VALID_TRANSITIONS.get(interaction.status, set()))

    return render(request, 'workforce_interaction_detail.html', {
        'interaction': interaction, 'timeline': timeline, 'impact': impact, 'next_statuses': next_statuses,
    })


# ==================================================
# ORGANIZATIONAL BRAIN / CLOSED DECISION LOOP (Prompt 11)
# Pure composition over existing models — no new "decision"/"intervention"
# table. Reuses early_warning, prediction_service, workforce_digital_twin.
# ==================================================

@admin_required
def organizational_brain_page(request):
    from .ml.organizational_brain import build_organizational_memory
    memory = build_organizational_memory()
    return render(request, 'organizational_brain.html', memory)


@admin_required
def evidence_explorer(request):
    from .ml.organizational_brain import build_entity_history, build_impact_chain
    entity_type = request.GET.get('entity_type')
    entity_id = request.GET.get('entity_id')
    history, impact_chain, error = None, None, None

    if entity_type and entity_id and str(entity_id).isdigit():
        history = build_entity_history(entity_type, int(entity_id))
        if 'error' in (history or {}):
            error = history['error']
            history = None
        elif entity_type in ('employee', 'project'):
            impact_chain = build_impact_chain(entity_type, int(entity_id))

    return render(request, 'evidence_explorer.html', {
        'employees': Employee.objects.select_related('user').all(),
        'projects': Project.objects.all(),
        'tasks': Task.objects.select_related('emp', 'project').all(),
        'entity_type': entity_type, 'entity_id': entity_id,
        'history': history, 'impact_chain': impact_chain, 'error': error,
    })


@employee_required
def my_decisions(request):
    """Employee-only, self-scoped. Identity comes from request.user; the
    employee never supplies their own id — the filtering below is applied
    AFTER deriving emp.id from the session, so there is no IDOR path."""
    from .ml.organizational_brain import build_decision_history, build_intervention_history
    emp = Employee.objects.get(user=request.user)
    decisions = [d for d in build_decision_history(limit=200) if d['entity_type'] == 'employee' and d['entity_id'] == emp.id]
    interventions = [a for a in build_intervention_history(limit=200) if a['employee_id'] == emp.id]
    return render(request, 'my_decisions.html', {'decisions': decisions, 'interventions': interventions})
@employee_required
def new_task_detail(request,pid):
    task=Task.objects.get(id=pid)
    tracker=TaskTracking.objects.filter(taskId=pid)
    return render(request,'new_task_detail.html',locals())
@employee_required
def updateTaskTracker(request,pid):
    task = Task.objects.get(id=pid,emp__user=request.user)
    if request.method == "POST":
        r = request.POST['remark']
        s = request.POST['status']
        w = request.POST['workCompleted']
        old_status = task.status
        task.remark=r
        task.status=s
        task.work=w
        if s == "Completed":
            if not task.completedDate:
                task.completedDate = timezone.now()  # record the REAL completion moment, once
        else:
            task.completedDate = None  # task reopened/changed — no longer validly "completed"
        task.save()
        TaskTracking.objects.create(taskId=task,remark=r,status=s,workCompleted=w)

        from .ml.workforce_events import record_event
        if s == "Completed" and old_status != "Completed":
            record_event('TASK_COMPLETED', f'Task "{task.title}" marked completed by {task.emp.empid}.',
                         actor=request.user, employee=task.emp, task=task, project=task.project)
        elif old_status == "Completed" and s != "Completed":
            record_event('TASK_REOPENED', f'Task "{task.title}" reopened by {task.emp.empid}.',
                         actor=request.user, employee=task.emp, task=task, project=task.project, severity='warning')
        else:
            record_event('TASK_UPDATED', f'Task "{task.title}" status set to "{s}" by {task.emp.empid}.',
                         actor=request.user, employee=task.emp, task=task, project=task.project)

        messages.success(request, "Remark Updated Successfully")
        return redirect('emp_new_task')
    return render(request,'update_task_tracker.html',locals())
@employee_required
def Emp_Change_Password(request):
    user = User.objects.get(username=request.user.username)
    if request.method=="POST":
        n = request.POST['pwd1']
        c = request.POST['pwd2']
        o = request.POST['pwd3']
        if c == n:
            u = User.objects.get(username__exact=request.user.username)
            u.set_password(n)
            u.save()
            messages.success(request, "Password changed successfully")
            return redirect('/')
        else:
            messages.success(request, "New password and confirm password are not same.")
            return redirect('emp_Change_Password')

    return render(request,'emp_change_password.html')
@admin_required
def Admin_Change_Password(request):
    user = User.objects.get(username=request.user.username)
    if request.method=="POST":
        n = request.POST['pwd1']
        c = request.POST['pwd2']
        o = request.POST['pwd3']
        if c == n:
            u = User.objects.get(username__exact=request.user.username)
            u.set_password(n)
            u.save()
            messages.success(request, "Password changed successfully")
            return redirect('/')
        else:
            messages.success(request, "New password and confirm password are not same.")
            return redirect('admin_Change_Password')

    return render(request,'admin_change_password.html')
@admin_required
def admin_view_new_task(request):
    task=Task.objects.filter()
    for t in task:
        t.risk_label, t.risk_score = calculate_task_risk(t)
    return render(request,'admin_view_new_task.html',locals())
@admin_required
def admin_view_inprogress_task(request):
    task=Task.objects.filter(status="Inprogress")
    for t in task:
        t.risk_label, t.risk_score = calculate_task_risk(t)
    return render(request,'admin_view_inprogress_task.html',locals())
@admin_required
def admin_view_completed_task(request):
    task=Task.objects.filter(status="Completed")
    for t in task:
        t.risk_label, t.risk_score = calculate_task_risk(t)
    return render(request,'admin_view_completed_task.html',locals())
@admin_required
def admin_view_task_detail(request,pid):
    task=Task.objects.get(id=pid)
    tracker=TaskTracking.objects.filter(taskId=pid)
    return render(request,'admin_view_task_detail.html',locals())
@admin_required
def find_by_date(request):
    t=None
    datef=''
    datet=''
    if request.method=='POST':
        datef=request.POST['datef']
        datet=request.POST['datet']
        print(datef)
        print(datet)
        # try:
        t=Task.objects.filter(assignDate__date__lte=datet,assignDate__date__gte=datef)
        # except:
        #     t=None
        print(t)
    return render(request,'find_by_date.html',locals())
@admin_required
def search_employee(request):
    data=""
    empId=""
    if request.method=='POST':
        empId=request.POST['empid']
        try:
            data=Employee.objects.get(empid=empId)
        except:
            data=None
    return render(request,'search_employee.html',locals())
@admin_required
def view_emp_task(request,pid):
    emp=Employee.objects.get(id=pid)
    task=Task.objects.filter(emp=emp)
    return render(request,'view_emp_task_detail.html',locals())

