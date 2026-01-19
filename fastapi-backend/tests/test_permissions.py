"""Unit tests for the permission service.

Tests cover permission checks for the 3-tier role system:
1. Owner - full access to all projects and tasks
2. Editor with membership - can manage tasks in member projects only
3. Editor without membership - cannot manage tasks in non-member projects
4. Viewer - read-only access, cannot create/edit tasks

Also tests assignment eligibility and project member management permissions.
"""

from unittest.mock import MagicMock, patch, PropertyMock
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
        """Create a mock database session."""
        return MagicMock()

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

    def test_returns_owner_for_application_owner(self):
        """User who owns the application gets 'owner' role."""
        user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()
        mock_app = self._create_mock_application(owner_id=user_id)

        # Configure query to return the application
        mock_db.query.return_value.filter.return_value.first.return_value = mock_app

        service = PermissionService(mock_db)
        result = service.get_user_application_role(user_id, app_id)

        assert result == "owner"

    def test_returns_role_from_application_member(self):
        """User gets role from ApplicationMember if not owner."""
        user_id = uuid4()
        other_user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()
        mock_app = self._create_mock_application(owner_id=other_user_id)
        mock_member = self._create_mock_member(role="editor")

        # First query returns the application
        # Second query returns the member
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_app,  # Application lookup
            mock_member,  # ApplicationMember lookup
        ]

        service = PermissionService(mock_db)
        result = service.get_user_application_role(user_id, app_id)

        assert result == "editor"

    def test_returns_viewer_role(self):
        """User with viewer role gets 'viewer'."""
        user_id = uuid4()
        other_user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()
        mock_app = self._create_mock_application(owner_id=other_user_id)
        mock_member = self._create_mock_member(role="viewer")

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_app,
            mock_member,
        ]

        service = PermissionService(mock_db)
        result = service.get_user_application_role(user_id, app_id)

        assert result == "viewer"

    def test_returns_none_for_non_member(self):
        """User not in application gets None."""
        user_id = uuid4()
        other_user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()
        mock_app = self._create_mock_application(owner_id=other_user_id)

        # Application found, but member not found
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_app,
            None,  # No member record
        ]

        service = PermissionService(mock_db)
        result = service.get_user_application_role(user_id, app_id)

        assert result is None

    def test_returns_none_for_missing_application(self):
        """Returns None when application doesn't exist."""
        user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = PermissionService(mock_db)
        result = service.get_user_application_role(user_id, app_id)

        assert result is None

    def test_uses_provided_application_object(self):
        """Uses provided application object instead of querying."""
        user_id = uuid4()
        app_id = uuid4()

        mock_db = self._create_mock_db()
        mock_app = self._create_mock_application(owner_id=user_id)

        service = PermissionService(mock_db)
        # Pass application object directly
        result = service.get_user_application_role(user_id, app_id, application=mock_app)

        assert result == "owner"
        # Should not query for application
        mock_db.query.assert_not_called()


class TestIsProjectMember:
    """Tests for is_project_member method."""

    def test_returns_true_when_member_exists(self):
        """Returns True when user is a ProjectMember."""
        user_id = uuid4()
        project_id = uuid4()

        mock_db = MagicMock()
        mock_member = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_member

        service = PermissionService(mock_db)
        result = service.is_project_member(user_id, project_id)

        assert result is True

    def test_returns_false_when_not_member(self):
        """Returns False when user is not a ProjectMember."""
        user_id = uuid4()
        project_id = uuid4()

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = PermissionService(mock_db)
        result = service.is_project_member(user_id, project_id)

        assert result is False


