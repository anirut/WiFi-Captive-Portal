"""
Pydantic schemas for FIAS Emulator API.
"""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# Guest schemas
class GuestBase(BaseModel):
    """Base schema for Guest."""

    room_number: str = Field(..., min_length=1, max_length=20)
    last_name: str = Field(..., min_length=1, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    reservation_number: str = Field(..., min_length=1, max_length=50)
    arrival_date: date
    departure_date: date
    is_active: bool = True
    scenario_id: Optional[int] = None


class GuestCreate(GuestBase):
    """Schema for creating a new Guest."""

    pass


class GuestUpdate(BaseModel):
    """Schema for updating a Guest. All fields are optional."""

    room_number: Optional[str] = Field(None, min_length=1, max_length=20)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    reservation_number: Optional[str] = Field(None, min_length=1, max_length=50)
    arrival_date: Optional[date] = None
    departure_date: Optional[date] = None
    is_active: Optional[bool] = None
    scenario_id: Optional[int] = None


class GuestResponse(GuestBase):
    """Schema for Guest response."""

    id: int

    model_config = ConfigDict(from_attributes=True)


# Scenario schemas
class ScenarioBase(BaseModel):
    """Base schema for Scenario."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    is_active: bool = False


class ScenarioCreate(ScenarioBase):
    """Schema for creating a new Scenario."""

    pass


class ScenarioResponse(ScenarioBase):
    """Schema for Scenario response."""

    id: int
    guest_count: int = 0
    failure_rule_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# FailureRule schemas
class FailureRuleBase(BaseModel):
    """Base schema for FailureRule."""

    scenario_id: Optional[int] = None
    trigger: str = Field(..., min_length=1, max_length=50)
    action: str = Field(..., min_length=1, max_length=50)
    probability: float = Field(1.0, ge=0.0, le=1.0)
    malformed_type: Optional[str] = Field(None, max_length=50)
    business_rule: Optional[str] = Field(None, max_length=50)


class FailureRuleCreate(FailureRuleBase):
    """Schema for creating a new FailureRule."""

    pass


class FailureRuleResponse(FailureRuleBase):
    """Schema for FailureRule response."""

    id: int

    model_config = ConfigDict(from_attributes=True)


# Connection schemas
class ConnectionResponse(BaseModel):
    """Schema for Connection response."""

    id: int
    client_host: str
    client_port: int
    connected_at: datetime
    vendor_id: Optional[str]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# ActivityLog schemas
class ActivityLogResponse(BaseModel):
    """Schema for ActivityLog response."""

    id: int
    connection_id: Optional[int]
    timestamp: datetime
    direction: str
    record_type: str
    raw_content: str

    model_config = ConfigDict(from_attributes=True)


# Reset response
class ResetResponse(BaseModel):
    """Schema for reset endpoint response."""

    message: str = "All data cleared and reset to defaults"
    guests_cleared: int
    connections_cleared: int
    activity_logs_cleared: int
