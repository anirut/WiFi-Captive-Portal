# WiFi Captive Portal — รายละเอียดโปรแกรมและฟีเจอร์

> เวอร์ชัน: Phase 2 (PMS Integration)
> อัปเดต: 2026-03-21

---

## 1. ภาพรวมระบบ

WiFi Captive Portal คือระบบควบคุมการเข้าถึงอินเทอร์เน็ตสำหรับโรงแรม โดยแขกจะต้องยืนยันตัวตนก่อนจึงจะใช้งาน WiFi ได้ รองรับการเชื่อมต่อกับระบบ PMS (Property Management System) หลายประเภท เพื่อให้แขกล็อกอินด้วยหมายเลขห้องและนามสกุลที่ลงทะเบียนในระบบโรงแรมได้โดยตรง

### สถาปัตยกรรม

```
┌─────────────────────────────────────────────────────────────────┐
│                        Hotel Network                            │
│                                                                 │
│  Guest Device ──► WiFi AP ──► [iptables/tc Gateway] ──► Internet│
│                                     │                           │
│                                     ▼                           │
│                           WiFi Captive Portal                   │
│                           (FastAPI + PostgreSQL + Redis)        │
│                                     │                           │
│                                     ▼                           │
│                              PMS System                         │
│                    (Opera / Cloudbeds / Mews / Custom)          │
└─────────────────────────────────────────────────────────────────┘
```

### เทคโนโลยีที่ใช้

| ส่วนประกอบ | เทคโนโลยี |
|-----------|-----------|
| Web Framework | FastAPI (Python 3.12) |
| Database | PostgreSQL 14+ (asyncpg) |
| Cache / Rate Limit | Redis |
| ORM | SQLAlchemy 2.0 (Async) |
| Migration | Alembic |
| Network Control | iptables + tc (iproute2) |
| Scheduler | APScheduler 3.x |
| Frontend | Jinja2 + CSS (Glassmorphism) |
| Encryption | Fernet (cryptography library) |
| Auth | JWT (python-jose) |

---

## 2. ฟีเจอร์หลัก

### 2.1 การยืนยันตัวตนแขก (Guest Authentication)

#### ยืนยันด้วยหมายเลขห้อง (Room Authentication)
- แขกกรอก **หมายเลขห้อง** + **นามสกุล**
- ระบบตรวจสอบกับ PMS ว่าแขกเช็คอินอยู่จริง
- Session มีอายุถึงวันเช็คเอาท์หรือตาม Policy ที่ตั้งไว้
- รองรับ T&C Acceptance (ต้องยอมรับเงื่อนไขก่อนใช้งาน)

#### ยืนยันด้วย Voucher Code
- แขกกรอก **รหัส Voucher** 8 หลัก (เช่น `K9ZXYB7Q`)
- รองรับ 2 ประเภท:
  - **Time-based** — กำหนดระยะเวลา (นาที)
  - **Data-based** — กำหนดปริมาณข้อมูล (MB)
- ควบคุมจำนวนครั้งที่ใช้ได้ (`max_uses`)
- กำหนดวันหมดอายุได้

#### Rate Limiting
- จำกัดการพยายาม Login **5 ครั้ง / 10 นาที** ต่อ IP address
- ป้องกัน brute-force attack
- ใช้ Redis เก็บ counter

---

### 2.2 การจัดการ Session

#### การสร้าง Session
- บันทึก IP address และ MAC address ของอุปกรณ์
- ตั้งเวลาหมดอายุตาม check-out หรือ policy
- เพิ่มกฎ iptables เพื่อให้ traffic ผ่านได้
- ใส่ bandwidth limit ผ่าน tc (Linux Traffic Control)

#### การหมดอายุ Session
| วิธี | รายละเอียด |
|------|-----------|
| **Auto Expire** | Scheduler ตรวจทุก 60 วินาที |
| **Checkout Sync** | PMS แจ้งเช็คเอาท์ → ตัด session ทันที |
| **Webhook** | Opera Cloud / Mews push event |
| **Polling** | Cloudbeds / Custom / FIAS poll ทุก 5 นาที |
| **Manual Kick** | Admin ตัด session ผ่านหน้า admin |
| **Self Disconnect** | แขกกด Disconnect เอง |

#### Bandwidth Shaping (QoS)
- กำหนด **Download** limit ต่อ IP ได้ (kbps)
- ใช้ HTB (Hierarchical Token Bucket) ผ่าน `tc`
- Class ID คำนวณจาก 2 octet สุดท้ายของ IP
- Traffic ที่ไม่มี limit จะไหลผ่านที่ 1000 Mbps (unlimited)