class TestCheckCanManageTasks:
    """Tests for check_can_manage_tasks method - core permission logic."""

    def _setup_service_with_mocks(self, role, is_member=False, project_exists=True):
        """Set up a PermissionService with mocked methods."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        # Mock the internal methods
        if project_exists:
            mock_project = MagicMock()
            mock_project.application_id = uuid4()
            mock_project.application = MagicMock()
        else:
            mock_project = None

        service.get_project_with_application = MagicMock(return_value=mock_project)
        service.get_user_application_role = MagicMock(return_value=role)
        service.is_project_member = MagicMock(return_value=is_member)

        return service

    def test_owner_can_always_manage_tasks(self):
        """Application Owner can manage tasks in any project."""
        service = self._setup_service_with_mocks(role="owner", is_member=False)
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        result = service.check_can_manage_tasks(mock_user, project_id)

        assert result is True

    def test_owner_can_manage_without_membership(self):
        """Owner doesn't need to be a ProjectMember to manage tasks."""
        service = self._setup_service_with_mocks(role="owner", is_member=False)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_manage_tasks(mock_user, uuid4())

        assert result is True
        # is_project_member should not be called for owners
        service.is_project_member.assert_not_called()

    def test_editor_with_membership_can_manage_tasks(self):
        """Editor who is a ProjectMember can manage tasks."""
        service = self._setup_service_with_mocks(role="editor", is_member=True)
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        result = service.check_can_manage_tasks(mock_user, project_id)

        assert result is True
        service.is_project_member.assert_called_once()

    def test_editor_without_membership_cannot_manage_tasks(self):
        """Editor who is NOT a ProjectMember cannot manage tasks."""
        service = self._setup_service_with_mocks(role="editor", is_member=False)
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        result = service.check_can_manage_tasks(mock_user, project_id)

        assert result is False
        service.is_project_member.assert_called_once()

    def test_viewer_cannot_manage_tasks(self):
        """Viewer cannot manage tasks even with membership."""
        service = self._setup_service_with_mocks(role="viewer", is_member=True)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_manage_tasks(mock_user, uuid4())

        assert result is False

    def test_viewer_cannot_manage_tasks_without_membership(self):
        """Viewer cannot manage tasks regardless of membership status."""
        service = self._setup_service_with_mocks(role="viewer", is_member=False)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_manage_tasks(mock_user, uuid4())

        assert result is False

    def test_non_member_cannot_manage_tasks(self):
        """User with no application role cannot manage tasks."""
        service = self._setup_service_with_mocks(role=None)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_manage_tasks(mock_user, uuid4())

        assert result is False

    def test_returns_false_for_missing_project(self):
        """Returns False when project doesn't exist."""
        service = self._setup_service_with_mocks(role="owner", project_exists=False)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_manage_tasks(mock_user, uuid4())

        assert result is False


class TestCheckCanViewProject:
    """Tests for check_can_view_project method."""

    def _setup_service_with_mocks(self, role, project_exists=True):
        """Set up a PermissionService with mocked methods."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        if project_exists:
            mock_project = MagicMock()
            mock_project.application_id = uuid4()
            mock_project.application = MagicMock()
        else:
            mock_project = None

        service.get_project_with_application = MagicMock(return_value=mock_project)
        service.get_user_application_role = MagicMock(return_value=role)

        return service

    def test_owner_can_view_project(self):
        """Owner can view any project."""
        service = self._setup_service_with_mocks(role="owner")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_view_project(mock_user, uuid4())

        assert result is True

    def test_editor_can_view_project(self):
        """Editor can view any project in their application."""
        service = self._setup_service_with_mocks(role="editor")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_view_project(mock_user, uuid4())

        assert result is True

    def test_viewer_can_view_project(self):
        """Viewer can view projects (read-only access)."""
        service = self._setup_service_with_mocks(role="viewer")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_view_project(mock_user, uuid4())

        assert result is True

    def test_non_member_cannot_view_project(self):
        """User with no role cannot view project."""
        service = self._setup_service_with_mocks(role=None)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_view_project(mock_user, uuid4())

        assert result is False

    def test_returns_false_for_missing_project(self):
        """Returns False when project doesn't exist."""
        service = self._setup_service_with_mocks(role="owner", project_exists=False)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_view_project(mock_user, uuid4())

        assert result is False


