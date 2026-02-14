"""Unit tests for the status derivation service.

Tests cover all derivation rules:
1. Empty project returns "Todo"
2. All done tasks returns "Done"
3. Any issue task returns "Issue"
4. Active tasks returns "In Progress"
5. Default (only todo) returns "Todo"

Also tests aggregation update functions and helper utilities.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.services.status_derivation_service import (
    ProjectAggregation,
    STATUS_TO_COUNTER_FIELD,
    derive_project_status,
    derive_project_status_from_model,
    get_counter_field_for_status,
    recalculate_aggregation_from_tasks,
    update_aggregation_on_task_create,
    update_aggregation_on_task_delete,
    update_aggregation_on_task_status_change,
)
from app.models.task_status import StatusCategory, StatusName


class TestProjectAggregation:
    """Tests for the ProjectAggregation dataclass."""

    def test_create_aggregation(self):
        """Test creating a ProjectAggregation instance."""
        agg = ProjectAggregation(
            total_tasks=10,
            todo_tasks=3,
            active_tasks=2,
            review_tasks=1,
            issue_tasks=1,
            done_tasks=3,
        )

        assert agg.total_tasks == 10
        assert agg.todo_tasks == 3
        assert agg.active_tasks == 2
        assert agg.review_tasks == 1
        assert agg.issue_tasks == 1
        assert agg.done_tasks == 3

    def test_create_empty_aggregation(self):
        """Test creating an empty ProjectAggregation using class method."""
        agg = ProjectAggregation.empty()

        assert agg.total_tasks == 0
        assert agg.todo_tasks == 0
        assert agg.active_tasks == 0
        assert agg.review_tasks == 0
        assert agg.issue_tasks == 0
        assert agg.done_tasks == 0

    def test_create_from_dict(self):
        """Test creating ProjectAggregation from a dictionary."""
        data = {
            "total_tasks": 5,
            "todo_tasks": 2,
            "active_tasks": 1,
            "review_tasks": 0,
            "issue_tasks": 0,
            "done_tasks": 2,
        }
        agg = ProjectAggregation.from_dict(data)

        assert agg.total_tasks == 5
        assert agg.todo_tasks == 2
        assert agg.active_tasks == 1
        assert agg.review_tasks == 0
        assert agg.issue_tasks == 0
        assert agg.done_tasks == 2

    def test_create_from_partial_dict(self):
        """Test creating ProjectAggregation from a partial dictionary."""
        data = {"total_tasks": 3, "todo_tasks": 3}
        agg = ProjectAggregation.from_dict(data)

        assert agg.total_tasks == 3
        assert agg.todo_tasks == 3
        assert agg.active_tasks == 0
        assert agg.review_tasks == 0
        assert agg.issue_tasks == 0
        assert agg.done_tasks == 0

    def test_negative_count_raises_error(self):
        """Test that negative counts raise ValueError."""
        with pytest.raises(ValueError, match="cannot be negative"):
            ProjectAggregation(
                total_tasks=-1,
                todo_tasks=0,
                active_tasks=0,
                review_tasks=0,
                issue_tasks=0,
                done_tasks=0,
            )

    def test_negative_todo_count_raises_error(self):
        """Test that negative todo_tasks raises ValueError."""
        with pytest.raises(ValueError, match="todo_tasks cannot be negative"):
            ProjectAggregation(
                total_tasks=5,
                todo_tasks=-1,
                active_tasks=0,
                review_tasks=0,
                issue_tasks=0,
                done_tasks=0,
            )


class TestDeriveProjectStatus:
    """Tests for the derive_project_status function."""

    def test_empty_project_returns_todo(self):
        """Rule 1: Empty project (no tasks) returns Todo."""
        agg = ProjectAggregation(
            total_tasks=0,
            todo_tasks=0,
            active_tasks=0,
            review_tasks=0,
            issue_tasks=0,
            done_tasks=0,
        )

        result = derive_project_status(agg)

        assert result == "Todo"

    def test_all_done_returns_done(self):
        """Rule 2: All tasks done returns Done."""
        agg = ProjectAggregation(
            total_tasks=5,
            todo_tasks=0,
            active_tasks=0,
            review_tasks=0,
            issue_tasks=0,
            done_tasks=5,
        )

        result = derive_project_status(agg)

        assert result == "Done"

    def test_any_issue_returns_issue(self):
        """Rule 3: Any issue task returns Issue (issue escalation)."""
        agg = ProjectAggregation(
            total_tasks=5,
            todo_tasks=2,
            active_tasks=1,
            review_tasks=0,
            issue_tasks=1,
            done_tasks=1,
        )

        result = derive_project_status(agg)

        assert result == "Issue"

    def test_single_issue_returns_issue(self):
        """Rule 3: Even a single issue task makes project Issue."""
        agg = ProjectAggregation(
            total_tasks=10,
            todo_tasks=5,
            active_tasks=2,
            review_tasks=1,
            issue_tasks=1,
            done_tasks=1,
        )

        result = derive_project_status(agg)

        assert result == "Issue"

    def test_issue_priority_over_in_progress(self):
        """Rule 3: Issue has higher priority than In Progress."""
        agg = ProjectAggregation(
            total_tasks=3,
            todo_tasks=0,
            active_tasks=1,  # Has active work
            review_tasks=0,
            issue_tasks=1,  # But also has issue
            done_tasks=1,
        )

        result = derive_project_status(agg)

        assert result == "Issue"

    def test_active_work_returns_in_progress(self):
        """Rule 4: Active work (in_progress tasks) returns In Progress."""
        agg = ProjectAggregation(
            total_tasks=5,
            todo_tasks=2,
            active_tasks=2,
            review_tasks=0,
            issue_tasks=0,
            done_tasks=1,
        )

        result = derive_project_status(agg)

        assert result == "In Progress"

    def test_review_tasks_returns_in_progress(self):
        """Rule 4: Review tasks also count as active work."""
        agg = ProjectAggregation(
            total_tasks=5,
            todo_tasks=2,
            active_tasks=0,
            review_tasks=2,
            issue_tasks=0,
            done_tasks=1,
        )

        result = derive_project_status(agg)

        assert result == "In Progress"

    def test_mixed_active_and_review_returns_in_progress(self):
        """Rule 4: Mix of active and review tasks returns In Progress."""
        agg = ProjectAggregation(
            total_tasks=6,
            todo_tasks=2,
            active_tasks=1,
            review_tasks=1,
            issue_tasks=0,
            done_tasks=2,
        )

        result = derive_project_status(agg)

        assert result == "In Progress"

    def test_only_todo_returns_todo(self):
        """Rule 5: Only todo tasks returns Todo."""
        agg = ProjectAggregation(
            total_tasks=5,
            todo_tasks=5,
            active_tasks=0,
            review_tasks=0,
            issue_tasks=0,
            done_tasks=0,
        )

        result = derive_project_status(agg)

        assert result == "Todo"

    def test_todo_and_done_returns_todo(self):
        """Rule 5: Mix of todo and done (no active) returns Todo."""
        agg = ProjectAggregation(
            total_tasks=6,
            todo_tasks=3,
            active_tasks=0,
            review_tasks=0,
            issue_tasks=0,
            done_tasks=3,
        )

        result = derive_project_status(agg)

        assert result == "Todo"

    def test_all_tasks_deleted_returns_todo(self):
        """Edge case: Project that had tasks but now has none returns Todo."""
        agg = ProjectAggregation.empty()

        result = derive_project_status(agg)

        assert result == "Todo"

    def test_single_task_in_progress(self):
        """Single task in progress returns In Progress."""
        agg = ProjectAggregation(
            total_tasks=1,
            todo_tasks=0,
            active_tasks=1,
            review_tasks=0,
            issue_tasks=0,
            done_tasks=0,
        )

        result = derive_project_status(agg)

        assert result == "In Progress"

    def test_single_task_done(self):
        """Single task done returns Done."""
        agg = ProjectAggregation(
            total_tasks=1,
            todo_tasks=0,
            active_tasks=0,
            review_tasks=0,
            issue_tasks=0,
            done_tasks=1,
        )

        result = derive_project_status(agg)

        assert result == "Done"


class TestDeriveProjectStatusFromModel:
    """Tests for the derive_project_status_from_model function."""

    def test_with_none_returns_todo(self):
        """None aggregation model returns Todo."""
        result = derive_project_status_from_model(None)

        assert result == "Todo"

    def test_with_model_instance(self):
        """Model instance is converted to ProjectAggregation."""
        mock_model = MagicMock()
        mock_model.total_tasks = 5
        mock_model.todo_tasks = 0
        mock_model.active_tasks = 0
        mock_model.review_tasks = 0
        mock_model.issue_tasks = 0
        mock_model.done_tasks = 5

        result = derive_project_status_from_model(mock_model)

        assert result == "Done"

    def test_with_null_values_in_model(self):
        """Model with None values treated as zero."""
        mock_model = MagicMock()
        mock_model.total_tasks = None
        mock_model.todo_tasks = None
        mock_model.active_tasks = None
        mock_model.review_tasks = None
        mock_model.issue_tasks = None
        mock_model.done_tasks = None

        result = derive_project_status_from_model(mock_model)

        # All None = all zeros = empty project = Todo
        assert result == "Todo"


class TestGetCounterFieldForStatus:
    """Tests for the get_counter_field_for_status function."""

    def test_todo_maps_to_todo_tasks(self):
        """Todo status maps to todo_tasks counter."""
        result = get_counter_field_for_status("Todo")
        assert result == "todo_tasks"

    def test_in_progress_maps_to_active_tasks(self):
        """In Progress status maps to active_tasks counter."""
        result = get_counter_field_for_status("In Progress")
        assert result == "active_tasks"

    def test_in_review_maps_to_review_tasks(self):
        """In Review status maps to review_tasks counter."""
        result = get_counter_field_for_status("In Review")
        assert result == "review_tasks"

    def test_issue_maps_to_issue_tasks(self):
        """Issue status maps to issue_tasks counter."""
        result = get_counter_field_for_status("Issue")
        assert result == "issue_tasks"

    def test_done_maps_to_done_tasks(self):
        """Done status maps to done_tasks counter."""
        result = get_counter_field_for_status("Done")
        assert result == "done_tasks"

    def test_invalid_status_raises_error(self):
        """Invalid status name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid status name"):
            get_counter_field_for_status("Invalid Status")

    def test_all_status_names_mapped(self):
        """All StatusName enum values have counter field mappings."""
        for status_name in StatusName:
            result = get_counter_field_for_status(status_name.value)
            assert result is not None
            assert result.endswith("_tasks")


