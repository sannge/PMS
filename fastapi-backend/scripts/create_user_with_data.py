"""
Create user samngestep2@gmail.com with projects and tasks for testing.
"""

import asyncio
import bcrypt
from uuid import uuid4
from datetime import datetime, timedelta, date
import sys

sys.path.insert(0, ".")

from sqlalchemy import select
from app.database import async_session_maker
from app.models import User, Application, Project, Task
from app.models.task_status import TaskStatus, StatusName


async def create_user_with_data():
    email = 'samngestep2@gmail.com'
    password = 'Test123!'

    # Hash password
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')

    async with async_session_maker() as db:
        # Check if user exists
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                id=uuid4(),
                email=email,
                password_hash=password_hash,
                display_name='Sam Ng 2',
            )
            db.add(user)
            await db.flush()
            print(f'Created user: {email}')
        else:
            print(f'User {email} already exists')

        # Create Application
        app = Application(
            id=uuid4(),
            name='Sam Test Application',
            description='Test application with various projects and tasks',
            owner_id=user.id,
        )
        db.add(app)
        await db.flush()
        print(f'Created application: {app.name}')

        # ========== PROJECT 1: Active project with mixed tasks ==========
        proj1 = Project(
            id=uuid4(),
            application_id=app.id,
            name='Active Development Project',
            key='DEV01',
            description='Active project with ongoing work',
            project_type='kanban',
            due_date=date.today() + timedelta(days=30),
        )
        db.add(proj1)
        await db.flush()

        # Create statuses for project 1
        statuses1 = TaskStatus.create_default_statuses(proj1.id)
        for s in statuses1:
            db.add(s)
        await db.flush()

        # Get statuses
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj1.id, TaskStatus.name == StatusName.TODO.value))
        todo1 = result.scalar_one()
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj1.id, TaskStatus.name == StatusName.IN_PROGRESS.value))
        in_progress1 = result.scalar_one()
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj1.id, TaskStatus.name == StatusName.DONE.value))
        done1 = result.scalar_one()

        print(f'Created project: {proj1.key} - {proj1.name}')

        # Active tasks
        for i, title in enumerate(['Setup CI/CD pipeline', 'Design database schema', 'Implement user auth'], 1):
            task = Task(
                id=uuid4(),
                project_id=proj1.id,
                task_key=f'DEV01-{i}',
                title=title,
                task_type='story',
                task_status_id=in_progress1.id,
                priority='high',
                reporter_id=user.id,
            )
            db.add(task)
            print(f'  Created task: {task.task_key} - {title} (in progress)')

        # Todo tasks
        for i, title in enumerate(['Write API documentation', 'Add unit tests'], 4):
            task = Task(
                id=uuid4(),
                project_id=proj1.id,
                task_key=f'DEV01-{i}',
                title=title,
                task_type='story',
                task_status_id=todo1.id,
                priority='medium',
                reporter_id=user.id,
            )
            db.add(task)
            print(f'  Created task: {task.task_key} - {title} (todo)')

        # Old done task (archivable)
        task = Task(
            id=uuid4(),
            project_id=proj1.id,
            task_key='DEV01-6',
            title='Initial project setup',
            task_type='story',
            task_status_id=done1.id,
            priority='high',
            reporter_id=user.id,
            completed_at=datetime.utcnow() - timedelta(days=10),
        )
        db.add(task)
        print(f'  Created task: {task.task_key} - Initial project setup (done 10 days - ARCHIVABLE)')

        # ========== PROJECT 2: Ready to archive (all tasks old done) ==========
        proj2 = Project(
            id=uuid4(),
            application_id=app.id,
            name='Completed Legacy Project',
            key='LEG01',
            description='Old project ready for archiving',
            project_type='kanban',
            due_date=date.today() - timedelta(days=60),
        )
        db.add(proj2)
        await db.flush()

        statuses2 = TaskStatus.create_default_statuses(proj2.id)
        for s in statuses2:
            db.add(s)
        await db.flush()

        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj2.id, TaskStatus.name == StatusName.DONE.value))
        done2 = result.scalar_one()

        print(f'Created project: {proj2.key} - {proj2.name}')

        for i, (title, days) in enumerate([
            ('Legacy feature A', 15),
            ('Legacy feature B', 12),
            ('Legacy bug fix', 9),
        ], 1):
            task = Task(
                id=uuid4(),
                project_id=proj2.id,
                task_key=f'LEG01-{i}',
                title=title,
                task_type='story',
                task_status_id=done2.id,
                priority='medium',
                reporter_id=user.id,
                completed_at=datetime.utcnow() - timedelta(days=days),
            )
            db.add(task)
            print(f'  Created task: {task.task_key} - {title} (done {days} days - ARCHIVABLE)')

        # ========== PROJECT 3: Another active project ==========
        proj3 = Project(
            id=uuid4(),
            application_id=app.id,
            name='Mobile App Development',
            key='MOB01',
            description='New mobile app project',
            project_type='kanban',
            due_date=date.today() + timedelta(days=90),
        )
        db.add(proj3)
        await db.flush()

        statuses3 = TaskStatus.create_default_statuses(proj3.id)
        for s in statuses3:
            db.add(s)
        await db.flush()

        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj3.id, TaskStatus.name == StatusName.TODO.value))
        todo3 = result.scalar_one()
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj3.id, TaskStatus.name == StatusName.IN_REVIEW.value))
        review3 = result.scalar_one()

        print(f'Created project: {proj3.key} - {proj3.name}')

        for i, title in enumerate(['Design app wireframes', 'Setup React Native', 'Create login screen'], 1):
            task = Task(
                id=uuid4(),
                project_id=proj3.id,
                task_key=f'MOB01-{i}',
                title=title,
                task_type='story',
                task_status_id=todo3.id if i < 3 else review3.id,
                priority='high',
                reporter_id=user.id,
            )
            db.add(task)
            status = 'todo' if i < 3 else 'in review'
            print(f'  Created task: {task.task_key} - {title} ({status})')

        await db.commit()

        print()
        print('=' * 60)
        print('SUMMARY')
        print('=' * 60)
        print(f'User: {email}')
        print(f'Application: {app.name}')
        print()
        print('Projects:')
        print(f'  1. {proj1.key} - Active with mixed tasks (1 archivable task)')
        print(f'  2. {proj2.key} - Ready to archive (all 3 tasks archivable)')
        print(f'  3. {proj3.key} - Active with all active tasks')
        print()
        print('Expected archive result:')
        print('  - 4 tasks archived (1 from DEV01 + 3 from LEG01)')
        print('  - 1 project archived (LEG01)')


if __name__ == "__main__":
    asyncio.run(create_user_with_data())
