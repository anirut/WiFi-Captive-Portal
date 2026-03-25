from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class RoomAuthRequest(BaseModel):
    room_number: str = Field(..., min_length=1, max_length=20)
    last_name: str = Field(..., min_length=1, max_length=100)
    tc_accepted: bool

    @field_validator("tc_accepted")
    @classmethod
    def must_accept_tc(cls, v):
        if not v:
            raise ValueError("Must accept terms and conditions")
        return v

    @field_validator("room_number", "last_name")
    @classmethod
    def strip_whitespace(cls, v):
        return v.strip()


class VoucherAuthRequest(BaseModel):
    code: str = Field(..., pattern=r"^[A-Z0-9]{4,12}$")
    tc_accepted: bool

    @field_validator("tc_accepted")
    @classmethod
    def must_accept_tc(cls, v):
        if not v:
            raise ValueError("Must accept terms and conditions")
        return v

    @field_validator("code")
    @classmethod
    def uppercase_code(cls, v):
        return v.upper()


class SessionResponse(BaseModel):
    session_id: str
    expires_at: datetime