class TestUpdateAggregationOnTaskCreate:
    """Tests for the update_aggregation_on_task_create function."""

    def _create_mock_agg(
        self,
        total=0,
        todo=0,
        active=0,
        review=0,
        issue=0,
        done=0,
    ):
        """Create a mock ProjectTaskStatusAgg."""
        mock = MagicMock()
        mock.total_tasks = total
        mock.todo_tasks = todo
        mock.active_tasks = active
        mock.review_tasks = review
        mock.issue_tasks = issue
        mock.done_tasks = done
        mock.updated_at = None
        return mock

    def test_create_todo_task(self):
        """Creating a Todo task increments todo_tasks."""
        agg = self._create_mock_agg()

        new_status = update_aggregation_on_task_create(agg, "Todo")

        assert agg.todo_tasks == 1
        assert agg.total_tasks == 1
        assert agg.updated_at is not None
        assert new_status == "Todo"

    def test_create_in_progress_task(self):
        """Creating an In Progress task increments active_tasks."""
        agg = self._create_mock_agg()

        new_status = update_aggregation_on_task_create(agg, "In Progress")

        assert agg.active_tasks == 1
        assert agg.total_tasks == 1
        assert new_status == "In Progress"

    def test_create_issue_task(self):
        """Creating an Issue task increments issue_tasks and returns Issue status."""
        agg = self._create_mock_agg(total=3, todo=2, done=1)

        new_status = update_aggregation_on_task_create(agg, "Issue")

        assert agg.issue_tasks == 1
        assert agg.total_tasks == 4
        assert new_status == "Issue"

    def test_create_done_task(self):
        """Creating a Done task increments done_tasks."""
        agg = self._create_mock_agg()

        new_status = update_aggregation_on_task_create(agg, "Done")

        assert agg.done_tasks == 1
        assert agg.total_tasks == 1
        assert new_status == "Done"

    def test_create_multiple_tasks(self):
        """Creating multiple tasks increments counters correctly."""
        agg = self._create_mock_agg()

        update_aggregation_on_task_create(agg, "Todo")
        update_aggregation_on_task_create(agg, "Todo")
        update_aggregation_on_task_create(agg, "In Progress")

        assert agg.todo_tasks == 2
        assert agg.active_tasks == 1
        assert agg.total_tasks == 3


