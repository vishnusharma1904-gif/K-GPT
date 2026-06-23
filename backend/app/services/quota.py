"""Deprecated — superseded by `entitlements` (Epic B).

Kept as a thin shim so any stray import doesn't break. Use
`app.services.entitlements` for all quota logic.
"""
from app.services.entitlements import (  # noqa: F401
    check_access as ensure_access,
    record_usage as record,
    usage_view,
)