---

### 2.3 PMS Adapters (การเชื่อมต่อระบบโรงแรม)

รองรับ PMS ดังนี้:

#### Opera Cloud (OHIP REST API)
- **Protocol:** HTTPS REST
- **Auth:** OAuth2 Client Credentials (token cache ใน memory)
- **Token Refresh:** อัตโนมัติเมื่อ token ใกล้หมดอายุ (< 60 วินาที)
- **Checkout Sync:** Webhook (push events)
- **Config:** `api_url`, `client_id`, `client_secret`, `hotel_id`

#### Opera FIAS (Opera 5 / Suite8)
- **Protocol:** TCP Socket ถาวร (FIAS XML)
- **Auth:** AuthKey + VendorID ผ่าน Login Record
- **Connection:** Persistent connection พร้อม Heartbeat ทุก 30 วินาที
- **Serialization:** asyncio.Lock ป้องกันการส่งพร้อมกัน
- **Checkout Sync:** Polling ทุก 5 นาที
- **Config:** `host`, `port`, `auth_key`, `vendor_id`

#### Cloudbeds
- **Protocol:** HTTPS REST (Cloudbeds API v1.1)
- **Auth:** API Key ใน Authorization header
- **Checkout Sync:** Polling ทุก 5 นาที
- **Config:** `api_url`, `api_key`, `property_id`

#### Mews
- **Protocol:** HTTPS REST (Mews Connector API)
- **Auth:** ClientToken + AccessToken ใน request body ทุกครั้ง
- **Checkout Sync:** Webhook (push events)
- **Config:** `api_url`, `client_token`, `access_token`

#### Custom (Any REST PMS)
- **Protocol:** HTTPS REST (กำหนดเอง)
- **Auth:** Bearer token หรือ HTTP Basic Auth
- **Field Mapping:** dot-notation JSON path (เช่น `data.guest.surname`)
- **Config:** กำหนด endpoint ทุกตัวได้เอง พร้อม `field_map`
- **ตัวอย่าง field_map:**
  ```json
  {
    "pms_id":      "reservation.id",
    "room_number": "reservation.room",
    "last_name":   "guest.surname",
    "first_name":  "guest.given_name",
    "check_in":    "reservation.arrival",
    "check_out":   "reservation.departure"
  }
  ```

#### Standalone (ไม่มี PMS)
- บันทึกข้อมูลแขกใน local database โดยตรง
- ใช้ได้กับโรงแรมที่ไม่มีระบบ PMS
- Admin เพิ่ม Guest record เองผ่าน DB

---

### 2.4 Webhook Checkout Sync

**Endpoint:** `POST /internal/pms/webhook/{adapter_id}`

- รับ checkout event จาก PMS โดยตรง (real-time)
- ตรวจสอบ signature ด้วย **HMAC-SHA256** (timing-safe comparison)
- รองรับ Opera Cloud และ Mews
- เมื่อรับ checkout event → ตัด session ทุก session ของห้องนั้นทันที

**ตัวอย่าง payload Opera Cloud:**
```json
{
  "eventType": "CHECKED_OUT",
  "roomNumber": "101"
}
```

**ตัวอย่าง payload Mews:**
```json
{
  "Type": "ReservationUpdated",
  "State": "Checked_out",
  "RoomNumber": "202"
}
```

---

### 2.5 Admin Panel

#### จัดการ Session
| Feature | รายละเอียด |
|---------|-----------|
| ดู Active Sessions | แสดง IP, เวลาเชื่อมต่อ, เวลาหมดอายุ |
| Kick Session | ตัด session ทันที + ลบ iptables/tc rules |

#### จัดการ PMS
| Feature | รายละเอียด |
|---------|-----------|
| ดู Config | แสดง config ปัจจุบัน (ซ่อน credentials ด้วย `***`) |
| อัปเดต Config | บันทึก + เข้ารหัส + reload adapter ทันที |
| ทดสอบ Config | ทดสอบการเชื่อมต่อ + วัด latency |

---

### 2.6 ความปลอดภัย (Security)

#### การเข้ารหัส
- **PMS Credentials:** เข้ารหัสด้วย Fernet (AES-128-CBC + HMAC-SHA256)
- **Admin Passwords:** bcrypt hash
- **JWT:** HMAC-SHA256 signing

