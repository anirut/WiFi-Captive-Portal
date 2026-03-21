import uuid
import enum
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Boolean, BigInteger, Text, ForeignKey, Enum, DateTime, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, INET, MACADDR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

class SessionStatus(enum.Enum):
    active = "active"
    expired = "expired"
    kicked = "kicked"

class VoucherType(enum.Enum):
    time = "time"
    data = "data"

class PMSAdapterType(enum.Enum):
    opera = "opera"              # legacy — keep for DB compat, unused by adapters
    opera_fias = "opera_fias"   # OPERA 5/Suite8 via FIAS TCP
    opera_cloud = "opera_cloud" # OPERA Cloud via OHIP REST
    cloudbeds = "cloudbeds"
    mews = "mews"
    custom = "custom"
    standalone = "standalone"

class AdminRole(enum.Enum):
    superadmin = "superadmin"
    staff = "staff"

class LanguageType(enum.Enum):
    th = "th"
    en = "en"


class DnsModeType(str, enum.Enum):
    redirect = "redirect"
    forward = "forward"

class Guest(Base):
    __tablename__ = "guests"
    id: Mapped[uuid.UUID] = uuid_pk()
    room_number: Mapped[str] = mapped_column(String(20))
    last_name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pms_guest_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    check_in: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_out: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_devices: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    sessions: Mapped[list["Session"]] = relationship(back_populates="guest")

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    guest_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("guests.id"), nullable=True)
    voucher_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vouchers.id"), nullable=True)
    ip_address: Mapped[str] = mapped_column(INET)
    mac_address: Mapped[str | None] = mapped_column(MACADDR, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bytes_up: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_down: Mapped[int] = mapped_column(BigInteger, default=0)
    bandwidth_up_kbps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), default=SessionStatus.active)
    guest: Mapped["Guest | None"] = relationship(back_populates="sessions")
    voucher: Mapped["Voucher | None"] = relationship(back_populates="sessions")

class Voucher(Base):
    __tablename__ = "vouchers"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(50), unique=True)
    type: Mapped[VoucherType] = mapped_column(Enum(VoucherType))
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_limit_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_devices: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_users.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    sessions: Mapped[list["Session"]] = relationship(back_populates="voucher")

class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[uuid.UUID] = uuid_pk()
    number: Mapped[str] = mapped_column(String(20), unique=True)
    room_type: Mapped[str] = mapped_column(String(50), default="standard")
    policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("policies.id"), nullable=True)
    pms_room_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(100))
    bandwidth_up_kbps: Mapped[int] = mapped_column(Integer, default=0)
    bandwidth_down_kbps: Mapped[int] = mapped_column(Integer, default=0)
    session_duration_min: Mapped[int] = mapped_column(Integer, default=0)
    max_devices: Mapped[int] = mapped_column(Integer, default=3)

class PMSAdapter(Base):
    __tablename__ = "pms_adapters"
    id: Mapped[uuid.UUID] = uuid_pk()
    type: Mapped[PMSAdapterType] = mapped_column(Enum(PMSAdapterType))
    config_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(200), nullable=True)

class AdminUser(Base):
    __tablename__ = "admin_users"
    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[AdminRole] = mapped_column(Enum(AdminRole), default=AdminRole.staff)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageSnapshot(Base):
    __tablename__ = "usage_snapshots"
    id: Mapped[uuid.UUID] = uuid_pk()
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_bytes_up: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    total_bytes_down: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    voucher_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class BrandConfig(Base):
    __tablename__ = "brand_config"
    id: Mapped[uuid.UUID] = uuid_pk()
    hotel_name: Mapped[str] = mapped_column(String(200), nullable=False, default="Hotel WiFi", server_default="'Hotel WiFi'")
    logo_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#3B82F6", server_default="'#3B82F6'")
    tc_text_th: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tc_text_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[LanguageType] = mapped_column(Enum(LanguageType, name="languagetype"), nullable=False, default=LanguageType.th)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), server_default="now()")


class DhcpConfig(Base):
    __tablename__ = "dhcp_config"
    id: Mapped[uuid.UUID] = uuid_pk()
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    interface: Mapped[str] = mapped_column(String(32), nullable=False, default="wlan0", server_default="'wlan0'")
    gateway_ip: Mapped[str] = mapped_column(String(15), nullable=False, default="192.168.0.1", server_default="'192.168.0.1'")
    subnet: Mapped[str] = mapped_column(String(18), nullable=False, default="192.168.0.0/22", server_default="'192.168.0.0/22'")
    dhcp_range_start: Mapped[str] = mapped_column(String(15), nullable=False, default="192.168.0.10", server_default="'192.168.0.10'")
    dhcp_range_end: Mapped[str] = mapped_column(String(15), nullable=False, default="192.168.3.250", server_default="'192.168.3.250'")
    lease_time: Mapped[str] = mapped_column(String(8), nullable=False, default="8h", server_default="'8h'")
    dns_upstream_1: Mapped[str] = mapped_column(String(45), nullable=False, default="8.8.8.8", server_default="'8.8.8.8'")
    dns_upstream_2: Mapped[str] = mapped_column(String(45), nullable=False, default="8.8.4.4", server_default="'8.8.4.4'")
    dns_mode: Mapped[DnsModeType] = mapped_column(
        Enum(DnsModeType, name="dnsmodetype"), nullable=False, default=DnsModeType.redirect
    )
    log_queries: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default="now()"
    )
