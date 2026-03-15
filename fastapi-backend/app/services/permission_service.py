"""Permission service for role checks and ProjectMember gate logic.

This service implements the 3-tier permission model (Owner/Editor/Viewer)
with ProjectMember gate for Editors. It centralizes permission checks
to ensure consistent enforcement across the application.

Permission Model:
- Application Owner: Super admin - full access to all projects and tasks
- Application Editor: Can only manage tasks in projects where they are ProjectMembers
- Application Viewer: Read-only access, cannot create/edit/delete tasks

Project Member Roles:
- Project Admin: Can manage project members + edit/move tasks
- Project Member: Can edit/move tasks only

Assignment Rules:
- Only ProjectMembers (admin/member) who are Owner/Editor can be assigned
- App Owners can be assigned even without project membership
- Viewers cannot be assigned to tasks
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.application import Application
from ..models.application_member import ApplicationMember
from ..models.project import Project
from ..models.project_member import ProjectMember
from ..models.user import User


class PermissionService:
    """
    Service class for permission checks and ProjectMember gate logic.

    Provides methods to verify user permissions at both application and
    project levels, implementing the 3-tier role system with ProjectMember
    gate for Editors.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the PermissionService.

        Args:
            db: SQLAlchemy async database session
        """
        self.db = db

    async def get_user_application_role(
        self,
        user_id: UUID,
        application_id: UUID,
        application: Optional[Application] = None,
    ) -> Optional[str]:
        """
        Get the user's role in an application.

        Args:
            user_id: The user's ID
            application_id: The application's ID
            application: Optional pre-fetched application to avoid extra query

        Returns:
            The role string ('owner', 'editor', 'viewer') or None if not a member.
        """
        # If application is provided, use it; otherwise fetch
        if application is None:
            result = await self.db.execute(
                select(Application).where(Application.id == application_id)
            )
            application = result.scalar_one_or_none()

        if not application:
            return None

        # Check if user is the original owner
        if application.owner_id == user_id:
            return "owner"

        # Check ApplicationMembers table
        result = await self.db.execute(
            select(ApplicationMember).where(
                ApplicationMember.application_id == application_id,
                ApplicationMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()

        return member.role if member else None

    async def is_application_member(
        self,
        user_id: UUID,
        application_id: UUID,
    ) -> bool:
        """
        Check if a user is a member of an application (any role).

        Uses EXISTS pattern for optimal performance.

        Args:
            user_id: The user's ID
            application_id: The application's ID

        Returns:
            True if user is an ApplicationMember or owner, False otherwise.
        """
        # Single query: check owner OR member via UNION ALL inside EXISTS
        from sqlalchemy import union_all, literal
        owner_check = select(literal(1)).where(
            Application.id == application_id,
            Application.owner_id == user_id,
        )
        member_check = select(literal(1)).where(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == user_id,
        )
        combined = union_all(owner_check, member_check)
        result = await self.db.execute(
            select(exists(combined.subquery().select()))
        )
        return result.scalar() or False

    async def is_application_owner(
        self,
        user_id: UUID,
        application_id: UUID,
    ) -> bool:
        """Check if the user is an owner of the application."""
        role = await self.get_user_application_role(user_id, application_id)
        return role == "owner"

    async def can_edit_application(
        self,
        user_id: UUID,
        application_id: UUID,
    ) -> bool:
        """Check if the user can edit the application (owner or editor)."""
        role = await self.get_user_application_role(user_id, application_id)
        return role in ("owner", "editor")

    async def is_project_member(
        self,
        user_id: UUID,
        project_id: UUID,
    ) -> bool:
        """
        Check if a user is a member of a project.

        Uses EXISTS pattern for optimal performance - avoids loading
        the entire record when we only need existence check.

        Args:
            user_id: The user's ID
            project_id: The project's ID

        Returns:
            True if user is a ProjectMember, False otherwise.
        """
        result = await self.db.execute(
            select(
                exists().where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == user_id,
                )
            )
        )
        return result.scalar() or False

    async def get_project_member_role(
        self,
        user_id: UUID,
        project_id: UUID,
    ) -> Optional[str]:
        """
        Get the user's role within a project.

        Args:
            user_id: The user's ID
            project_id: The project's ID

        Returns:
            The role string ('admin', 'member') or None if not a project member.
        """
        result = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()

        return member.role if member else None

    async def get_project_with_application(
        self,
        project_id: UUID,
    ) -> Optional[Project]:
        """
        Fetch a project with its parent application loaded.

        Args:
            project_id: The project's ID

        Returns:
            Project with application loaded, or None if not found.
        """
        result = await self.db.execute(
            select(Project)
            .options(selectinload(Project.application))
            .where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def check_can_view_knowledge(
        self, user_id: UUID, scope: str, scope_id: UUID
    ) -> bool:
        """Check if user can view documents/folders in a scope.

        Args:
            user_id: The user's ID
            scope: One of "personal", "application", "project"
            scope_id: The scope entity ID (user_id, application_id, or project_id)

        Returns:
            True if user can view knowledge in this scope.
        """
        if scope == "personal":
            return scope_id == user_id
        elif scope == "application":
            return await self.is_application_member(user_id, scope_id)
        elif scope == "project":
            project = await self.get_project_with_application(scope_id)
            if not project:
                return False
            return await self.is_application_member(user_id, project.application_id)
        return False

    async def check_can_edit_knowledge(
        self, user_id: UUID, scope: str, scope_id: UUID
    ) -> bool:
        """Check if user can create/edit/delete documents/folders in a scope.

        Args:
            user_id: The user's ID
            scope: One of "personal", "application", "project"
            scope_id: The scope entity ID (user_id, application_id, or project_id)

        Returns:
            True if user can edit knowledge in this scope.
        """
        if scope == "personal":
            return scope_id == user_id
        elif scope == "application":
            role = await self.get_user_application_role(user_id, scope_id)
            return role in ("owner", "editor")
        elif scope == "project":
            project = await self.get_project_with_application(scope_id)
            if not project:
                return False
            app_role = await self.get_user_application_role(
                user_id, project.application_id
            )
            if app_role == "owner":
                return True
            if app_role not in ("editor",):
                # Viewers and non-members cannot edit project knowledge
                return False
            return await self.is_project_member(user_id, scope_id)
        return False

    @staticmethod
    def resolve_entity_scope(entity) -> tuple[str, UUID]:
        """Extract (scope_type, scope_id) from a Document or DocumentFolder.

        Args:
            entity: A Document or DocumentFolder instance

        Returns:
            Tuple of (scope_type_str, scope_id_uuid)

        Raises:
            ValueError: If entity has no scope FK set
        """
        if entity.application_id:
            return "application", entity.application_id
        elif entity.project_id:
            return "project", entity.project_id
        elif entity.user_id:
            return "personal", entity.user_id
        raise ValueError("Entity has no scope FK set")

    async def check_can_manage_tasks(
        self,
        user: User,
        project_id: UUID,
        application_id: Optional[UUID] = None,
    ) -> bool:
        """
        Check if a user can create, edit, move, or delete tasks in a project.

        Permission rules:
        - Application Owner: Super admin - always can manage tasks
        - Application Editor: Only if they are a ProjectMember (admin or member role)
        - Application Viewer: Never can manage tasks (read-only)

        Args:
            user: The user to check permissions for
            project_id: The project's ID
            application_id: Optional application ID (will be fetched if not provided)

        Returns:
            True if user can manage tasks, False otherwise.
        """
        # Get application_id from project if not provided
        if application_id is None:
            project = await self.get_project_with_application(project_id)
            if not project:
                return False
            application_id = project.application_id
            application = project.application
        else:
            application = None

        # Get user's application role
        app_role = await self.get_user_application_role(user.id, application_id, application)

        if not app_role:
            return False

        # Application Owners have super admin access
        if app_role == "owner":
            return True

        # Viewers never have edit access
        if app_role == "viewer":
            return False

        # Editors must be project member with admin or member role
        project_role = await self.get_project_member_role(user.id, project_id)
        return project_role in ("admin", "member")

    async def check_can_view_project(
        self,
        user: User,
        project_id: UUID,
        application_id: Optional[UUID] = None,
    ) -> bool:
        """
        Check if a user can view a project and its tasks.

        Permission rules:
        - Any application member (owner, editor, viewer) can view projects

        Args:
            user: The user to check permissions for
            project_id: The project's ID
            application_id: Optional application ID (will be fetched if not provided)

        Returns:
            True if user can view the project, False otherwise.
        """
        # Get application_id from project if not provided
        if application_id is None:
            project = await self.get_project_with_application(project_id)
            if not project:
                return False
            application_id = project.application_id
            application = project.application
        else:
            application = None

        # Get user's application role
        role = await self.get_user_application_role(user.id, application_id, application)

        # Any role means view access
        return role is not None

    async def check_can_be_assigned(
        self,
        user_id: UUID,
        project_id: UUID,
        application_id: Optional[UUID] = None,
    ) -> bool:
        """
        Check if a user can be assigned to tasks in a project.

        Assignment eligibility rules:
        - Must be a ProjectMember
        - Must have Owner or Editor role in the application
        - Viewers cannot be assigned to tasks

        Args:
            user_id: The user's ID to check eligibility for
            project_id: The project's ID
            application_id: Optional application ID (will be fetched if not provided)

        Returns:
            True if user can be assigned to tasks, False otherwise.
        """
        # Get application_id from project if not provided
        if application_id is None:
            project = await self.get_project_with_application(project_id)
            if not project:
                return False
            application_id = project.application_id
            application = project.application
        else:
            application = None

        # Get user's application role
        role = await self.get_user_application_role(user_id, application_id, application)

        # Must have a role and not be a viewer
        if not role or role == "viewer":
            return False

        # Must be a ProjectMember
        return await self.is_project_member(user_id, project_id)

    async def check_can_manage_project_members(
        self,
        user: User,
        project_id: UUID,
        application_id: Optional[UUID] = None,
    ) -> bool:
        """
        Check if a user can add or remove project members.

        Permission rules:
        - Application Owner: Super admin - can always manage members
        - Project Admin: Can manage members within their project
        - Application Editor (not project admin): Cannot manage members
        - Application Viewer: Cannot manage members

        Args:
            user: The user to check permissions for
            project_id: The project's ID
            application_id: Optional application ID (will be fetched if not provided)

        Returns:
            True if user can manage project members, False otherwise.
        """
        # Get application_id from project if not provided
        if application_id is None:
            project = await self.get_project_with_application(project_id)
            if not project:
                return False
            application_id = project.application_id
            application = project.application
        else:
            application = None

        # Get user's application role
        app_role = await self.get_user_application_role(user.id, application_id, application)

        if not app_role:
            return False

        # Application Owners have super admin access
        if app_role == "owner":
            return True

        # Viewers cannot manage members
        if app_role == "viewer":
            return False

        # Editors must be project admin to manage members
        project_role = await self.get_project_member_role(user.id, project_id)
        return project_role == "admin"

    async def check_can_view_project_members(
        self,
        user: User,
        project_id: UUID,
        application_id: Optional[UUID] = None,
    ) -> bool:
        """
        Check if a user can view the project member list.

        Permission rules:
        - Any application member (owner/editor/viewer) can view project members

        Args:
            user: The user to check permissions for
            project_id: The project's ID
            application_id: Optional application ID (will be fetched if not provided)

        Returns:
            True if user can view project members, False otherwise.
        """
        # Get application_id from project if not provided
        if application_id is None:
            project = await self.get_project_with_application(project_id)
            if not project:
                return False
            application_id = project.application_id
            application = project.application
        else:
            application = None

        # Get user's application role
        app_role = await self.get_user_application_role(user.id, application_id, application)

        # Any application member can view project members
        return app_role is not None

    async def check_can_override_project_status(
        self,
        user: User,
        project_id: UUID,
        application_id: Optional[UUID] = None,
    ) -> bool:
        """
        Check if a user can override a project's derived status.

        Permission rules:
        - Only Application Owners can override project status
        - Editors and Viewers cannot override status

        Args:
            user: The user to check permissions for
            project_id: The project's ID
            application_id: Optional application ID (will be fetched if not provided)

        Returns:
            True if user can override project status, False otherwise.
        """
        # Get application_id from project if not provided
        if application_id is None:
            project = await self.get_project_with_application(project_id)
            if not project:
                return False
            application_id = project.application_id
            application = project.application
        else:
            application = None

        # Only application owners can override project status
        app_role = await self.get_user_application_role(user.id, application_id, application)
        return app_role == "owner"

    async def get_assignable_users_for_project(
        self,
        project_id: UUID,
        application_id: Optional[UUID] = None,
    ) -> list[User]:
        """
        Get all users who can be assigned to tasks in a project.

        Returns:
        - All Project Members (admin/member roles) who are App Owners or Editors
        - All App Owners (even if not project members)

        Args:
            project_id: The project's ID
            application_id: Optional application ID (will be fetched if not provided)

        Returns:
            List of User objects who can be assigned to tasks.
        """
        # Get application_id from project if not provided
        if application_id is None:
            project = await self.get_project_with_application(project_id)
            if not project:
                return []
            application_id = project.application_id
            application = project.application
        else:
            project = None
            result = await self.db.execute(
                select(Application).where(Application.id == application_id)
            )
            application = result.scalar_one_or_none()

        if not application:
            return []

        # Single query: project members who are also app owners or editors
        from sqlalchemy import or_, union_all, literal_column
        pm_users = (
            select(User)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
            .where(
                or_(
                    # App owner by ownership
                    User.id == application.owner_id,
                    # App member with owner or editor role
                    User.id.in_(
                        select(ApplicationMember.user_id).where(
                            ApplicationMember.application_id == application_id,
                            ApplicationMember.role.in_(["owner", "editor"]),
                        )
                    ),
                )
            )
        )

        # App owners (even if not project members)
        app_owner_users = (
            select(User)
            .where(
                or_(
                    User.id == application.owner_id,
                    User.id.in_(
                        select(ApplicationMember.user_id).where(
                            ApplicationMember.application_id == application_id,
                            ApplicationMember.role == "owner",
                        )
                    ),
                )
            )
        )

        # Combine and deduplicate
        combined = union_all(pm_users, app_owner_users).subquery()
        result = await self.db.execute(
            select(User).where(User.id.in_(select(combined.c.id)))
        )
        return list(result.scalars().all())


def get_permission_service(db: AsyncSession) -> PermissionService:
    """
    Factory function to create a PermissionService instance.

    Args:
        db: SQLAlchemy async database session

    Returns:
        PermissionService instance
    """
    return PermissionService(db)


# ---------------------------------------------------------------------------
# Standalone convenience wrappers (avoid duplicating logic in routers)
# ---------------------------------------------------------------------------


async def get_user_application_role(
    db: AsyncSession,
    user_id: UUID,
    application_id: UUID,
    application: Optional[Application] = None,
) -> Optional[str]:
    """Standalone wrapper around PermissionService.get_user_application_role."""
    return await PermissionService(db).get_user_application_role(
        user_id, application_id, application
    )


async def is_application_owner(
    db: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user is the owner of the application."""
    role = await PermissionService(db).get_user_application_role(user_id, application_id)
    return role == "owner"


async def is_application_member(
    db: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user is a member of the application (any role).

    Delegates to PermissionService.is_application_member which uses
    an optimized UNION ALL EXISTS query (single round-trip).
    """
    return await PermissionService(db).is_application_member(user_id, application_id)


async def can_edit_application(
    db: AsyncSession,
    user_id: UUID,
    application_id: UUID,
) -> bool:
    """Check if the user can edit the application (owner or editor)."""
    return await PermissionService(db).can_edit_application(user_id, application_id)
