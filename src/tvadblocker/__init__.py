"""Switch OBS scenes by detecting a broadcast channel logo over NDI.

Only lightweight, dependency-free names are exported here so that importing
the package (e.g. for tests) does not pull in the native NDI/OBS bindings.
"""

from __future__ import annotations

__version__ = "0.2.0"

__all__ = ["__version__"]
