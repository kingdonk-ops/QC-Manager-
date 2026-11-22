"""Platform administration: module access per user, the built-in roles, and user preferences."""


async def on_startup() -> None:
    from ...infrastructure.logging import get_logger  # noqa: PLC0415
    from .roles import sync_builtin_roles  # noqa: PLC0415

    try:
        await sync_builtin_roles()
    except Exception:  # an unmigrated database must not stop the app from starting
        get_logger().exception("Could not sync the built-in roles; run the migrations")