class TestCheckCanBeAssigned:
    """Tests for check_can_be_assigned method - assignment eligibility."""

    def _setup_service_with_mocks(self, role, is_member=False, project_exists=True):
        """Set up a PermissionService with mocked methods."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        if project_exists:
            mock_project = MagicMock()
            mock_project.application_id = uuid4()
            mock_project.application = MagicMock()
        else:
            mock_project = None

        service.get_project_with_application = MagicMock(return_value=mock_project)
        service.get_user_application_role = MagicMock(return_value=role)
        service.is_project_member = MagicMock(return_value=is_member)

        return service

    def test_owner_member_can_be_assigned(self):
        """Owner who is ProjectMember can be assigned to tasks."""
        service = self._setup_service_with_mocks(role="owner", is_member=True)
        user_id = uuid4()
        project_id = uuid4()

        result = service.check_can_be_assigned(user_id, project_id)

        assert result is True

    def test_owner_non_member_cannot_be_assigned(self):
        """Owner who is NOT a ProjectMember cannot be assigned."""
        service = self._setup_service_with_mocks(role="owner", is_member=False)
        user_id = uuid4()
        project_id = uuid4()

        result = service.check_can_be_assigned(user_id, project_id)

        assert result is False

    def test_editor_member_can_be_assigned(self):
        """Editor who is ProjectMember can be assigned to tasks."""
        service = self._setup_service_with_mocks(role="editor", is_member=True)
        user_id = uuid4()
        project_id = uuid4()

        result = service.check_can_be_assigned(user_id, project_id)

        assert result is True

    def test_editor_non_member_cannot_be_assigned(self):
        """Editor who is NOT a ProjectMember cannot be assigned."""
        service = self._setup_service_with_mocks(role="editor", is_member=False)
        user_id = uuid4()
        project_id = uuid4()

        result = service.check_can_be_assigned(user_id, project_id)

        assert result is False

    def test_viewer_cannot_be_assigned_even_as_member(self):
        """Viewer cannot be assigned to tasks even if ProjectMember."""
        service = self._setup_service_with_mocks(role="viewer", is_member=True)
        user_id = uuid4()
        project_id = uuid4()

        result = service.check_can_be_assigned(user_id, project_id)

        assert result is False
        # Should not even check membership for viewers
        service.is_project_member.assert_not_called()

    def test_viewer_cannot_be_assigned(self):
        """Viewer cannot be assigned to tasks."""
        service = self._setup_service_with_mocks(role="viewer", is_member=False)
        user_id = uuid4()

        result = service.check_can_be_assigned(user_id, uuid4())

        assert result is False

    def test_non_member_cannot_be_assigned(self):
        """User with no application role cannot be assigned."""
        service = self._setup_service_with_mocks(role=None)
        user_id = uuid4()

        result = service.check_can_be_assigned(user_id, uuid4())

        assert result is False


class TestCheckCanManageProjectMembers:
    """Tests for check_can_manage_project_members method."""

    def _setup_service_with_mocks(self, role, project_exists=True):
        """Set up a PermissionService with mocked methods."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        if project_exists:
            mock_project = MagicMock()
            mock_project.application_id = uuid4()
            mock_project.application = MagicMock()
        else:
            mock_project = None

        service.get_project_with_application = MagicMock(return_value=mock_project)
        service.get_user_application_role = MagicMock(return_value=role)

        return service

    def test_owner_can_manage_project_members(self):
        """Only Owner can add/remove project members."""
        service = self._setup_service_with_mocks(role="owner")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_manage_project_members(mock_user, uuid4())

        assert result is True

    def test_editor_cannot_manage_project_members(self):
        """Editor cannot manage project membership."""
        service = self._setup_service_with_mocks(role="editor")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_manage_project_members(mock_user, uuid4())

        assert result is False

    def test_viewer_cannot_manage_project_members(self):
        """Viewer cannot manage project membership."""
        service = self._setup_service_with_mocks(role="viewer")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_manage_project_members(mock_user, uuid4())

        assert result is False

    def test_non_member_cannot_manage_project_members(self):
        """Non-application member cannot manage project members."""
        service = self._setup_service_with_mocks(role=None)
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_manage_project_members(mock_user, uuid4())

        assert result is False


