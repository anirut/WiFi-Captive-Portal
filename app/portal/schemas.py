from pydantic import BaseModel, field_validator
from datetime import datetime

class RoomAuthRequest(BaseModel):
    room_number: str
    last_name: str
    tc_accepted: bool

    @field_validator("tc_accepted")
    @classmethod
    def must_accept_tc(cls, v):
        if not v:
            raise ValueError("Must accept terms and conditions")
        return v

class VoucherAuthRequest(BaseModel):
    code: str
    tc_accepted: bool

    @field_validator("tc_accepted")
    @classmethod
    def must_accept_tc(cls, v):
        if not v:
            raise ValueError("Must accept terms and conditions")
        return v

class SessionResponse(BaseModel):
    session_id: str
    expires_at: datetime
