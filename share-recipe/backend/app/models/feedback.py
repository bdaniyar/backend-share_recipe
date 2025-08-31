# filepath: backend/app/models/feedback.py
from pydantic import BaseModel, EmailStr
from datetime import datetime


class FeedbackCreate(BaseModel):
    email: EmailStr
    message: str


class FeedbackResponse(BaseModel):
    id: int
    email: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True
