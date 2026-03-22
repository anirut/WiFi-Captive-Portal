"""
SQLAlchemy database models for FIAS Emulator.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class Guest(Base):
    """
    Guest record simulating PMS guest data.

    This represents the guest information that would normally be queried
    from the hotel PMS system.
    """

    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reservation_number: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    arrival_date: Mapped[date] = mapped_column(Date, nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scenario_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("scenarios.id"), nullable=True
    )

    # Relationship
    scenario: Mapped[Optional["Scenario"]] = relationship(
        "Scenario", back_populates="guests"
    )

    def __repr__(self) -> str:
        return (
            f"<Guest(id={self.id}, room={self.room_number}, "
            f"name={self.last_name}, reservation={self.reservation_number})>"
        )


class Scenario(Base):
    """
    Test scenario grouping guests and failure rules.

    Scenarios allow grouping guests with specific failure behaviors
    for testing different edge cases.
    """

    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    guests: Mapped[list["Guest"]] = relationship(
        "Guest", back_populates="scenario", lazy="selectin"
    )
    failure_rules: Mapped[list["FailureRule"]] = relationship(
        "FailureRule", back_populates="scenario", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Scenario(id={self.id}, name={self.name}, active={self.is_active})>"


class FailureRule(Base):
    """
    Failure injection rule for simulating PMS issues.

    Rules can be global (scenario_id=None) or scoped to a specific scenario.
    They define when and how to inject failures into FIAS responses.
    """

    __tablename__ = "failure_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("scenarios.id"), nullable=True, index=True
    )
    trigger: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "on_login", "on_query", "on_room:101"
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "drop_connection", "delay:5s", "malformed_xml"
    probability: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    malformed_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # "missing_field", "bad_encoding", "unknown_tag"
    business_rule: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # "checkout_mid_session", "room_reassign"

    # Relationship
    scenario: Mapped[Optional["Scenario"]] = relationship(
        "Scenario", back_populates="failure_rules"
    )

    def __repr__(self) -> str:
        return (
            f"<FailureRule(id={self.id}, trigger={self.trigger}, "
            f"action={self.action}, probability={self.probability})>"
        )


class Connection(Base):
    """
    Active TCP connection from a PMS client.

    Tracks connections for debugging and activity logging purposes.
    """

    __tablename__ = "connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_host: Mapped[str] = mapped_column(String(50), nullable=False)
    client_port: Mapped[int] = mapped_column(Integer, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    vendor_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationship
    activity_logs: Mapped[list["ActivityLog"]] = relationship(
        "ActivityLog", back_populates="connection", lazy="selectin"
    )

    def __repr__(self) -> str:
        return (
            f"<Connection(id={self.id}, client={self.client_host}:{self.client_port}, "
            f"active={self.is_active})>"
        )


class ActivityLog(Base):
    """
    Log of FIAS record traffic for debugging and analysis.

    Records all incoming and outgoing FIAS messages with timestamps.
    """

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("connections.id"), nullable=True, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # "in" or "out"
    record_type: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # "LR", "GIQ", "GI", etc.
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationship
    connection: Mapped[Optional["Connection"]] = relationship(
        "Connection", back_populates="activity_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<ActivityLog(id={self.id}, direction={self.direction}, "
            f"type={self.record_type}, timestamp={self.timestamp})>"
        )
