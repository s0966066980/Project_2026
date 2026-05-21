from fastapi import HTTPException, Request

import config


def require_admin_token(request: Request):
    if not config.is_demo_public_mode():
        return
    expected = config.ADMIN_DEMO_TOKEN
    token = request.headers.get("X-Admin-Token") or request.query_params.get("token")
    if not expected or token != expected:
        raise HTTPException(status_code=403, detail="admin token required")
