import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.recipe import RecipeResponse  # added import


class UserSignup(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=20, pattern=r"^[A-Za-z0-9._]+$")
    password: str = Field(..., min_length=8)
    password2: str = Field(..., min_length=8)

    @model_validator(mode="after")
    def check_password_strength(self):
        pw = self.password
        # at least one uppercase, one digit, one special character
        if not (
            re.search(r"[A-Z]", pw)
            and re.search(r"[0-9]", pw)
            and re.search(r"[^A-Za-z0-9]", pw)
        ):
            raise ValueError(
                "Password must contain at least one uppercase letter, one digit, and one special character."
            )
        if self.password != self.password2:
            raise ValueError("Passwords do not match")
        return self


class UserSignIn(BaseModel):
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, min_length=2, max_length=20)
    last_name: Optional[str] = Field(default=None, min_length=2, max_length=20)
    username: Optional[str] = Field(
        default=None, min_length=3, max_length=20, pattern=r"^[A-Za-z0-9._]+$"
    )
    photo_url: Optional[str] = None
    bio: Optional[str] = Field(default=None, max_length=300)

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: Optional[str]):
        if v is None or v == "":
            return v
        if not re.fullmatch(r"[A-Za-zА-Яа-яЁё\-\s]{2,20}", v):
            raise ValueError(
                "Name must be 2-20 letters and may include spaces or hyphens."
            )
        if not v[0].isupper():
            raise ValueError("Name must start with a capital letter.")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: Optional[str]):
        if v is None or v == "":
            return v
        if not re.fullmatch(r"^[A-Za-z0-9._]{3,20}$", v):
            raise ValueError(
                "Username must be 3-20 chars: letters, digits, dots, underscores."
            )
        return v


class UserProfile(BaseModel):
    username: str
    first_name: str | None = None
    last_name: str | None = None
    joined: datetime | None = None
    is_active: bool | None = None
    photo_url: str | None = None
    bio: str | None = None

    class Config:
        from_attributes = True


class UserPublicProfile(BaseModel):
    username: str
    first_name: str | None = None
    last_name: str | None = None
    joined: datetime | None = None
    photo_url: str | None = None
    bio: str | None = None
    recipes: list[RecipeResponse] = []
    saved_recipes: list[RecipeResponse] = []

    class Config:
        from_attributes = True
