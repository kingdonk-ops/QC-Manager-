"""Starting and stopping the business modules with the app."""

from ..composition import Lifecycle
from .loader import start_modules, stop_modules

lifecycle = Lifecycle("modules", startup=start_modules, shutdown=(stop_modules,))
