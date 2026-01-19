"""Permission service for role checks and ProjectMember gate logic.

This service implements the 3-tier permission model (Owner/Editor/Viewer)
with ProjectMember gate for Editors. It centralizes permission checks
to ensure consistent enforcement across the application.

Permission Model:
- Application Owner: Full access to all projects and tasks within the application
- Application Editor: Can only manage tasks in projects where they are ProjectMembers
- Application Viewer: Read-only access, cannot create/edit/delete tasks

Assignment Rules:
- Only ProjectMembers who are Owner/Editor can be assigned to tasks
- Viewers cannot be assigned to tasks
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

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

    def __init__(self, db: Session):
        """
        Initialize the PermissionService.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def get_user_application_role(
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
            application = self.db.query(Application).filter(
                Application.id == application_id
            ).first()

        if not application:
            return None

        # Check if user is the original owner
        if application.owner_id == user_id:
            return "owner"

        # Check ApplicationMembers table
        member = self.db.query(ApplicationMember).filter(
            ApplicationMember.application_id == application_id,
            ApplicationMember.user_id == user_id,
        ).first()

        return member.role if member else None

    def is_project_member(
        self,
        user_id: UUID,
        project_id: UUID,
    ) -> bool:
        """
        Check if a user is a member of a project.

        Args:
            user_id: The user's ID
            project_id: The project's ID

        Returns:
            True if user is a ProjectMember, False otherwise.
        """
        member = self.db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        ).first()

        return member is not None

    def get_project_with_application(
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
        from sqlalchemy.orm import joinedload

        return self.db.query(Project).options(
            joinedload(Project.application)
        ).filter(
            Project.id == project_id,
        ).first()

    def check_can_manage_tasks(
        self,
        user: User,
        project_id: UUID,
        application_id: Optional[UUID] = None,
    ) -> bool:
        """
        Check if a user can create, edit, move, or delete tasks in a project.

        Permission rules:
        - Application Owner: Always can manage tasks (no ProjectMember gate)
        - Application Editor: Only if they are a ProjectMember
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
            project = self.get_project_with_application(project_id)
            if not project:
                return False
            application_id = project.application_id
            application = project.application
        else:
            application = None

        # Get user's application role
        role = self.get_user_application_role(user.id, application_id, application)

        if not role:
            return False

        # Owners always have full access
        if role == "owner":
            return True

        # Editors need to be ProjectMembers
        if role == "editor":
            return self.is_project_member(user.id, project_id)

        # Viewers cannot manage tasks
        return False

    def check_can_view_project(
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
            project = self.get_project_with_application(project_id)
            if not project:
                return False
            application_id = project.application_id
            application = project.application
        else:
            application = None

        # Get user's application role
        role = self.get_user_application_role(user.id, application_id, application)

        # Any role means view access
        return role is not None

    def check_can_be_assigned(
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
            project = self.get_project_with_application(project_id)
            if not project:
                return False
            application_id = project.application_id
            application = project.application
        else:
            application = None

        # Get user's application role
        role = self.get_user_application_role(user_id, application_id, application)

        # Must have a role and not be a viewer
        if not role or role == "viewer":
            return False

        # Must be a ProjectMember
        return self.is_project_member(user_id, project_id)

    def check_can_manage_project_members(
        self,
        user: User,
        project_id: UUID,
        application_id: Optional[UUID] = None,
    ) -> bool:
        """
        Check if a user can add or remove project members.

        Permission rules:
        - Only Application Owners can manage project membership
        - Editors cannot manage membership even if they are ProjectMembers
        - Viewers cannot manage membership

        Args:
            user: The user to check permissions for
            project_id: The project's ID
            application_id: Optional application ID (will be fetched if not provided)

        Returns:
            True if user can manage project members, False otherwise.
        """
        # Get application_id from project if not provided
        if application_id is None:
            project = self.get_project_with_application(project_id)
            if not project:
                return False
            application_id = project.application_id
            application = project.application
        else:
            application = None

        # Get user's application role
        role = self.get_user_application_role(user.id, application_id, application)

        # Only owners can manage project members
        return role == "owner"

    def check_can_override_project_status(
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
        # Same permission as managing project members - owner only
        return self.check_can_manage_project_members(user, project_id, application_id)

    def get_assignable_users_for_project(
        self,
        project_id: UUID,
        application_id: Optional[UUID] = None,
    ) -> list[User]:
        """
        Get all users who can be assigned to tasks in a project.

        Returns ProjectMembers who are either Owners or Editors in the application.

        Args:
            project_id: The project's ID
            application_id: Optional application ID (will be fetched if not provided)

        Returns:
            List of User objects who can be assigned to tasks.
        """
        # Get application_id from project if not provided
        if application_id is None:
            project = self.get_project_with_application(project_id)
            if not project:
                return []
            application_id = project.application_id
            application = project.application
        else:
            project = None
            application = None

        # Get all project members
        project_members = self.db.query(ProjectMember).filter(
            ProjectMember.project_id == project_id,
        ).all()

        if not project_members:
            return []

        # Filter to only those with owner/editor role in the application
        assignable_users = []
        for pm in project_members:
            role = self.get_user_application_role(pm.user_id, application_id, application)
            if role in ("owner", "editor"):
                assignable_users.append(pm.user)

        return assignable_users


def get_permission_service(db: Session) -> PermissionService:
    """
    Factory function to create a PermissionService instance.

    Args:
        db: SQLAlchemy database session

    Returns:
        PermissionService instance
    """
    return PermissionService(db)