class TestUpdateAggregationOnTaskStatusChange:
    """Tests for the update_aggregation_on_task_status_change function."""

    def _create_mock_agg(
        self,
        total=0,
        todo=0,
        active=0,
        review=0,
        issue=0,
        done=0,
    ):
        """Create a mock ProjectTaskStatusAgg."""
        mock = MagicMock()
        mock.total_tasks = total
        mock.todo_tasks = todo
        mock.active_tasks = active
        mock.review_tasks = review
        mock.issue_tasks = issue
        mock.done_tasks = done
        mock.updated_at = None
        return mock

    def test_move_from_todo_to_in_progress(self):
        """Moving task from Todo to In Progress updates both counters."""
        agg = self._create_mock_agg(total=5, todo=3, active=1, done=1)

        new_status = update_aggregation_on_task_status_change(agg, "Todo", "In Progress")

        assert agg.todo_tasks == 2
        assert agg.active_tasks == 2
        assert agg.total_tasks == 5  # Total unchanged
        assert new_status == "In Progress"

    def test_move_from_in_progress_to_done(self):
        """Moving task from In Progress to Done updates counters."""
        agg = self._create_mock_agg(total=3, active=2, done=1)

        new_status = update_aggregation_on_task_status_change(agg, "In Progress", "Done")

        assert agg.active_tasks == 1
        assert agg.done_tasks == 2
        assert agg.total_tasks == 3

    def test_same_status_no_change(self):
        """Same old and new status doesn't change counters."""
        agg = self._create_mock_agg(total=3, todo=1, active=1, done=1)
        original_todo = agg.todo_tasks
        original_active = agg.active_tasks

        update_aggregation_on_task_status_change(agg, "Todo", "Todo")

        assert agg.todo_tasks == original_todo
        assert agg.active_tasks == original_active

    def test_move_to_issue_changes_project_status(self):
        """Moving any task to Issue changes project status to Issue."""
        agg = self._create_mock_agg(total=3, active=2, done=1)

        new_status = update_aggregation_on_task_status_change(agg, "In Progress", "Issue")

        assert agg.active_tasks == 1
        assert agg.issue_tasks == 1
        assert new_status == "Issue"

    def test_move_last_issue_to_done(self):
        """Moving last issue task to Done changes project status."""
        agg = self._create_mock_agg(total=3, todo=0, active=0, issue=1, done=2)

        new_status = update_aggregation_on_task_status_change(agg, "Issue", "Done")

        assert agg.issue_tasks == 0
        assert agg.done_tasks == 3
        assert new_status == "Done"

    def test_counter_cannot_go_negative(self):
        """Counter stays at zero even if decremented from zero."""
        agg = self._create_mock_agg(total=1, todo=0, done=1)

        # Try to decrement todo which is already 0
        update_aggregation_on_task_status_change(agg, "Todo", "Done")

        assert agg.todo_tasks == 0  # Stays at 0, not -1


