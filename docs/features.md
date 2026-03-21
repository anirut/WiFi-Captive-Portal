# WiFi Captive Portal — รายละเอียดโปรแกรมและฟีเจอร์

> เวอร์ชัน: Phase 3 (Admin Dashboard + DHCP/DNS)
> อัปเดต: 2026-03-21

---

## 1. ภาพรวมระบบ

WiFi Captive Portal คือระบบควบคุมการเข้าถึงอินเทอร์เน็ตสำหรับโรงแรม โดยแขกจะต้องยืนยันตัวตนก่อนจึงจะใช้งาน WiFi ได้ รองรับการเชื่อมต่อกับระบบ PMS (Property Management System) หลายประเภท พร้อม Admin Dashboard แบบเต็มรูปแบบและระบบ DHCP/DNS ในตัว

### สถาปัตยกรรม

```
┌─────────────────────────────────────────────────────────────────┐
│                        Hotel Network                            │
│                                                                 │
│  Guest Device ──► WiFi AP ──► [nftables/tc Gateway] ──► Internet│
│                      │              │                           │
│                      │              ▼                           │
│                      │    ┌────────────────────┐                │
│                      └───►│ dnsmasq (DHCP+DNS) │                │
│                           └────────────────────┘                │
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
| Cache / Rate Limit / Token Blocklist | Redis |
| ORM | SQLAlchemy 2.0 (Async) |
| Migration | Alembic |
| Network Control | nftables + flowtables + tc (iproute2) |
| DHCP + DNS | dnsmasq |
| Scheduler | APScheduler 3.x |
| Frontend | Jinja2 + HTMX + Alpine.js + Tailwind CSS |
| Charts | Chart.js |
| PDF Generation | reportlab + qrcode |
| Encryption | Fernet (cryptography library) |
| Auth | JWT (python-jose) + bcrypt |

---

## 2. ฟีเจอร์หลัก

### 2.1 การยืนยันตัวตนแขก (Guest Authentication)

#### ยืนยันด้วยหมายเลขห้อง (Room Authentication)
- แขกกรอก **หมายเลขห้อง** + **นามสกุล**
- ระบบตรวจสอบกับ PMS ว่าแขกเช็คอินอยู่จริง
- Session มีอายุถึงวันเช็คเอาท์หรือตาม Policy ที่ตั้งไว้
- รองรับ T&C Acceptance (ต้องยอมรับเงื่อนไขก่อนใช้งาน)
- จำกัดจำนวนอุปกรณ์ต่อแขก (max_devices)

#### ยืนยันด้วย Voucher Code
- แขกกรอก **รหัส Voucher** 8 หลัก (เช่น `K9ZXYB7Q`)
- รองรับ 2 ประเภท:
  - **Time-based** — กำหนดระยะเวลา (นาที)
  - **Data-based** — กำหนดปริมาณข้อมูล (MB) — ระบบจะตัด session อัตโนมัติเมื่อใช้ครบโควต้า
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
- ใส่ bandwidth limit ผ่าน tc (Linux Traffic Control) — ทั้ง **Download** และ **Upload**
- เพิ่ม DNS bypass rule สำหรับ authenticated guests (redirect mode)

#### การหมดอายุ Session
| วิธี | รายละเอียด |
|------|-----------|
| **Auto Expire** | Scheduler ตรวจทุก 60 วินาที |
| **Checkout Sync** | PMS แจ้งเช็คเอาท์ → ตัด session ทันที |
| **Webhook** | Opera Cloud / Mews push event |
| **Polling** | Cloudbeds / Custom / FIAS poll ทุก 5 นาที |
| **Manual Kick** | Admin ตัด session ผ่านหน้า admin |
| **Self Disconnect** | แขกกด Disconnect เอง |
| **Data Quota Exceeded** | Voucher แบบ data-based ใช้ครบโควต้า |

#### Bandwidth Shaping (QoS)
- กำหนด **Download** และ **Upload** limit ต่อ IP ได้ (kbps)
- ใช้ HTB (Hierarchical Token Bucket) ผ่าน `tc`
- Download: ควบคุมบน WAN interface
- Upload: ควบคุมบน IFB (Intermediate Functional Block) device
- Class ID คำนวณจาก 2 octet สุดท้ายของ IP

#### Bytes Tracking
- ติดตาม bytes_up และ bytes_down ทุก 60 วินาที
- ใช้สำหรับ data-based voucher enforcement
- บันทึกลง database สำหรับ analytics

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

#### Standalone (ไม่มี PMS)
- บันทึกข้อมูลแขกใน local database โดยตรง
- ใช้ได้กับโรงแรมที่ไม่มีระบบ PMS

---

### 2.4 Webhook Checkout Sync

**Endpoint:** `POST /internal/pms/webhook/{adapter_id}`

- รับ checkout event จาก PMS โดยตรง (real-time)
- ตรวจสอบ signature ด้วย **HMAC-SHA256** (timing-safe comparison)
- รองรับ Opera Cloud และ Mews
- เมื่อรับ checkout event → ตัด session ทุก session ของห้องนั้นทันที

---

### 2.5 DHCP + DNS (dnsmasq)

ระบบมี dnsmasq ในตัวสำหรับให้บริการ DHCP และ DNS:

#### DHCP Features
- กำหนด IP range สำหรับแขกได้
- ตั้งค่า lease time (30m, 1h, 4h, 8h, 12h, 24h)
- Gateway และ DNS server แนบไปกับ DHCP response
- ดูรายการ lease ปัจจุบันได้ใน Admin UI

#### DNS Modes
| Mode | พฤติกรรม | ข้อดี |
|------|----------|-------|
| **redirect** | ตอบ DNS ทุก domain ด้วย portal IP; authenticated guests ได้รับ DNS bypass | Captive portal detection ทำงานได้ดีที่สุด |
| **forward** | ส่ง DNS query ต่อไปยัง upstream DNS | ง่ายกว่า ใช้ได้กับอุปกรณ์ส่วนใหญ่ |

#### DNS Bypass (redirect mode)
- Authenticated guests ได้รับ nftables DNAT rule ส่ง DNS ไปยัง 8.8.8.8 โดยตรง
- ข้าม dnsmasq catch-all redirect
- ทำให้ใช้อินเทอร์เน็ตได้ปกติหลัง login

---

### 2.6 Admin Dashboard

Admin Dashboard แบบเต็มรูปแบบพร้อม UI สวยงาม (Glassmorphism design):

#### Authentication
- Login ด้วย username/password
- JWT token เก็บใน httpOnly cookie
- Redis-based token blocklist (jti) สำหรับ logout
- รองรับ 2 roles: **superadmin** และ **staff**

#### Dashboard Modules

| Module | รายละเอียด | Role |
|--------|-----------|------|
| **Dashboard** | สถิติภาพรวม, active sessions, recent activity | staff + superadmin |
| **Sessions** | รายการ session ที่ active, kick session, HTMX polling | staff + superadmin |
| **Vouchers** | สร้าง/ลบ voucher, batch generate, PDF export พร้อม QR | staff + superadmin |
| **Rooms & Policies** | จัดการ policies, assign policy ให้ห้อง | superadmin only |
| **Analytics** | Charts: sessions, bandwidth, peak hours, auth breakdown | superadmin only |
| **PMS Settings** | ตั้งค่า PMS adapter, test connection | superadmin only |
| **Brand & Config** | Logo, ชื่อโรงแรม, สี, Terms & Conditions, ภาษา | superadmin only |
| **Admin Users** | สร้าง/จัดการ staff accounts | superadmin only |
| **DHCP** | ตั้งค่า DHCP/DNS, ดู leases, reload dnsmasq | superadmin only |

#### Voucher PDF Export
- สร้าง PDF พร้อม QR code ได้ 2 โหมด:
  - **URL mode**: QR = portal URL (แขกแสกนแล้วเปิดหน้า login พร้อม voucher code)
  - **Code mode**: QR = voucher code เฉย ๆ
- Batch export หลาย voucher ในไฟล์เดียว

---

### 2.7 Analytics

#### Usage Snapshots
- Scheduler บันทึก snapshot ทุก 1 ชั่วโมง
- เก็บ: active sessions, total bytes up/down, voucher uses

#### Charts (Chart.js)
- **Sessions over time**: เส้นแสดงจำนวน sessions
- **Bandwidth per hour**: stacked bar (up + down)
- **Peak hours heatmap**: วัน/เวลาที่มีคนใช้เยอะที่สุด
- **Auth breakdown**: pie chart แยก room auth vs voucher auth

#### Time Ranges
- 24 hours, 7 days, 30 days

---

### 2.8 ความปลอดภัย (Security)

#### การเข้ารหัส
- **PMS Credentials:** เข้ารหัสด้วย Fernet (AES-128-CBC + HMAC-SHA256)
- **Admin Passwords:** bcrypt hash
- **JWT:** HMAC-SHA256 signing พร้อม jti สำหรับ revocation

#### Network Security
- **Webhook Signature:** HMAC-SHA256 + `hmac.compare_digest` (timing-safe)
- **Rate Limiting:** Redis-backed counter ต่อ IP
- **nftables DROP:** default drop สำหรับ unauthenticated traffic
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
| `bandwidth_up_kbps` | Integer | Upload limit |
| `bandwidth_down_kbps` | Integer | Download limit |
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

### ตาราง admin_users
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key |
| `username` | String(100) | ชื่อผู้ใช้ (unique) |
| `password_hash` | String(200) | bcrypt hash |
| `role` | Enum | `superadmin` / `staff` |
| `last_login_at` | DateTime(tz) | เวลา login ล่าสุด |

### ตาราง brand_config
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key (fixed) |
| `hotel_name` | String(200) | ชื่อโรงแรม |
| `logo_path` | String(500) | Path ของ logo |
| `primary_color` | String(7) | สีหลัก (hex) |
| `tc_text_th` | Text | Terms & Conditions (ไทย) |
| `tc_text_en` | Text | Terms & Conditions (อังกฤษ) |
| `language` | Enum | `th` / `en` |

### ตาราง dhcp_config
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key (fixed) |
| `enabled` | Boolean | เปิด/ปิด dnsmasq |
| `interface` | String(32) | Interface สำหรับ DHCP |
| `gateway_ip` | String(15) | Gateway IP |
| `subnet` | String(18) | Subnet (CIDR) |
| `dhcp_range_start` | String(15) | IP เริ่มต้น |
| `dhcp_range_end` | String(15) | IP สุดท้าย |
| `lease_time` | String(8) | Lease duration |
| `dns_upstream_1` | String(45) | Primary DNS |
| `dns_upstream_2` | String(45) | Secondary DNS |
| `dns_mode` | Enum | `redirect` / `forward` |
| `log_queries` | Boolean | เปิด DNS logging |

### ตาราง usage_snapshots
| คอลัมน์ | ชนิด | รายละเอียด |
|---------|------|-----------|
| `id` | UUID | Primary key |
| `snapshot_at` | DateTime(tz) | เวลา snapshot |
| `active_sessions` | Integer | จำนวน session ขณะนั้น |
| `total_bytes_up` | BigInteger | รวม upload |
| `total_bytes_down` | BigInteger | รวม download |
| `voucher_uses` | Integer | Voucher ใช้ในชั่วโมงนั้น |

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

### Admin API

| Method | Path | Role | รายละเอียด |
|--------|------|------|-----------|
| `GET` | `/admin/api/sessions` | staff+ | รายการ session ที่ active |
| `DELETE` | `/admin/api/sessions/{id}` | staff+ | Kick session |
| `GET` | `/admin/api/pms` | superadmin | ดู PMS config (masked) |
| `PUT` | `/admin/api/pms` | superadmin | อัปเดต PMS config |
| `POST` | `/admin/api/pms/test` | superadmin | ทดสอบ PMS connection |
| `GET` | `/admin/api/policies` | superadmin | รายการ policies |
| `POST` | `/admin/api/policies` | superadmin | สร้าง policy |
| `PUT` | `/admin/api/policies/{id}` | superadmin | แก้ไข policy |
| `DELETE` | `/admin/api/policies/{id}` | superadmin | ลบ policy |
| `GET` | `/admin/api/rooms` | superadmin | รายการห้อง |
| `PUT` | `/admin/api/rooms/{id}/policy` | superadmin | Assign policy ให้ห้อง |
| `GET` | `/admin/api/analytics/data` | superadmin | ข้อมูล analytics |
| `GET` | `/admin/api/brand` | superadmin | Brand config |
| `PUT` | `/admin/api/brand` | superadmin | อัปเดต brand |
| `POST` | `/admin/brand/logo` | superadmin | Upload logo |
| `GET` | `/admin/api/users` | superadmin | รายการ admin users |
| `POST` | `/admin/api/users` | superadmin | สร้าง admin user |
| `GET` | `/admin/api/dhcp` | superadmin | DHCP config |
| `PUT` | `/admin/api/dhcp` | superadmin | อัปเดต DHCP config |
| `GET` | `/admin/api/dhcp/status` | superadmin | dnsmasq status |
| `GET` | `/admin/api/dhcp/leases` | superadmin | DHCP leases |
| `POST` | `/admin/api/dhcp/reload` | superadmin | Reload dnsmasq |
| `POST` | `/admin/vouchers/batch` | staff+ | สร้าง vouchers หลายตัว |
| `GET` | `/admin/vouchers/{id}/pdf` | staff+ | Download voucher PDF |
| `POST` | `/admin/logout` | staff+ | Logout (token blocklist) |

### Admin HTML Pages

| Path | Role | รายละเอียด |
|------|------|-----------|
| `/admin/login` | public | หน้า login |
| `/admin/` | staff+ | Dashboard |
| `/admin/sessions` | staff+ | Sessions list |
| `/admin/vouchers` | staff+ | Vouchers management |
| `/admin/policies` | superadmin | Policies management |
| `/admin/rooms` | superadmin | Rooms management |
| `/admin/analytics` | superadmin | Analytics charts |
| `/admin/pms` | superadmin | PMS settings |
| `/admin/brand` | superadmin | Brand & config |
| `/admin/users` | superadmin | Admin users |
| `/admin/dhcp` | superadmin | DHCP settings |

### Internal

| Method | Path | Auth | รายละเอียด |
|--------|------|------|-----------|
| `POST` | `/internal/pms/webhook/{id}` | HMAC-SHA256 | รับ checkout event จาก PMS |

---

## 5. Scheduler Jobs

| Job | ความถี่ | รายละเอียด |
|-----|---------|-----------|
| `_expire_job` | ทุก 60 วินาที | ตรวจ session ที่หมดอายุ → ลบ rules + update status |
| `_bytes_job` | ทุก 60 วินาที | อัปเดต bytes_up/bytes_down + enforce data voucher limit |
| `_poll_checkouts_job` | ทุก 300 วินาที | Sync checkout จาก PMS (Cloudbeds, FIAS, Custom) |
| `_analytics_snapshot_job` | ทุก 3600 วินาที | บันทึก usage snapshot สำหรับ analytics |

---

## 6. Environment Variables

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

## 7. ข้อจำกัดปัจจุบัน

| รายการ | สถานะ |
|--------|-------|
| Multi-server deployment | ⚠️ Design สำหรับ single-server hotel |
| IPv6 support | ⚠️ iptables rules ใช้ IPv4 เท่านั้น |
| Data-based voucher realtime enforcement | ⚠️ ตรวจทุก 60 วินาที (ไม่ใช่ realtime) |
