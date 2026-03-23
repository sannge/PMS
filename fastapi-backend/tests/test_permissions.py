"""Unit tests for the permission service.

Tests cover permission checks for the 3-tier role system:
1. Owner - full access to all projects and tasks
2. Editor with membership - can manage tasks in member projects only
3. Editor without membership - cannot manage tasks in non-member projects
4. Viewer - read-only access, cannot create/edit tasks

Also tests assignment eligibility and project member management permissions.

All PermissionService methods are async, so tests use AsyncMock and await.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.permission_service import PermissionService, get_permission_service


class TestPermissionServiceInit:
    """Tests for PermissionService initialization."""

    def test_init_stores_db_session(self):
        """PermissionService stores the database session."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)
        assert service.db is mock_db

    def test_get_permission_service_factory(self):
        """get_permission_service creates a PermissionService instance."""
        mock_db = MagicMock()
        service = get_permission_service(mock_db)
        assert isinstance(service, PermissionService)
        assert service.db is mock_db


class TestGetUserApplicationRole:
    """Tests for get_user_application_role method."""

    def _create_mock_db(self):
        """Create a mock async database session."""
        return AsyncMock()

    def _create_mock_application(self, owner_id):
        """Create a mock Application with an owner."""
        app = MagicMock()
        app.owner_id = owner_id
        return app

    def _create_mock_member(self, role):
        """Create a mock ApplicationMember with a role."""
        member = MagicMock()
        member.role = role
        return member

    async def test_returns_owner_for_application_owner(self):
        """User who owns the application gets 'owner' role."""
        user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()

        # Single JOIN query: result.first() returns (owner_id, member_role)
        mock_result = MagicMock()
        mock_result.first.return_value = (user_id, None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PermissionService(mock_db)
        result = await service.get_user_application_role(user_id, app_id)

        assert result == "owner"

    async def test_returns_role_from_application_member(self):
        """User gets role from ApplicationMember if not owner."""
        user_id = uuid4()
        other_user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()

        # Single JOIN query: result.first() returns (owner_id, member_role)
        mock_result = MagicMock()
        mock_result.first.return_value = (other_user_id, "editor")
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PermissionService(mock_db)
        result = await service.get_user_application_role(user_id, app_id)

        assert result == "editor"

    async def test_returns_viewer_role(self):
        """User with viewer role gets 'viewer'."""
        user_id = uuid4()
        other_user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()

        # Single JOIN query: result.first() returns (owner_id, member_role)
        mock_result = MagicMock()
        mock_result.first.return_value = (other_user_id, "viewer")
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PermissionService(mock_db)
        result = await service.get_user_application_role(user_id, app_id)

        assert result == "viewer"

    async def test_returns_none_for_non_member(self):
        """User not in application gets None."""
        user_id = uuid4()
        other_user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()

        # Single JOIN query: app exists but no member record (role is None)
        mock_result = MagicMock()
        mock_result.first.return_value = (other_user_id, None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PermissionService(mock_db)
        result = await service.get_user_application_role(user_id, app_id)

        assert result is None

    async def test_returns_none_for_missing_application(self):
        """Returns None when application doesn't exist."""
        user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()

        # Single JOIN query: no row returned (application doesn't exist)
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PermissionService(mock_db)
        result = await service.get_user_application_role(user_id, app_id)

        assert result is None

    async def test_uses_provided_application_object(self):
        """Uses provided application object instead of querying."""
        user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()
        mock_app = self._create_mock_application(owner_id=user_id)

        service = PermissionService(mock_db)
        # Pass application object directly — no db.execute needed for app lookup
        result = await service.get_user_application_role(user_id, app_id, application=mock_app)

        assert result == "owner"
        # Should not query for application (owner short-circuits before member query)
        mock_db.execute.assert_not_awaited()


class TestIsProjectMember:
    """Tests for is_project_member method."""

    async def test_returns_true_when_member_exists(self):
        """Returns True when user is a ProjectMember."""
        user_id = uuid4()
        project_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PermissionService(mock_db)
        result = await service.is_project_member(user_id, project_id)

        assert result is True

    async def test_returns_false_when_not_member(self):
        """Returns False when user is not a ProjectMember."""
        user_id = uuid4()
        project_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_db.execute = AsyncMock(return_value=mock_result)

        service = PermissionService(mock_db)
        result = await service.is_project_member(user_id, project_id)

        assert result is False


class TestCheckCanManageTasks:
    """Tests for check_can_manage_tasks method - core permission logic."""

    def _setup_service_with_mocks(self, role, project_member_role="member", project_exists=True):
        """Set up a PermissionService with mocked async methods.

        Args:
            role: Application role ('owner', 'editor', 'viewer', None)
            project_member_role: Project member role for editors ('admin', 'member', None)
            project_exists: Whether the project exists
        """
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        if project_exists:
            mock_project = MagicMock()
            mock_project.application_id = uuid4()
            mock_project.application = MagicMock()
        else:
            mock_project = None

        service.get_project_with_application = AsyncMock(return_value=mock_project)
        service.get_user_application_role = AsyncMock(return_value=role)
        service.get_project_member_role = AsyncMock(return_value=project_member_role)

        return service

    async def test_owner_can_always_manage_tasks(self):
        """Application Owner can manage tasks in any project."""
        service = self._setup_service_with_mocks(role="owner")
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        result = await service.check_can_manage_tasks(mock_user, project_id)

        assert result is True

    async def test_owner_can_manage_without_membership(self):
        """Owner doesn't need to be a ProjectMember to manage tasks."""
        service = self._setup_service_with_mocks(role="owner", project_member_role=None)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_manage_tasks(mock_user, uuid4())

        assert result is True
        # get_project_member_role should not be called for owners
        service.get_project_member_role.assert_not_awaited()

    async def test_editor_with_membership_can_manage_tasks(self):
        """Editor who is a ProjectMember (admin/member) can manage tasks."""
        service = self._setup_service_with_mocks(role="editor", project_member_role="member")
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        result = await service.check_can_manage_tasks(mock_user, project_id)

        assert result is True
        service.get_project_member_role.assert_awaited_once()

    async def test_editor_without_membership_cannot_manage_tasks(self):
        """Editor who is NOT a ProjectMember cannot manage tasks."""
        service = self._setup_service_with_mocks(role="editor", project_member_role=None)
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        result = await service.check_can_manage_tasks(mock_user, project_id)

        assert result is False
        service.get_project_member_role.assert_awaited_once()

    async def test_viewer_cannot_manage_tasks(self):
        """Viewer cannot manage tasks even with membership."""
        service = self._setup_service_with_mocks(role="viewer", project_member_role="member")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_manage_tasks(mock_user, uuid4())

        assert result is False

    async def test_viewer_cannot_manage_tasks_without_membership(self):
        """Viewer cannot manage tasks regardless of membership status."""
        service = self._setup_service_with_mocks(role="viewer", project_member_role=None)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_manage_tasks(mock_user, uuid4())

        assert result is False

    async def test_non_member_cannot_manage_tasks(self):
        """User with no application role cannot manage tasks."""
        service = self._setup_service_with_mocks(role=None)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_manage_tasks(mock_user, uuid4())

        assert result is False

    async def test_returns_false_for_missing_project(self):
        """Returns False when project doesn't exist."""
        service = self._setup_service_with_mocks(role="owner", project_exists=False)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_manage_tasks(mock_user, uuid4())

        assert result is False


class TestCheckCanViewProject:
    """Tests for check_can_view_project method."""

    def _setup_service_with_mocks(self, role, project_exists=True):
        """Set up a PermissionService with mocked async methods."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        if project_exists:
            mock_project = MagicMock()
            mock_project.application_id = uuid4()
            mock_project.application = MagicMock()
        else:
            mock_project = None

        service.get_project_with_application = AsyncMock(return_value=mock_project)
        service.get_user_application_role = AsyncMock(return_value=role)

        return service

    async def test_owner_can_view_project(self):
        """Owner can view any project."""
        service = self._setup_service_with_mocks(role="owner")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_view_project(mock_user, uuid4())

        assert result is True

    async def test_editor_can_view_project(self):
        """Editor can view any project in their application."""
        service = self._setup_service_with_mocks(role="editor")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_view_project(mock_user, uuid4())

        assert result is True

    async def test_viewer_can_view_project(self):
        """Viewer can view projects (read-only access)."""
        service = self._setup_service_with_mocks(role="viewer")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_view_project(mock_user, uuid4())

        assert result is True

    async def test_non_member_cannot_view_project(self):
        """User with no role cannot view project."""
        service = self._setup_service_with_mocks(role=None)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_view_project(mock_user, uuid4())

        assert result is False

    async def test_returns_false_for_missing_project(self):
        """Returns False when project doesn't exist."""
        service = self._setup_service_with_mocks(role="owner", project_exists=False)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_view_project(mock_user, uuid4())

        assert result is False


class TestCheckCanBeAssigned:
    """Tests for check_can_be_assigned method - assignment eligibility."""

    def _setup_service_with_mocks(self, role, is_member=False, project_exists=True):
        """Set up a PermissionService with mocked async methods."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        if project_exists:
            mock_project = MagicMock()
            mock_project.application_id = uuid4()
            mock_project.application = MagicMock()
        else:
            mock_project = None

        service.get_project_with_application = AsyncMock(return_value=mock_project)
        service.get_user_application_role = AsyncMock(return_value=role)
        service.is_project_member = AsyncMock(return_value=is_member)

        return service

    async def test_owner_member_can_be_assigned(self):
        """Owner who is ProjectMember can be assigned to tasks."""
        service = self._setup_service_with_mocks(role="owner", is_member=True)
        user_id = uuid4()
        project_id = uuid4()

        result = await service.check_can_be_assigned(user_id, project_id)

        assert result is True

    async def test_owner_non_member_can_be_assigned(self):
        """Owner who is NOT a ProjectMember can still be assigned (owner guard)."""
        service = self._setup_service_with_mocks(role="owner", is_member=False)
        user_id = uuid4()
        project_id = uuid4()

        result = await service.check_can_be_assigned(user_id, project_id)

        assert result is True

    async def test_editor_member_can_be_assigned(self):
        """Editor who is ProjectMember can be assigned to tasks."""
        service = self._setup_service_with_mocks(role="editor", is_member=True)
        user_id = uuid4()
        project_id = uuid4()

        result = await service.check_can_be_assigned(user_id, project_id)

        assert result is True

    async def test_editor_non_member_cannot_be_assigned(self):
        """Editor who is NOT a ProjectMember cannot be assigned."""
        service = self._setup_service_with_mocks(role="editor", is_member=False)
        user_id = uuid4()
        project_id = uuid4()

        result = await service.check_can_be_assigned(user_id, project_id)

        assert result is False

    async def test_viewer_cannot_be_assigned_even_as_member(self):
        """Viewer cannot be assigned to tasks even if ProjectMember."""
        service = self._setup_service_with_mocks(role="viewer", is_member=True)
        user_id = uuid4()
        project_id = uuid4()

        result = await service.check_can_be_assigned(user_id, project_id)

        assert result is False
        # Should not even check membership for viewers
        service.is_project_member.assert_not_awaited()

    async def test_viewer_cannot_be_assigned(self):
        """Viewer cannot be assigned to tasks."""
        service = self._setup_service_with_mocks(role="viewer", is_member=False)
        user_id = uuid4()

        result = await service.check_can_be_assigned(user_id, uuid4())

        assert result is False

    async def test_non_member_cannot_be_assigned(self):
        """User with no application role cannot be assigned."""
        service = self._setup_service_with_mocks(role=None)
        user_id = uuid4()

        result = await service.check_can_be_assigned(user_id, uuid4())

        assert result is False


class TestCheckCanManageProjectMembers:
    """Tests for check_can_manage_project_members method."""

    def _setup_service_with_mocks(self, role, project_member_role=None, project_exists=True):
        """Set up a PermissionService with mocked async methods."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        if project_exists:
            mock_project = MagicMock()
            mock_project.application_id = uuid4()
            mock_project.application = MagicMock()
        else:
            mock_project = None

        service.get_project_with_application = AsyncMock(return_value=mock_project)
        service.get_user_application_role = AsyncMock(return_value=role)
        service.get_project_member_role = AsyncMock(return_value=project_member_role)

        return service

    async def test_owner_can_manage_project_members(self):
        """Only Owner can add/remove project members."""
        service = self._setup_service_with_mocks(role="owner")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_manage_project_members(mock_user, uuid4())

        assert result is True

    async def test_editor_cannot_manage_project_members(self):
        """Editor without project admin role cannot manage project membership."""
        service = self._setup_service_with_mocks(role="editor", project_member_role="member")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_manage_project_members(mock_user, uuid4())

        assert result is False

    async def test_viewer_cannot_manage_project_members(self):
        """Viewer cannot manage project membership."""
        service = self._setup_service_with_mocks(role="viewer")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_manage_project_members(mock_user, uuid4())

        assert result is False

    async def test_non_member_cannot_manage_project_members(self):
        """Non-application member cannot manage project members."""
        service = self._setup_service_with_mocks(role=None)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_manage_project_members(mock_user, uuid4())

        assert result is False


class TestCheckCanOverrideProjectStatus:
    """Tests for check_can_override_project_status method."""

    def _setup_service_with_mocks(self, role, project_member_role=None, project_exists=True):
        """Set up a PermissionService with mocked async methods."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        if project_exists:
            mock_project = MagicMock()
            mock_project.application_id = uuid4()
            mock_project.application = MagicMock()
        else:
            mock_project = None

        service.get_project_with_application = AsyncMock(return_value=mock_project)
        service.get_user_application_role = AsyncMock(return_value=role)
        service.get_project_member_role = AsyncMock(return_value=project_member_role)

        return service

    async def test_owner_can_override_status(self):
        """Only Owner can override project status."""
        service = self._setup_service_with_mocks(role="owner")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_override_project_status(mock_user, uuid4())

        assert result is True

    async def test_editor_cannot_override_status(self):
        """Editor cannot override project status."""
        service = self._setup_service_with_mocks(role="editor", project_member_role="member")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_override_project_status(mock_user, uuid4())

        assert result is False

    async def test_viewer_cannot_override_status(self):
        """Viewer cannot override project status."""
        service = self._setup_service_with_mocks(role="viewer")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await service.check_can_override_project_status(mock_user, uuid4())

        assert result is False


class TestGetAssignableUsersForProject:
    """Tests for get_assignable_users_for_project method."""

    async def test_returns_owner_and_editor_members(self):
        """Returns ProjectMembers who are Owners or Editors."""
        mock_db = AsyncMock()
        service = PermissionService(mock_db)

        project_id = uuid4()
        app_id = uuid4()

        # Create mock project with application
        mock_project = MagicMock()
        mock_project.application_id = app_id
        mock_app = MagicMock()
        mock_app.owner_id = uuid4()
        mock_project.application = mock_app
        service.get_project_with_application = AsyncMock(return_value=mock_project)

        # Create mock users
        owner_user = MagicMock()
        owner_user.id = uuid4()
        editor_user = MagicMock()
        editor_user.id = uuid4()

        # Single UNION ALL query: db.execute returns User objects via scalars().all()
        combined_result = MagicMock()
        combined_result.scalars.return_value.all.return_value = [owner_user, editor_user]
        mock_db.execute = AsyncMock(return_value=combined_result)

        result = await service.get_assignable_users_for_project(project_id)

        assert owner_user in result
        assert editor_user in result
        assert len(result) == 2

    async def test_returns_empty_for_no_members(self):
        """Returns empty list when project has no members (only app owner)."""
        mock_db = AsyncMock()
        service = PermissionService(mock_db)

        mock_project = MagicMock()
        mock_project.application_id = uuid4()
        mock_app = MagicMock()
        mock_app.owner_id = uuid4()
        mock_project.application = mock_app
        service.get_project_with_application = AsyncMock(return_value=mock_project)

        # App owner returned from the single UNION ALL query
        app_owner_user = MagicMock()
        app_owner_user.id = mock_app.owner_id
        combined_result = MagicMock()
        combined_result.scalars.return_value.all.return_value = [app_owner_user]
        mock_db.execute = AsyncMock(return_value=combined_result)

        result = await service.get_assignable_users_for_project(uuid4())

        # Only app owner is returned
        assert len(result) == 1
        assert app_owner_user in result

    async def test_returns_empty_for_missing_project(self):
        """Returns empty list when project doesn't exist."""
        mock_db = AsyncMock()
        service = PermissionService(mock_db)
        service.get_project_with_application = AsyncMock(return_value=None)

        result = await service.get_assignable_users_for_project(uuid4())

        assert result == []


class TestPermissionRulesIntegration:
    """Integration tests verifying permission rule priorities."""

    def _create_service(self):
        """Create a PermissionService with mock DB."""
        mock_db = MagicMock()
        return PermissionService(mock_db)

    async def test_permission_hierarchy(self):
        """Verify permission hierarchy: Owner > Editor > Viewer."""
        service = self._create_service()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        # Mock project lookup
        mock_project = MagicMock()
        mock_project.application_id = uuid4()
        mock_project.application = MagicMock()
        service.get_project_with_application = AsyncMock(return_value=mock_project)
        service.get_project_member_role = AsyncMock(return_value="member")

        # Test Owner permissions
        service.get_user_application_role = AsyncMock(return_value="owner")
        assert await service.check_can_manage_tasks(mock_user, project_id) is True
        assert await service.check_can_view_project(mock_user, project_id) is True
        assert await service.check_can_manage_project_members(mock_user, project_id) is True
        assert await service.check_can_override_project_status(mock_user, project_id) is True

        # Test Editor permissions (with membership)
        service.get_user_application_role = AsyncMock(return_value="editor")
        assert await service.check_can_manage_tasks(mock_user, project_id) is True
        assert await service.check_can_view_project(mock_user, project_id) is True
        assert await service.check_can_manage_project_members(mock_user, project_id) is False
        assert await service.check_can_override_project_status(mock_user, project_id) is False

        # Test Viewer permissions
        service.get_user_application_role = AsyncMock(return_value="viewer")
        assert await service.check_can_manage_tasks(mock_user, project_id) is False
        assert await service.check_can_view_project(mock_user, project_id) is True
        assert await service.check_can_manage_project_members(mock_user, project_id) is False
        assert await service.check_can_override_project_status(mock_user, project_id) is False

    async def test_project_member_gate_for_editors(self):
        """Verify ProjectMember gate only applies to Editors."""
        service = self._create_service()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        mock_project = MagicMock()
        mock_project.application_id = uuid4()
        mock_project.application = MagicMock()
        service.get_project_with_application = AsyncMock(return_value=mock_project)

        # Owner bypasses ProjectMember gate
        service.get_user_application_role = AsyncMock(return_value="owner")
        service.get_project_member_role = AsyncMock(return_value=None)
        assert await service.check_can_manage_tasks(mock_user, project_id) is True

        # Editor requires ProjectMember gate
        service.get_user_application_role = AsyncMock(return_value="editor")

        service.get_project_member_role = AsyncMock(return_value=None)
        assert await service.check_can_manage_tasks(mock_user, project_id) is False

        service.get_project_member_role = AsyncMock(return_value="member")
        assert await service.check_can_manage_tasks(mock_user, project_id) is True

    async def test_assignment_requires_both_role_and_membership(self):
        """Verify assignment requires both Owner/Editor role AND ProjectMember."""
        service = self._create_service()
        user_id = uuid4()
        project_id = uuid4()

        mock_project = MagicMock()
        mock_project.application_id = uuid4()
        mock_project.application = MagicMock()
        service.get_project_with_application = AsyncMock(return_value=mock_project)

        # Owner + Member = assignable
        service.get_user_application_role = AsyncMock(return_value="owner")
        service.is_project_member = AsyncMock(return_value=True)
        assert await service.check_can_be_assigned(user_id, project_id) is True

        # Owner + NOT Member = still assignable (owner guard)
        service.is_project_member = AsyncMock(return_value=False)
        assert await service.check_can_be_assigned(user_id, project_id) is True

        # Editor + Member = assignable
        service.get_user_application_role = AsyncMock(return_value="editor")
        service.is_project_member = AsyncMock(return_value=True)
        assert await service.check_can_be_assigned(user_id, project_id) is True

        # Editor + NOT Member = NOT assignable
        service.is_project_member = AsyncMock(return_value=False)
        assert await service.check_can_be_assigned(user_id, project_id) is False

        # Viewer = NEVER assignable (role check happens first)
        service.get_user_application_role = AsyncMock(return_value="viewer")
        service.is_project_member = AsyncMock(return_value=True)  # Even if member
        assert await service.check_can_be_assigned(user_id, project_id) is False