class TestUpdateAggregationOnTaskDelete:
    """Tests for the update_aggregation_on_task_delete function."""

    def _create_mock_agg(
        self,
        total=0,
        todo=0,
        active=0,
        review=0,
        issue=0,
        done=0,
    ):
        """Create a mock ProjectTaskStatusAgg."""
        mock = MagicMock()
        mock.total_tasks = total
        mock.todo_tasks = todo
        mock.active_tasks = active
        mock.review_tasks = review
        mock.issue_tasks = issue
        mock.done_tasks = done
        mock.updated_at = None
        return mock

    def test_delete_todo_task(self):
        """Deleting a Todo task decrements counters."""
        agg = self._create_mock_agg(total=3, todo=2, done=1)

        new_status = update_aggregation_on_task_delete(agg, "Todo")

        assert agg.todo_tasks == 1
        assert agg.total_tasks == 2

    def test_delete_last_task(self):
        """Deleting last task returns Todo (empty project)."""
        agg = self._create_mock_agg(total=1, active=1)

        new_status = update_aggregation_on_task_delete(agg, "In Progress")

        assert agg.total_tasks == 0
        assert agg.active_tasks == 0
        assert new_status == "Todo"

    def test_delete_issue_task(self):
        """Deleting an Issue task may change project status."""
        agg = self._create_mock_agg(total=3, active=1, issue=1, done=1)

        new_status = update_aggregation_on_task_delete(agg, "Issue")

        assert agg.issue_tasks == 0
        assert agg.total_tasks == 2
        assert new_status == "In Progress"  # No more issues, active work present

    def test_counter_cannot_go_negative(self):
        """Counter stays at zero when deleted from zero."""
        agg = self._create_mock_agg(total=1, done=1, todo=0)

        # Delete a todo task when todo count is 0 (shouldn't happen normally)
        update_aggregation_on_task_delete(agg, "Todo")

        assert agg.todo_tasks == 0  # Stays at 0
        assert agg.total_tasks == 0  # But total still decrements

    def test_delete_all_tasks_returns_todo(self):
        """Deleting all tasks one by one results in Todo status."""
        agg = self._create_mock_agg(total=2, active=1, done=1)

        update_aggregation_on_task_delete(agg, "In Progress")
        result = update_aggregation_on_task_delete(agg, "Done")

        assert agg.total_tasks == 0
        assert result == "Todo"


