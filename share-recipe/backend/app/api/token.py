from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.auth import verify_refresh_token
from app.utils.security import create_access_token

router = APIRouter(prefix="/api/user/token", tags=["Token"])


class RefreshRequest(BaseModel):
    refresh: str


@router.post("/refresh/")
async def refresh_token(data: RefreshRequest):
    user_id = verify_refresh_token(data.refresh)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    new_access_token = create_access_token(user_id)
    return {"access": new_access_token}