#### Network Security
- **Webhook Signature:** HMAC-SHA256 + `hmac.compare_digest` (timing-safe)
- **Rate Limiting:** Redis-backed counter ต่อ IP
- **iptables DROP:** default drop สำหรับ unauthenticated traffic
- **DNS Allow:** อนุญาต port 53 เพื่อ captive portal detection

#### Config Security
- `.env` file permission: `600` (อ่านได้เฉพาะ owner)
- Database credentials: เก็บแยกจาก code
- Fernet key: generate ใหม่ทุก install

---

## 3. โครงสร้าง Database

### ตาราง guests
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key |
| `room_number` | String(20) | หมายเลขห้อง |
| `last_name` | String(100) | นามสกุล |
| `first_name` | String(100) | ชื่อ (optional) |
| `pms_guest_id` | String(100) | ID จาก PMS (optional) |
| `check_in` | DateTime(tz) | วันเช็คอิน |
| `check_out` | DateTime(tz) | วันเช็คเอาท์ |
| `max_devices` | Integer | จำนวนอุปกรณ์สูงสุด (default: 3) |
| `created_at` | DateTime(tz) | วันที่บันทึก |

### ตาราง sessions
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key |
| `guest_id` | UUID FK | เชื่อมกับ guests (optional) |
| `voucher_id` | UUID FK | เชื่อมกับ vouchers (optional) |
| `ip_address` | INET | IP address ของอุปกรณ์ |
| `mac_address` | MACADDR | MAC address (optional) |
| `connected_at` | DateTime(tz) | เวลาเชื่อมต่อ |
| `expires_at` | DateTime(tz) | เวลาหมดอายุ |
| `bytes_up` | BigInteger | Upload (bytes) |
| `bytes_down` | BigInteger | Download (bytes) |
| `status` | Enum | `active` / `expired` / `kicked` |

### ตาราง vouchers
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key |
| `code` | String(50) | รหัส voucher (unique) |
| `type` | Enum | `time` / `data` |
| `duration_minutes` | Integer | ระยะเวลา (สำหรับ type=time) |
| `data_limit_mb` | Integer | ปริมาณข้อมูล (สำหรับ type=data) |
| `max_devices` | Integer | จำนวนอุปกรณ์ (default: 1) |
| `created_by` | UUID FK | Admin ที่สร้าง |
| `expires_at` | DateTime(tz) | วันหมดอายุ voucher |
| `used_count` | Integer | ใช้ไปแล้วกี่ครั้ง |
| `max_uses` | Integer | ใช้ได้กี่ครั้งสูงสุด |

### ตาราง rooms
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key |
| `number` | String(20) | หมายเลขห้อง (unique) |
| `room_type` | String(50) | ประเภทห้อง (default: standard) |
| `policy_id` | UUID FK | Policy ที่ใช้ (optional) |
| `pms_room_id` | String(100) | Room ID จาก PMS (optional) |

### ตาราง policies
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key |
| `name` | String(100) | ชื่อ policy |
| `bandwidth_up_kbps` | Integer | Upload limit (0 = ไม่จำกัด) |
| `bandwidth_down_kbps` | Integer | Download limit (0 = ไม่จำกัด) |
| `session_duration_min` | Integer | ระยะเวลา session (0 = ถึงเช็คเอาท์) |
| `max_devices` | Integer | จำนวนอุปกรณ์สูงสุด (default: 3) |

### ตาราง pms_adapters
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key |
| `type` | Enum | ประเภท PMS |
| `config_encrypted` | LargeBinary | Config ที่เข้ารหัสด้วย Fernet |
| `is_active` | Boolean | เปิดใช้งานหรือไม่ |
| `last_sync_at` | DateTime(tz) | เวลา sync ล่าสุด |
| `webhook_secret` | String(200) | SHA-256 hash ของ webhook secret |

### ตาราง admin_users
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key |
| `username` | String(100) | ชื่อผู้ใช้ (unique) |
| `password_hash` | String(200) | bcrypt hash |
| `role` | Enum | `superadmin` / `staff` |
| `last_login_at` | DateTime(tz) | เวลา login ล่าสุด |

---

## 4. API Endpoints ทั้งหมด

### Guest Portal

| Method | Path | Auth | รายละเอียด |
|--------|------|------|-----------|
| `GET` | `/` | — | หน้า login portal |
| `POST` | `/auth/room` | — | ล็อกอินด้วยหมายเลขห้อง + นามสกุล |
| `POST` | `/auth/voucher` | — | ล็อกอินด้วย voucher code |
| `GET` | `/success` | — | หน้า success หลัง login |
| `GET` | `/expired` | — | หน้า session expired |
| `POST` | `/session/disconnect` | — | ตัดการเชื่อมต่อด้วยตนเอง |