class TestRecalculateAggregationFromTasks:
    """Tests for the recalculate_aggregation_from_tasks function."""

    def _create_mock_agg(self):
        """Create a mock ProjectTaskStatusAgg."""
        mock = MagicMock()
        mock.total_tasks = 99  # Start with wrong value
        mock.todo_tasks = 99
        mock.active_tasks = 99
        mock.review_tasks = 99
        mock.issue_tasks = 99
        mock.done_tasks = 99
        mock.updated_at = None
        return mock

    def _create_mock_task_with_status_obj(self, status_name):
        """Create a mock task with task_status relationship."""
        mock = MagicMock()
        mock.task_status = MagicMock()
        mock.task_status.name = status_name
        return mock

    def _create_mock_task_with_legacy_status(self, status):
        """Create a mock task with legacy status string."""
        mock = MagicMock()
        mock.task_status = None
        mock.status = status
        return mock

    def test_recalculate_empty_tasks(self):
        """Recalculating with no tasks resets all counters to zero."""
        agg = self._create_mock_agg()

        result = recalculate_aggregation_from_tasks(agg, [])

        assert agg.total_tasks == 0
        assert agg.todo_tasks == 0
        assert agg.active_tasks == 0
        assert agg.review_tasks == 0
        assert agg.issue_tasks == 0
        assert agg.done_tasks == 0
        assert result == "Todo"

    def test_recalculate_with_task_status_objects(self):
        """Recalculates correctly using task_status relationship."""
        agg = self._create_mock_agg()
        tasks = [
            self._create_mock_task_with_status_obj("Todo"),
            self._create_mock_task_with_status_obj("Todo"),
            self._create_mock_task_with_status_obj("In Progress"),
            self._create_mock_task_with_status_obj("Done"),
        ]

        result = recalculate_aggregation_from_tasks(agg, tasks)

        assert agg.total_tasks == 4
        assert agg.todo_tasks == 2
        assert agg.active_tasks == 1
        assert agg.done_tasks == 1
        assert result == "In Progress"

    def test_recalculate_with_legacy_status_strings(self):
        """Recalculates correctly using legacy status strings."""
        agg = self._create_mock_agg()
        tasks = [
            self._create_mock_task_with_legacy_status("todo"),
            self._create_mock_task_with_legacy_status("in_progress"),
            self._create_mock_task_with_legacy_status("done"),
        ]

        result = recalculate_aggregation_from_tasks(agg, tasks)

        assert agg.total_tasks == 3
        assert agg.todo_tasks == 1
        assert agg.active_tasks == 1
        assert agg.done_tasks == 1
        assert result == "In Progress"

    def test_recalculate_maps_blocked_to_issue(self):
        """Recalculates blocked status as issue (migration support)."""
        agg = self._create_mock_agg()
        tasks = [
            self._create_mock_task_with_legacy_status("blocked"),
            self._create_mock_task_with_legacy_status("todo"),
        ]

        result = recalculate_aggregation_from_tasks(agg, tasks)

        assert agg.total_tasks == 2
        assert agg.issue_tasks == 1  # blocked mapped to issue
        assert agg.todo_tasks == 1
        assert result == "Issue"

    def test_recalculate_with_all_statuses(self):
        """Recalculates correctly with all status types."""
        agg = self._create_mock_agg()
        tasks = [
            self._create_mock_task_with_status_obj("Todo"),
            self._create_mock_task_with_status_obj("In Progress"),
            self._create_mock_task_with_status_obj("In Review"),
            self._create_mock_task_with_status_obj("Issue"),
            self._create_mock_task_with_status_obj("Done"),
        ]

        result = recalculate_aggregation_from_tasks(agg, tasks)

        assert agg.total_tasks == 5
        assert agg.todo_tasks == 1
        assert agg.active_tasks == 1
        assert agg.review_tasks == 1
        assert agg.issue_tasks == 1
        assert agg.done_tasks == 1
        assert result == "Issue"  # Issue takes priority

    def test_recalculate_updates_timestamp(self):
        """Recalculating updates the updated_at timestamp."""
        agg = self._create_mock_agg()
        tasks = []

        recalculate_aggregation_from_tasks(agg, tasks)

        assert agg.updated_at is not None


