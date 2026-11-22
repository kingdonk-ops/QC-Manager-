"""Business modules: self-contained packages under ``src/modules`` that carry a ``manifest.py``.

See ``docs/modules.md`` at the repository root for how to write one.
"""

from .events import publish, subscribe
from .manifest import ModuleManifest

__all__ = ["ModuleManifest", "publish", "subscribe"]
