from __future__ import annotations

import os

from fastapi import Header, HTTPException, status


def verify_api_key(
    x_api_key: str | None = Header(default=None),
) -> None:
    expected_api_key = os.getenv("API_KEY")

    if not expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API security is not configured",
        )

    if x_api_key != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )