"""
Create user bellaeaint@gmail.com with applications and memberships.
"""

import asyncio
import bcrypt
from uuid import uuid4
from datetime import datetime, timedelta, date
import sys

sys.path.insert(0, ".")

from sqlalchemy import select
from app.database import async_session_maker
from app.models import User, Application, Project, Task, ApplicationMember
from app.models.task_status import TaskStatus, StatusName


async def create_bella_with_data():
    async with async_session_maker() as db:
        # Get existing users
        result = await db.execute(select(User).where(User.email == 'samngestep@gmail.com'))
        sam1 = result.scalar_one_or_none()

        result = await db.execute(select(User).where(User.email == 'samngestep2@gmail.com'))
        sam2 = result.scalar_one_or_none()

        # Create Bella user
        email = 'bellaeaint@gmail.com'
        password = 'Test123!'

        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')

        result = await db.execute(select(User).where(User.email == email))
        bella = result.scalar_one_or_none()

        if not bella:
            bella = User(
                id=uuid4(),
                email=email,
                password_hash=password_hash,
                display_name='Bella Eaint',
            )
            db.add(bella)
            await db.flush()
            print(f'Created user: {email}')
        else:
            print(f'User {email} already exists')

        # ========== APP 1: Owned by Bella, Sam1 and Sam2 are members ==========
        app1 = Application(
            id=uuid4(),
            name='Bella Design Studio',
            description='Design projects owned by Bella',
            owner_id=bella.id,
        )
        db.add(app1)
        await db.flush()
        print(f'Created application: {app1.name} (Owner: Bella)')

        # Add Sam1 and Sam2 as members
        if sam1:
            member1 = ApplicationMember(
                id=uuid4(),
                application_id=app1.id,
                user_id=sam1.id,
                role='editor',
            )
            db.add(member1)
            print(f'  Added member: samngestep@gmail.com (editor)')

        if sam2:
            member2 = ApplicationMember(
                id=uuid4(),
                application_id=app1.id,
                user_id=sam2.id,
                role='viewer',
            )
            db.add(member2)
            print(f'  Added member: samngestep2@gmail.com (viewer)')

        # Create a project in Bella's app
        proj1 = Project(
            id=uuid4(),
            application_id=app1.id,
            name='Website Redesign',
            key='WEB01',
            description='Company website redesign project',
            project_type='kanban',
            due_date=date.today() + timedelta(days=45),
        )
        db.add(proj1)
        await db.flush()

        statuses1 = TaskStatus.create_default_statuses(proj1.id)
        for s in statuses1:
            db.add(s)
        await db.flush()

        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj1.id, TaskStatus.name == StatusName.TODO.value))
        todo1 = result.scalar_one()
        result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj1.id, TaskStatus.name == StatusName.IN_PROGRESS.value))
        in_progress1 = result.scalar_one()

        print(f'  Created project: {proj1.key} - {proj1.name}')

        for i, title in enumerate(['Create mockups', 'Review with stakeholders', 'Implement homepage'], 1):
            task = Task(
                id=uuid4(),
                project_id=proj1.id,
                task_key=f'WEB01-{i}',
                title=title,
                task_type='story',
                task_status_id=todo1.id if i == 1 else in_progress1.id,
                priority='high',
                reporter_id=bella.id,
            )
            db.add(task)
        print(f'    Created 3 tasks')

        # ========== APP 2: Owned by Sam1, Bella is member ==========
        if sam1:
            app2 = Application(
                id=uuid4(),
                name='Sam Engineering Hub',
                description='Engineering projects owned by Sam',
                owner_id=sam1.id,
            )
            db.add(app2)
            await db.flush()
            print(f'Created application: {app2.name} (Owner: samngestep@gmail.com)')

            # Add Bella as member
            member3 = ApplicationMember(
                id=uuid4(),
                application_id=app2.id,
                user_id=bella.id,
                role='editor',
            )
            db.add(member3)
            print(f'  Added member: bellaeaint@gmail.com (editor)')

            # Create project
            proj2 = Project(
                id=uuid4(),
                application_id=app2.id,
                name='API Development',
                key='API01',
                description='Backend API development',
                project_type='kanban',
                due_date=date.today() + timedelta(days=60),
            )
            db.add(proj2)
            await db.flush()

            statuses2 = TaskStatus.create_default_statuses(proj2.id)
            for s in statuses2:
                db.add(s)
            await db.flush()

            result = await db.execute(select(TaskStatus).where(TaskStatus.project_id == proj2.id, TaskStatus.name == StatusName.IN_PROGRESS.value))
            in_progress2 = result.scalar_one()

            print(f'  Created project: {proj2.key} - {proj2.name}')

            for i, title in enumerate(['Design REST endpoints', 'Implement authentication', 'Write tests'], 1):
                task = Task(
                    id=uuid4(),
                    project_id=proj2.id,
                    task_key=f'API01-{i}',
                    title=title,
                    task_type='story',
                    task_status_id=in_progress2.id,
                    priority='high',
                    reporter_id=sam1.id,
                )
                db.add(task)
            print(f'    Created 3 tasks')

        # ========== APP 3: Owned by Sam2, Bella is member ==========
        if sam2:
            app3 = Application(
                id=uuid4(),
                name='Mobile Team Workspace',
                description='Mobile development projects',
                owner_id=sam2.id,
            )
            db.add(app3)
            await db.flush()
            print(f'Created application: {app3.name} (Owner: samngestep2@gmail.com)')

            # Add Bella as member
            member4 = ApplicationMember(
                id=uuid4(),
                application_id=app3.id,
                user_id=bella.id,
                role='viewer',
            )
            db.add(member4)
            print(f'  Added member: bellaeaint@gmail.com (viewer)')

            # Add Sam1 as member too
            if sam1:
                member5 = ApplicationMember(
                    id=uuid4(),
                    application_id=app3.id,
                    user_id=sam1.id,
                    role='editor',
                )
                db.add(member5)
                print(f'  Added member: samngestep@gmail.com (editor)')

            # Create project
            proj3 = Project(
                id=uuid4(),
                application_id=app3.id,
                name='iOS App v2',
                key='IOS01',
                description='iOS app version 2 development',
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

            print(f'  Created project: {proj3.key} - {proj3.name}')

            for i, title in enumerate(['Swift UI migration', 'Core Data optimization', 'Push notifications'], 1):
                task = Task(
                    id=uuid4(),
                    project_id=proj3.id,
                    task_key=f'IOS01-{i}',
                    title=title,
                    task_type='story',
                    task_status_id=todo3.id,
                    priority='medium',
                    reporter_id=sam2.id,
                )
                db.add(task)
            print(f'    Created 3 tasks')

        await db.commit()

        print()
        print('=' * 60)
        print('SUMMARY')
        print('=' * 60)
        print()
        print('Users:')
        print('  - samngestep@gmail.com (password: 9ol.(OL>)')
        print('  - samngestep2@gmail.com (password: Test123!)')
        print('  - bellaeaint@gmail.com (password: Test123!)')
        print()
        print('Applications & Memberships:')
        print()
        print('  1. Bella Design Studio')
        print('     Owner: bellaeaint@gmail.com')
        print('     Members: samngestep@gmail.com (editor), samngestep2@gmail.com (viewer)')
        print()
        print('  2. Sam Engineering Hub')
        print('     Owner: samngestep@gmail.com')
        print('     Members: bellaeaint@gmail.com (editor)')
        print()
        print('  3. Mobile Team Workspace')
        print('     Owner: samngestep2@gmail.com')
        print('     Members: bellaeaint@gmail.com (viewer), samngestep@gmail.com (editor)')


if __name__ == "__main__":
    asyncio.run(create_bella_with_data())
