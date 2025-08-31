# filepath: backend/app/db/feedback.py
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.db.base import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
