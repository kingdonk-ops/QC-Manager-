"""Ordering, validating and switching off business modules."""

import pytest

from src.infrastructure.modules import events
from src.infrastructure.modules.loader import ModuleLoadError, _order
from src.infrastructure.modules.manifest import ModuleManifest


def _found(*manifests: ModuleManifest) -> dict:
    return {m.name: (m, f"pkg.{m.name}") for m in manifests}


def test_dependencies_load_first():
    found = _found(
        ModuleManifest(name="cvr", version="1", display_name="C", depends=("projects",)),
        ModuleManifest(name="projects", version="1", display_name="P", depends=("team",)),
        ModuleManifest(name="team", version="1", display_name="T"),
    )

    assert [m.manifest.name for m in _order(found, set())] == ["team", "projects", "cvr"]


def test_disabling_a_module_disables_what_depends_on_it():
    found = _found(
        ModuleManifest(name="a", version="1", display_name="A"),
        ModuleManifest(name="b", version="1", display_name="B", depends=("a",)),
        ModuleManifest(name="c", version="1", display_name="C", optional_depends=("a",)),
    )

    enabled = {m.manifest.name: m.enabled for m in _order(found, {"a"})}

    assert enabled == {"a": False, "b": False, "c": True}


def test_a_missing_dependency_stops_the_app():
    with pytest.raises(ModuleLoadError, match="not installed"):
        _order(_found(ModuleManifest(name="b", version="1", display_name="B", depends=("a",))), set())


def test_a_cycle_stops_the_app():
    found = _found(
        ModuleManifest(name="a", version="1", display_name="A", depends=("b",)),
        ModuleManifest(name="b", version="1", display_name="B", depends=("a",)),
    )

    with pytest.raises(ModuleLoadError, match="cycle"):
        _order(found, set())


def test_names_are_snake_case():
    with pytest.raises(ValueError):
        ModuleManifest(name="My-Module", version="1", display_name="M")


def test_prefix_defaults_to_the_hyphenated_name():
    assert ModuleManifest(name="cost_codes", version="1", display_name="C").prefix == "/cost-codes"


async def test_events_reach_matching_subscribers_and_survive_a_failing_one():
    events.clear()
    seen: list[str] = []

    @events.subscribe("projects.*")
    async def broken(event, payload):
        raise RuntimeError("boom")

    @events.subscribe("projects.project.created")
    async def record(event, payload):
        seen.append(f"{event}:{payload['project_id']}")

    await events.publish("projects.project.created", {"project_id": 7})
    await events.publish("cvr.cost_head.created", {"project_id": 7})
    events.clear()

    assert seen == ["projects.project.created:7"]
