from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config.config import settings
from app.db.dao.dao import UserDAO

oauth2_scheme = HTTPBearer()
# Optional bearer that does not raise when header is missing
oauth2_scheme_optional = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format"
        )

    expire = payload.get("exp")
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())
    if (not expire) or (int(expire) < now_ts):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )

    try:
        user_id = int(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format"
        )

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    user = await UserDAO.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        oauth2_scheme_optional
    ),
):
    if not credentials:
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        sub = payload.get("sub")
        if sub is None:
            return None
        try:
            user_id = int(sub)
        except (TypeError, ValueError):
            return None
        user = await UserDAO.get_by_id(user_id)
        return user
    except JWTError:
        return None


def verify_refresh_token(refresh_token: str) -> int | None:
    try:
        payload = jwt.decode(
            refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is not None:
            try:
                return int(user_id)
            except (TypeError, ValueError):
                return None
        return None
    except JWTError:
        return None


async def get_email_verified(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        oauth2_scheme_optional
    ),
):
    if not credentials:
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        if payload.get("type") != "email":
            return None
        return payload.get("sub")  # email
    except JWTError:
        return None
