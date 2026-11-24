"""Who can hold the dossier override permission: its verb is outside the editing actions, so the built-in Editor and
Viewer roles and an Edit or View module access level never carry it."""

from src.modules.mdr.permissions import MdrPermissionName
from src.modules.platform.access import EDIT_ACTIONS, VIEW_ACTIONS
from src.modules.platform.roles import builtin_role_permissions

OVERRIDE = MdrPermissionName.OVERRIDE.value


def test_the_override_verb_is_outside_the_viewing_and_editing_actions():
    verb = OVERRIDE.split(".", 1)[1]
    assert verb not in VIEW_ACTIONS and verb not in EDIT_ACTIONS


def test_the_built_in_editor_and_viewer_roles_never_carry_the_override():
    roles = builtin_role_permissions()
    assert OVERRIDE not in roles["Editor"]
    assert OVERRIDE not in roles["Viewer"]
    assert OVERRIDE in roles["Admin"]  # Admin carries every registered permission