### Admin

| Method | Path | Auth | รายละเอียด |
|--------|------|------|-----------|
| `GET` | `/admin/sessions` | — | ดูรายการ session ที่ active |
| `DELETE` | `/admin/sessions/{id}` | — | Kick session |
| `GET` | `/admin/pms` | — | ดู PMS config (masked) |
| `PUT` | `/admin/pms` | — | อัปเดต PMS config |
| `POST` | `/admin/pms/test` | — | ทดสอบการเชื่อมต่อ PMS |

### Internal

| Method | Path | Auth | รายละเอียด |
|--------|------|------|-----------|
| `POST` | `/internal/pms/webhook/{id}` | HMAC-SHA256 | รับ checkout event จาก PMS |

---

## 5. Network Flow

```
Guest เปิด Browser
       │
       ▼
iptables PREROUTING (NAT)
  → HTTP port 80 ถูก DNAT ไปที่ Portal IP:PORT
       │
       ▼
Portal แสดงหน้า Login
       │
       ▼ (หลังล็อกอินสำเร็จ)
iptables FORWARD
  → เพิ่ม rule: -I FORWARD -s {guest_ip} -j ACCEPT
       │
       ▼
tc HTB Class
  → สร้าง class 1:{id} rate {bandwidth}kbit
  → สร้าง u32 filter match dst {guest_ip}/32
       │
       ▼
Guest ใช้อินเทอร์เน็ตได้ (ผ่าน FORWARD chain)
       │
       ▼ (เมื่อหมดอายุหรือ checkout)
iptables -D FORWARD -s {guest_ip} -j ACCEPT
tc class del + filter del
Session.status = expired
```

---

## 6. Scheduler Jobs

| Job | ความถี่ | รายละเอียด |
|-----|---------|-----------|
| `_expire_job` | ทุก 60 วินาที | ตรวจ session ที่หมดอายุ → ลบ rules + update status |
| `_poll_checkouts_job` | ทุก 300 วินาที | Sync checkout จาก PMS (Cloudbeds, FIAS, Custom) |

**Adapter ที่ skip การ poll:**
- OperaCloudAdapter → ใช้ Webhook
- MewsAdapter → ใช้ Webhook
- StandaloneAdapter → ไม่มี external PMS

**Error handling:**
- ถ้า poll ล้มเหลว → ไม่อัปเดต `last_sync_at` → poll รอบหน้าจะครอบคลุม window เดิม

---

## 7. Environment Variables

| ตัวแปร | จำเป็น | Default | รายละเอียด |
|--------|--------|---------|-----------|
| `SECRET_KEY` | ✅ | — | JWT signing key (≥32 chars) |
| `ENCRYPTION_KEY` | ✅ | — | Fernet key (generated) |
| `DATABASE_URL` | ✅ | — | `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | ✅ | — | `redis://host:port/db` |
| `ENVIRONMENT` | — | `development` | `production` ปิด SQL echo |
| `WIFI_INTERFACE` | — | `wlan0` | Interface ฝั่ง WiFi AP |
| `WAN_INTERFACE` | — | `eth0` | Interface ฝั่ง Internet |
| `PORTAL_IP` | — | `192.168.1.1` | IP ของ Portal (gateway) |
| `PORTAL_PORT` | — | `8080` | Port ของ Portal |
| `JWT_EXPIRE_HOURS` | — | `8` | อายุ Admin JWT (ชั่วโมง) |
| `AUTH_RATE_LIMIT_ATTEMPTS` | — | `5` | จำนวนครั้งก่อน rate limit |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | — | `600` | Window สำหรับ rate limit (วินาที) |

---

## 8. ข้อจำกัดปัจจุบัน

| รายการ | สถานะ |
|--------|-------|
| Upload bandwidth shaping | ⚠️ ยังไม่ implement (parameter รับแต่ไม่ทำงาน) |
| Admin JWT authentication | ⚠️ โครงสร้างพร้อม แต่ middleware ยังไม่ enforce |
| Data-based voucher enforcement | ⚠️ บันทึก bytes แต่ยังไม่ตัด session เมื่อเกิน |
| Multi-server deployment | ⚠️ Design สำหรับ single-server hotel |
| IPv6 support | ⚠️ iptables rules ใช้ IPv4 เท่านั้น |