class TestStatusToCounterFieldMapping:
    """Tests for STATUS_TO_COUNTER_FIELD constant."""

    def test_mapping_contains_all_statuses(self):
        """All StatusName enum values are mapped."""
        for status_name in StatusName:
            assert status_name.value in STATUS_TO_COUNTER_FIELD

    def test_mapping_values_are_valid(self):
        """All mapping values are valid counter field names."""
        expected_fields = {
            "todo_tasks",
            "active_tasks",
            "review_tasks",
            "issue_tasks",
            "done_tasks",
        }
        assert set(STATUS_TO_COUNTER_FIELD.values()) == expected_fields


class TestDerivationRulesIntegration:
    """Integration tests verifying complete derivation rule priority."""

    def test_derivation_priority_order(self):
        """Verify derivation follows priority: Done > Issue > In Progress > Todo."""
        # Test 1: All done beats everything
        assert derive_project_status(ProjectAggregation(3, 0, 0, 0, 0, 3)) == "Done"

        # Test 2: Issue beats In Progress
        assert derive_project_status(ProjectAggregation(3, 0, 1, 0, 1, 1)) == "Issue"

        # Test 3: In Progress beats Todo
        assert derive_project_status(ProjectAggregation(3, 1, 1, 0, 0, 1)) == "In Progress"

        # Test 4: Review also triggers In Progress
        assert derive_project_status(ProjectAggregation(3, 1, 0, 1, 0, 1)) == "In Progress"

        # Test 5: Default is Todo
        assert derive_project_status(ProjectAggregation(3, 3, 0, 0, 0, 0)) == "Todo"

    def test_edge_case_single_task_each_status(self):
        """Test with single task in each possible status."""
        # Single Todo task
        assert derive_project_status(ProjectAggregation(1, 1, 0, 0, 0, 0)) == "Todo"

        # Single In Progress task
        assert derive_project_status(ProjectAggregation(1, 0, 1, 0, 0, 0)) == "In Progress"

        # Single In Review task
        assert derive_project_status(ProjectAggregation(1, 0, 0, 1, 0, 0)) == "In Progress"

        # Single Issue task
        assert derive_project_status(ProjectAggregation(1, 0, 0, 0, 1, 0)) == "Issue"

        # Single Done task
        assert derive_project_status(ProjectAggregation(1, 0, 0, 0, 0, 1)) == "Done"
