"""Tests for the list_capabilities utility tool."""

from __future__ import annotations

import pytest

from app.ai.agent.tools.utility_tools import list_capabilities


@pytest.mark.asyncio
async def test_list_capabilities_returns_content() -> None:
    """list_capabilities returns a non-empty string with key sections."""
    result = await list_capabilities.ainvoke({})
    assert isinstance(result, str)
    assert len(result) > 100
    assert "## Blair AI Copilot" in result
    assert "Capabilities" in result


@pytest.mark.asyncio
async def test_list_capabilities_mentions_all_categories() -> None:
    """list_capabilities output covers every major feature category."""
    result = await list_capabilities.ainvoke({})
    expected_categories = [
        "Applications",
        "Projects",
        "Tasks",
        "Knowledge Base",
        "Web Research",
        "Data & Analytics",
        "Search & Discovery",
    ]
    for category in expected_categories:
        assert category in result, f"Missing category: {category}"
