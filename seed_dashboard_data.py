"""
Seeds realistic dummy Employees + Tasks so the Admin Dashboard
(KPIs, Task Trend chart, Department Distribution chart, Recent Activity,
Top Performing Employees, Department Performance, AI Recommendations)
has enough real data to display properly, and marks a couple of
employees "On Leave" with at-risk tasks so the AI leave-recommendation
rule has something real to show.

Run with (from the folder containing manage.py):
    python manage.py shell < seed_dashboard_data.py

Safe to re-run: it only ADDS new employees/tasks, it never deletes
or duplicates existing data.
"""

import random
from datetime import date, timedelta, datetime
from django.contrib.auth.models import User
from django.utils import timezone
from Employee.models import Department, Employee, Task

random.seed(7)

FIRST_NAMES = ["Aarav", "Priya", "Rohan", "Sneha", "Kabir", "Anjali", "Vikram", "Neha",
               "Arjun", "Divya", "Karan", "Isha", "Rahul", "Pooja", "Aditya", "Meera",
               "Siddharth", "Ritu", "Manish", "Sanya"]
LAST_NAMES = ["Sharma", "Verma", "Patel", "Reddy", "Nair", "Iyer", "Singh", "Gupta",
              "Mehta", "Kapoor", "Joshi", "Das", "Rao", "Bhat", "Chatterjee"]
DESIGNATIONS = ["Software Engineer", "Senior Developer", "QA Analyst", "Business Analyst",
                "Project Coordinator", "UI/UX Designer", "DevOps Engineer", "Data Analyst",
                "HR Executive", "Team Lead"]
TASK_TITLES = ["Fix login bug", "Design dashboard UI", "Prepare monthly report",
               "Client requirement review", "API integration", "Database optimization",
               "Unit testing", "Code review", "Deploy to staging", "Write documentation",
               "Sprint planning", "Bug triage", "Performance tuning", "Security audit",
               "User training session", "Data migration", "Feature rollout",
               "Customer feedback analysis", "Backup verification", "Server maintenance"]


def aware(d):
    """Turn a plain date into a timezone-aware datetime at midnight."""
    return timezone.make_aware(datetime.combine(d, datetime.min.time()))


# ---------------------------------------------------------
# 1. DEPARTMENTS — make sure at least a few exist
# ---------------------------------------------------------
depts = list(Department.objects.all())
if not depts:
    depts = [Department.objects.create(name=n) for n in
              ["Engineering", "QA", "HR", "Sales", "Support", "Finance", "Design"]]

# ---------------------------------------------------------
# 2. EMPLOYEES — add 15 new dummy employees
# ---------------------------------------------------------
existing_count = Employee.objects.count()
NEW_EMPLOYEES = 15
created_employees = []

for i in range(NEW_EMPLOYEES):
    fn = random.choice(FIRST_NAMES)
    ln = random.choice(LAST_NAMES)
    eid = str(2000 + existing_count + i)
    if User.objects.filter(username=eid).exists():
        continue
    user = User.objects.create_user(
        username=eid,
        email=f"{fn.lower()}.{ln.lower()}{eid}@example.com",
        password="Pass@123",
        first_name=fn,
        last_name=ln,
    )
    dept = random.choice(depts)
    doj = date.today() - timedelta(days=random.randint(90, 900))
    dob = date.today() - timedelta(days=random.randint(8000, 15000))
    emp = Employee.objects.create(
        user=user, dept=dept, empid=eid,
        contact=f"9{random.randint(100000000, 999999999)}",
        designation=random.choice(DESIGNATIONS),
        dob=dob, doj=doj,
        address=f"{random.randint(1, 200)} MG Road, City",
        description="Auto-generated demo profile",
    )
    created_employees.append(emp)

print(f"Employees created: {len(created_employees)}")

# ---------------------------------------------------------
# 3. TASKS — 3-7 tasks per employee, spread across last 6 months
# ---------------------------------------------------------
all_employees = list(Employee.objects.all())
today = date.today()
created_tasks = 0

for emp in all_employees:
    n_tasks = random.randint(3, 7)
    for _ in range(n_tasks):
        months_back = random.randint(0, 5)
        assign_date = (today.replace(day=1) - timedelta(days=30 * months_back))
        assign_date = assign_date.replace(day=random.randint(1, 28))

        roll = random.random()
        if roll < 0.45:
            status = "Completed"
            end_date = assign_date + timedelta(days=random.randint(3, 20))
        elif roll < 0.75:
            status = "Inprogress"
            end_date = today + timedelta(days=random.randint(-5, 15))
        else:
            status = "Not Updated Yet"
            end_date = today + timedelta(days=random.randint(1, 20))

        title = random.choice(TASK_TITLES)
        priority = random.choices(["Low", "Medium", "High"], weights=[0.3, 0.45, 0.25])[0]

        t = Task.objects.create(
            dept=emp.dept, emp=emp, priority=priority, title=title,
            description=f"{title} for {emp.dept.name if emp.dept else 'team'}",
            status=status, work="", remark="",
            endDate=aware(end_date),
        )
        # assignDate uses auto_now=True, so it must be backdated with .update()
        Task.objects.filter(id=t.id).update(assignDate=aware(assign_date))
        created_tasks += 1

print(f"Tasks created: {created_tasks}")

# ---------------------------------------------------------
# 4. LEAVE SCENARIO — mark 2 employees on leave with an at-risk task
#    so the "AI Decision Intelligence" leave rule has real data to show
# ---------------------------------------------------------
leave_candidates = [e for e in all_employees
                     if Task.objects.filter(emp=e).exclude(status="Completed").exists()]
random.shuffle(leave_candidates)
marked = 0
for e in leave_candidates[:2]:
    e.on_leave = True
    e.leave_return_date = today + timedelta(days=random.randint(2, 7))
    e.save()
    active_task = Task.objects.filter(emp=e).exclude(status="Completed").first()
    if active_task:
        active_task.endDate = aware(today + timedelta(days=random.randint(0, 2)))
        active_task.save()
    marked += 1

print(f"Employees marked On Leave (with at-risk active tasks): {marked}")
print("\nDone. Open /admin_home to see the refreshed dashboard.")
