from __future__ import annotations

from ms.services.base import BaseService

from .runtime import BuildRuntimeMixin


class BuildService(BaseService, BuildRuntimeMixin):
    """Build service for native and WASM targets."""
