"""Shared slowapi Limiter instance.

Split out from main.py so customer360/api/tenancy_routes.py can reuse the
exact same limiter/rate-limit conventions without importing main.py
itself (which would create a circular import, since main.py mounts
tenancy_routes.router).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
)