class TestCheckCanOverrideProjectStatus:
    """Tests for check_can_override_project_status method."""

    def _setup_service_with_mocks(self, role, project_exists=True):
        """Set up a PermissionService with mocked methods."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        if project_exists:
            mock_project = MagicMock()
            mock_project.application_id = uuid4()
            mock_project.application = MagicMock()
        else:
            mock_project = None

        service.get_project_with_application = MagicMock(return_value=mock_project)
        service.get_user_application_role = MagicMock(return_value=role)

        return service

    def test_owner_can_override_status(self):
        """Only Owner can override project status."""
        service = self._setup_service_with_mocks(role="owner")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_override_project_status(mock_user, uuid4())

        assert result is True

    def test_editor_cannot_override_status(self):
        """Editor cannot override project status."""
        service = self._setup_service_with_mocks(role="editor")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_override_project_status(mock_user, uuid4())

        assert result is False

    def test_viewer_cannot_override_status(self):
        """Viewer cannot override project status."""
        service = self._setup_service_with_mocks(role="viewer")
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = service.check_can_override_project_status(mock_user, uuid4())

        assert result is False


class TestGetAssignableUsersForProject:
    """Tests for get_assignable_users_for_project method."""

    def test_returns_owner_and_editor_members(self):
        """Returns ProjectMembers who are Owners or Editors."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        project_id = uuid4()
        app_id = uuid4()

        # Create mock project
        mock_project = MagicMock()
        mock_project.application_id = app_id
        mock_project.application = MagicMock()
        service.get_project_with_application = MagicMock(return_value=mock_project)

        # Create mock project members
        owner_user = MagicMock()
        owner_user.id = uuid4()
        owner_member = MagicMock()
        owner_member.user_id = owner_user.id
        owner_member.user = owner_user

        editor_user = MagicMock()
        editor_user.id = uuid4()
        editor_member = MagicMock()
        editor_member.user_id = editor_user.id
        editor_member.user = editor_user

        viewer_user = MagicMock()
        viewer_user.id = uuid4()
        viewer_member = MagicMock()
        viewer_member.user_id = viewer_user.id
        viewer_member.user = viewer_user

        # Mock ProjectMember query
        mock_db.query.return_value.filter.return_value.all.return_value = [
            owner_member,
            editor_member,
            viewer_member,
        ]

        # Mock role lookups - owner, editor, viewer
        def get_role(user_id, app_id, app=None):
            if user_id == owner_user.id:
                return "owner"
            elif user_id == editor_user.id:
                return "editor"
            else:
                return "viewer"

        service.get_user_application_role = MagicMock(side_effect=get_role)

        result = service.get_assignable_users_for_project(project_id)

        # Should return owner and editor, but not viewer
        assert len(result) == 2
        assert owner_user in result
        assert editor_user in result
        assert viewer_user not in result

    def test_returns_empty_for_no_members(self):
        """Returns empty list when project has no members."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)

        mock_project = MagicMock()
        mock_project.application_id = uuid4()
        service.get_project_with_application = MagicMock(return_value=mock_project)

        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = service.get_assignable_users_for_project(uuid4())

        assert result == []

    def test_returns_empty_for_missing_project(self):
        """Returns empty list when project doesn't exist."""
        mock_db = MagicMock()
        service = PermissionService(mock_db)
        service.get_project_with_application = MagicMock(return_value=None)

        result = service.get_assignable_users_for_project(uuid4())

        assert result == []


