"""
Create more projects with tasks, members, and archivable done tasks.
"""

import asyncio
from uuid import uuid4
from datetime import datetime, timedelta, date
import sys

sys.path.insert(0, ".")

from sqlalchemy import select
from app.database import async_session_maker
from app.models import User, Application, Project, Task, ProjectMember
from app.models.task_status import TaskStatus, StatusName


async def create_more_projects():
    async with async_session_maker() as db:
        # Get all users
        result = await db.execute(select(User).where(User.email.in_([
            'samngestep@gmail.com',
            'samngestep2@gmail.com',
            'bellaeaint@gmail.com'
        ])))
        users = {u.email: u for u in result.scalars().all()}

        sam1 = users.get('samngestep@gmail.com')
        sam2 = users.get('samngestep2@gmail.com')
        bella = users.get('bellaeaint@gmail.com')

        if not all([sam1, sam2, bella]):
            print('Missing users!')
            return

        # Get Sam1's application (Sam Engineering Hub)
        result = await db.execute(
            select(Application).where(Application.owner_id == sam1.id)
        )
        sam1_app = result.scalar_one_or_none()

        if not sam1_app:
            print('Sam1 app not found')
            return

        print(f'Using application: {sam1_app.name}')
        print()

        # ========== PROJECT 1: E-commerce Platform ==========
        proj1 = Project(
            id=uuid4(),
            application_id=sam1_app.id,
            name='E-commerce Platform',
            key='ECOM',
            description='Full e-commerce solution with cart, checkout, payments',
            project_type='kanban',
            due_date=date.today() + timedelta(days=60),
        )
        db.add(proj1)
        await db.flush()

        # Create statuses
        statuses = TaskStatus.create_default_statuses(proj1.id)
        for s in statuses:
            db.add(s)
        await db.flush()

        # Get statuses
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj1.id, TaskStatus.name == StatusName.TODO.value))
        todo = result.scalar_one()
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj1.id, TaskStatus.name == StatusName.IN_PROGRESS.value))
        in_progress = result.scalar_one()
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj1.id, TaskStatus.name == StatusName.IN_REVIEW.value))
        in_review = result.scalar_one()
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj1.id, TaskStatus.name == StatusName.DONE.value))
        done = result.scalar_one()

        # Add project members (roles: 'admin' or 'member')
        for user, role in [(sam2, 'member'), (bella, 'member')]:
            pm = ProjectMember(
                id=uuid4(),
                project_id=proj1.id,
                user_id=user.id,
                role=role,
            )
            db.add(pm)

        print(f'Created project: {proj1.key} - {proj1.name}')
        print(f'  Members: sam2 (member), bella (member)')

        # Done tasks (archivable - 8+ days)
        done_tasks = [
            ('Setup project structure', 15, sam1),
            ('Design database schema', 12, sam2),
            ('Create wireframes', 10, bella),
            ('Implement user registration', 9, sam2),
            ('Setup payment gateway', 8, sam1),
        ]
        for i, (title, days, assignee) in enumerate(done_tasks, 1):
            task = Task(
                id=uuid4(),
                project_id=proj1.id,
                task_key=f'ECOM-{i}',
                title=title,
                task_type='story',
                task_status_id=done.id,
                priority='high',
                reporter_id=sam1.id,
                assignee_id=assignee.id,
                completed_at=datetime.utcnow() - timedelta(days=days),
            )
            db.add(task)
            print(f'  Task: ECOM-{i} - {title} (Done {days}d ago, assigned: {assignee.display_name})')

        # Active tasks
        active_tasks = [
            ('Implement shopping cart', in_progress, sam2),
            ('Design checkout flow', in_progress, bella),
            ('Add product search', in_review, sam2),
            ('Create admin dashboard', todo, sam1),
            ('Write API documentation', todo, bella),
        ]
        for i, (title, status, assignee) in enumerate(active_tasks, 6):
            task = Task(
                id=uuid4(),
                project_id=proj1.id,
                task_key=f'ECOM-{i}',
                title=title,
                task_type='story',
                task_status_id=status.id,
                priority='medium',
                reporter_id=sam1.id,
                assignee_id=assignee.id,
            )
            db.add(task)
            print(f'  Task: ECOM-{i} - {title} ({status.name}, assigned: {assignee.display_name})')

        print()

        # ========== PROJECT 2: Customer Support Portal ==========
        proj2 = Project(
            id=uuid4(),
            application_id=sam1_app.id,
            name='Customer Support Portal',
            key='SUPP',
            description='Ticketing system and knowledge base',
            project_type='kanban',
            due_date=date.today() + timedelta(days=30),
        )
        db.add(proj2)
        await db.flush()

        statuses2 = TaskStatus.create_default_statuses(proj2.id)
        for s in statuses2:
            db.add(s)
        await db.flush()

        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj2.id, TaskStatus.name == StatusName.TODO.value))
        todo2 = result.scalar_one()
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj2.id, TaskStatus.name == StatusName.IN_PROGRESS.value))
        in_progress2 = result.scalar_one()
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj2.id, TaskStatus.name == StatusName.DONE.value))
        done2 = result.scalar_one()

        # Add members (roles: 'admin' or 'member')
        for user, role in [(sam2, 'member'), (bella, 'member')]:
            pm = ProjectMember(
                id=uuid4(),
                project_id=proj2.id,
                user_id=user.id,
                role=role,
            )
            db.add(pm)

        print(f'Created project: {proj2.key} - {proj2.name}')
        print(f'  Members: sam2 (member), bella (member)')

        # Done tasks
        done_tasks2 = [
            ('Setup ticketing database', 20, sam2),
            ('Create ticket submission form', 14, bella),
            ('Implement email notifications', 11, sam2),
            ('Design dashboard UI', 9, bella),
        ]
        for i, (title, days, assignee) in enumerate(done_tasks2, 1):
            task = Task(
                id=uuid4(),
                project_id=proj2.id,
                task_key=f'SUPP-{i}',
                title=title,
                task_type='story',
                task_status_id=done2.id,
                priority='high',
                reporter_id=sam1.id,
                assignee_id=assignee.id,
                completed_at=datetime.utcnow() - timedelta(days=days),
            )
            db.add(task)
            print(f'  Task: SUPP-{i} - {title} (Done {days}d ago, assigned: {assignee.display_name})')

        # Active tasks
        active_tasks2 = [
            ('Add ticket priority levels', in_progress2, sam2),
            ('Create knowledge base', todo2, bella),
        ]
        for i, (title, status, assignee) in enumerate(active_tasks2, 5):
            task = Task(
                id=uuid4(),
                project_id=proj2.id,
                task_key=f'SUPP-{i}',
                title=title,
                task_type='story',
                task_status_id=status.id,
                priority='medium',
                reporter_id=sam1.id,
                assignee_id=assignee.id,
            )
            db.add(task)
            print(f'  Task: SUPP-{i} - {title} ({status.name}, assigned: {assignee.display_name})')

        print()

        # ========== PROJECT 3: Analytics Dashboard (all done - ready to archive) ==========
        proj3 = Project(
            id=uuid4(),
            application_id=sam1_app.id,
            name='Analytics Dashboard v1',
            key='ANAL',
            description='Completed analytics project - ready for archiving',
            project_type='kanban',
            due_date=date.today() - timedelta(days=30),
        )
        db.add(proj3)
        await db.flush()

        statuses3 = TaskStatus.create_default_statuses(proj3.id)
        for s in statuses3:
            db.add(s)
        await db.flush()

        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj3.id, TaskStatus.name == StatusName.DONE.value))
        done3 = result.scalar_one()

        # Add members (roles: 'admin' or 'member')
        for user, role in [(sam2, 'admin'), (bella, 'member')]:
            pm = ProjectMember(
                id=uuid4(),
                project_id=proj3.id,
                user_id=user.id,
                role=role,
            )
            db.add(pm)

        print(f'Created project: {proj3.key} - {proj3.name}')
        print(f'  Members: sam2 (admin), bella (member)')
        print('  ** ALL TASKS DONE - PROJECT READY TO ARCHIVE **')

        done_tasks3 = [
            ('Setup data pipeline', 25, sam2),
            ('Create chart components', 22, bella),
            ('Implement filters', 18, sam2),
            ('Add export functionality', 15, sam1),
            ('Performance optimization', 10, sam2),
            ('Final testing', 8, bella),
        ]
        for i, (title, days, assignee) in enumerate(done_tasks3, 1):
            task = Task(
                id=uuid4(),
                project_id=proj3.id,
                task_key=f'ANAL-{i}',
                title=title,
                task_type='story',
                task_status_id=done3.id,
                priority='high',
                reporter_id=sam1.id,
                assignee_id=assignee.id,
                completed_at=datetime.utcnow() - timedelta(days=days),
            )
            db.add(task)
            print(f'  Task: ANAL-{i} - {title} (Done {days}d ago, assigned: {assignee.display_name})')

        print()

        # ========== PROJECT 4: Data Migration (recent done - not archivable) ==========
        proj4 = Project(
            id=uuid4(),
            application_id=sam1_app.id,
            name='Data Migration Q1',
            key='MIGR',
            description='Recent project with tasks done less than 7 days',
            project_type='kanban',
            due_date=date.today() + timedelta(days=7),
        )
        db.add(proj4)
        await db.flush()

        statuses4 = TaskStatus.create_default_statuses(proj4.id)
        for s in statuses4:
            db.add(s)
        await db.flush()

        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj4.id, TaskStatus.name == StatusName.DONE.value))
        done4 = result.scalar_one()
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj4.id, TaskStatus.name == StatusName.IN_PROGRESS.value))
        in_progress4 = result.scalar_one()

        pm = ProjectMember(
            id=uuid4(),
            project_id=proj4.id,
            user_id=sam2.id,
            role='member',
        )
        db.add(pm)

        print(f'Created project: {proj4.key} - {proj4.name}')
        print(f'  Members: sam2 (member)')
        print('  ** RECENT DONE TASKS - NOT ARCHIVABLE **')

        # Recent done tasks (NOT archivable)
        recent_done = [
            ('Export legacy data', 3, sam2),
            ('Transform data format', 2, sam1),
            ('Validate migration', 1, sam2),
        ]
        for i, (title, days, assignee) in enumerate(recent_done, 1):
            task = Task(
                id=uuid4(),
                project_id=proj4.id,
                task_key=f'MIGR-{i}',
                title=title,
                task_type='story',
                task_status_id=done4.id,
                priority='high',
                reporter_id=sam1.id,
                assignee_id=assignee.id,
                completed_at=datetime.utcnow() - timedelta(days=days),
            )
            db.add(task)
            print(f'  Task: MIGR-{i} - {title} (Done {days}d ago - NOT archivable)')

        # Active task
        task = Task(
            id=uuid4(),
            project_id=proj4.id,
            task_key='MIGR-4',
            title='Import to new system',
            task_type='story',
            task_status_id=in_progress4.id,
            priority='high',
            reporter_id=sam1.id,
            assignee_id=sam2.id,
        )
        db.add(task)
        print(f'  Task: MIGR-4 - Import to new system (In Progress)')

        await db.commit()

        print()
        print('=' * 70)
        print('SUMMARY')
        print('=' * 70)
        print()
        print('Login as: samngestep@gmail.com (password: 9ol.(OL>)')
        print('Application: Sam Engineering Hub')
        print()
        print('New Projects:')
        print('  1. ECOM - E-commerce Platform')
        print('     - 5 archivable tasks (Done 8-15 days)')
        print('     - 5 active tasks')
        print('     - Members: sam2, bella')
        print()
        print('  2. SUPP - Customer Support Portal')
        print('     - 4 archivable tasks (Done 9-20 days)')
        print('     - 2 active tasks')
        print('     - Members: sam2, bella')
        print()
        print('  3. ANAL - Analytics Dashboard v1')
        print('     - 6 archivable tasks (Done 8-25 days)')
        print('     - 0 active tasks')
        print('     - ** ENTIRE PROJECT WILL BE ARCHIVED **')
        print('     - Members: sam2, bella')
        print()
        print('  4. MIGR - Data Migration Q1')
        print('     - 0 archivable tasks (Done < 7 days)')
        print('     - 1 active task')
        print('     - ** NOTHING WILL BE ARCHIVED **')
        print()
        print('Expected archive results:')
        print('  - 15 tasks archived (5 ECOM + 4 SUPP + 6 ANAL)')
        print('  - 1 project archived (ANAL)')


if __name__ == "__main__":
    asyncio.run(create_more_projects())