class TestPermissionRulesIntegration:
    """Integration tests verifying permission rule priorities."""

    def _create_service(self):
        """Create a PermissionService with mock DB."""
        mock_db = MagicMock()
        return PermissionService(mock_db)

    def test_permission_hierarchy(self):
        """Verify permission hierarchy: Owner > Editor > Viewer."""
        # Create service with mock methods
        service = self._create_service()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        # Mock project lookup
        mock_project = MagicMock()
        mock_project.application_id = uuid4()
        mock_project.application = MagicMock()
        service.get_project_with_application = MagicMock(return_value=mock_project)
        service.is_project_member = MagicMock(return_value=True)

        # Test Owner permissions
        service.get_user_application_role = MagicMock(return_value="owner")
        assert service.check_can_manage_tasks(mock_user, project_id) is True
        assert service.check_can_view_project(mock_user, project_id) is True
        assert service.check_can_manage_project_members(mock_user, project_id) is True
        assert service.check_can_override_project_status(mock_user, project_id) is True

        # Test Editor permissions (with membership)
        service.get_user_application_role = MagicMock(return_value="editor")
        assert service.check_can_manage_tasks(mock_user, project_id) is True
        assert service.check_can_view_project(mock_user, project_id) is True
        assert service.check_can_manage_project_members(mock_user, project_id) is False
        assert service.check_can_override_project_status(mock_user, project_id) is False

        # Test Viewer permissions
        service.get_user_application_role = MagicMock(return_value="viewer")
        assert service.check_can_manage_tasks(mock_user, project_id) is False
        assert service.check_can_view_project(mock_user, project_id) is True
        assert service.check_can_manage_project_members(mock_user, project_id) is False
        assert service.check_can_override_project_status(mock_user, project_id) is False

    def test_project_member_gate_for_editors(self):
        """Verify ProjectMember gate only applies to Editors."""
        service = self._create_service()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        project_id = uuid4()

        mock_project = MagicMock()
        mock_project.application_id = uuid4()
        mock_project.application = MagicMock()
        service.get_project_with_application = MagicMock(return_value=mock_project)

        # Owner bypasses ProjectMember gate
        service.get_user_application_role = MagicMock(return_value="owner")
        service.is_project_member = MagicMock(return_value=False)
        assert service.check_can_manage_tasks(mock_user, project_id) is True

        # Editor requires ProjectMember gate
        service.get_user_application_role = MagicMock(return_value="editor")

        service.is_project_member = MagicMock(return_value=False)
        assert service.check_can_manage_tasks(mock_user, project_id) is False

        service.is_project_member = MagicMock(return_value=True)
        assert service.check_can_manage_tasks(mock_user, project_id) is True

    def test_assignment_requires_both_role_and_membership(self):
        """Verify assignment requires both Owner/Editor role AND ProjectMember."""
        service = self._create_service()
        user_id = uuid4()
        project_id = uuid4()

        mock_project = MagicMock()
        mock_project.application_id = uuid4()
        mock_project.application = MagicMock()
        service.get_project_with_application = MagicMock(return_value=mock_project)

        # Owner + Member = assignable
        service.get_user_application_role = MagicMock(return_value="owner")
        service.is_project_member = MagicMock(return_value=True)
        assert service.check_can_be_assigned(user_id, project_id) is True

        # Owner + NOT Member = NOT assignable
        service.is_project_member = MagicMock(return_value=False)
        assert service.check_can_be_assigned(user_id, project_id) is False

        # Editor + Member = assignable
        service.get_user_application_role = MagicMock(return_value="editor")
        service.is_project_member = MagicMock(return_value=True)
        assert service.check_can_be_assigned(user_id, project_id) is True

        # Editor + NOT Member = NOT assignable
        service.is_project_member = MagicMock(return_value=False)
        assert service.check_can_be_assigned(user_id, project_id) is False

        # Viewer = NEVER assignable (role check happens first)
        service.get_user_application_role = MagicMock(return_value="viewer")
        service.is_project_member = MagicMock(return_value=True)  # Even if member
        assert service.check_can_be_assigned(user_id, project_id) is False
