# คู่มือการใช้งาน WiFi Captive Portal

> สำหรับ: ผู้ดูแลระบบ (Admin) และ เจ้าหน้าที่โรงแรม
> เวอร์ชัน: Phase 2

---

## ส่วนที่ 1: สำหรับแขก (Guest)

### 1.1 วิธีการเชื่อมต่อ WiFi

**ขั้นตอน:**

1. เปิด WiFi บนอุปกรณ์ แล้วเลือกเครือข่าย WiFi ของโรงแรม
2. เปิดเบราว์เซอร์ (Chrome / Safari / Firefox)
3. ระบบจะ**เปลี่ยนหน้าอัตโนมัติ**ไปยังหน้า Login Portal
   - หากไม่เปลี่ยนอัตโนมัติ ให้เปิด `http://192.168.1.1:8080` (ตาม IP ที่โรงแรมกำหนด)

---

### 1.2 ล็อกอินด้วยหมายเลขห้อง

**ใช้เมื่อ:** แขกที่เช็คอินผ่านระบบ PMS ของโรงแรม

1. เลือกแท็บ **"Room Login"** (หรือ "เข้าสู่ระบบด้วยห้องพัก")
2. กรอกข้อมูล:
   - **Room Number** — หมายเลขห้องพัก เช่น `101`, `502A`
   - **Last Name** — นามสกุล (ตรงกับที่ลงทะเบียนเช็คอิน)
3. ติ๊ก ✅ ยอมรับเงื่อนไขการใช้งาน (Terms & Conditions)
4. กด **"Connect"**

**ผลลัพธ์:**
- ✅ สำเร็จ → หน้า Success ปรากฏ สามารถใช้อินเทอร์เน็ตได้ทันที
- ❌ ล้มเหลว → ข้อความแสดง error:
  - `guest_not_checked_in` — ชื่อ/ห้องไม่ตรงกับระบบโรงแรม ให้ติดต่อ Front Desk
  - `rate_limited` — พยายามหลายครั้งเกินไป รอ 10 นาทีแล้วลองใหม่

**ระยะเวลา Session:**
- Session มีอายุถึงเวลา **Check-out** ที่กำหนดไว้ในระบบ
- หรือตาม Policy ของห้องพัก (ถ้ากำหนดไว้)

---

### 1.3 ล็อกอินด้วย Voucher Code

**ใช้เมื่อ:** ได้รับรหัส WiFi จากเจ้าหน้าที่ (เช่น กรณีไม่มีการจอง หรือ Day Pass)

1. เลือกแท็บ **"Voucher"** (หรือ "รหัส WiFi")
2. กรอก **Voucher Code** เช่น `K9ZXYB7Q`
3. ติ๊ก ✅ ยอมรับเงื่อนไขการใช้งาน
4. กด **"Connect"**

**ผลลัพธ์:**
- ✅ สำเร็จ → ใช้งาน WiFi ได้ทันที
- ❌ ล้มเหลว:
  - `invalid_code` — รหัสไม่ถูกต้อง
  - `expired` — รหัสหมดอายุแล้ว
  - `no_uses_remaining` — รหัสถูกใช้จนครบแล้ว

**ระยะเวลา Session:**
- ตามที่กำหนดไว้ใน Voucher (เช่น 2 ชั่วโมง, 24 ชั่วโมง)

---

### 1.4 ตัดการเชื่อมต่อ

หากต้องการตัดการเชื่อมต่อก่อนหมดอายุ:

1. เปิดหน้า Portal อีกครั้งที่ `http://192.168.1.1:8080`
2. กดปุ่ม **"Disconnect"** (หรือ "ตัดการเชื่อมต่อ")

หรือส่ง POST request ไปที่ `/session/disconnect`

---

## ส่วนที่ 2: สำหรับผู้ดูแลระบบ (Admin)

### 2.1 เข้าสู่ Admin Panel

**URL:** `http://192.168.1.1:8080/admin`

> **หมายเหตุ:** ปัจจุบัน Admin Panel ไม่ต้องการ authentication (planned feature)
> ในการ Deploy จริง ควรจำกัดการเข้าถึง Admin URL ด้วย firewall หรือ VPN

---

### 2.2 ดูรายการ Session ที่ Active

**Endpoint:** `GET /admin/sessions`

**ตัวอย่างผลลัพธ์:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "ip": "192.168.1.105",
    "connected_at": "2026-03-21T08:30:00+00:00",
    "expires_at": "2026-03-23T12:00:00+00:00"
  },
  {
    "id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "ip": "192.168.1.110",
    "connected_at": "2026-03-21T10:15:00+00:00",
    "expires_at": "2026-03-21T12:15:00+00:00"
  }
]
```

**ตัวอย่าง curl:**
```bash
curl http://192.168.1.1:8080/admin/sessions
```

---

### 2.3 Kick Session (ตัด WiFi แขก)

**Endpoint:** `DELETE /admin/sessions/{session_id}`

**ตัวอย่าง:**
```bash
curl -X DELETE http://192.168.1.1:8080/admin/sessions/550e8400-e29b-41d4-a716-446655440000
```

**ผลลัพธ์:**
```json
{"status": "kicked"}
```

**สิ่งที่เกิดขึ้น:**
1. ลบ iptables rule สำหรับ IP ของแขก
2. ลบ tc bandwidth limit
3. อัปเดต session status เป็น `kicked`
4. แขกจะไม่สามารถเชื่อมต่อได้ทันที

---

### 2.4 ตั้งค่า PMS Integration

#### ดูการตั้งค่าปัจจุบัน

```bash
curl http://192.168.1.1:8080/admin/pms
```

**ผลลัพธ์:**
```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "type": "cloudbeds",
  "is_active": true,
  "last_sync_at": "2026-03-21T10:00:00+00:00",
  "config": {
    "api_url": "https://api.cloudbeds.com",
    "api_key": "***",
    "property_id": "hotel123"
  }
}
```

> Credentials จะถูกซ่อนด้วย `***` เพื่อความปลอดภัย

---

#### ตั้งค่า PMS แต่ละประเภท

**Opera Cloud:**
```bash
curl -X PUT http://192.168.1.1:8080/admin/pms \
  -H "Content-Type: application/json" \
  -d '{
    "type": "opera_cloud",
    "config": {
      "api_url": "https://api.oracle.com/ohip",
      "client_id": "your_client_id",
      "client_secret": "your_client_secret",
      "hotel_id": "HOTEL_CODE"
    }
  }'
```

**Opera FIAS (Opera 5 / Suite8):**
```bash
curl -X PUT http://192.168.1.1:8080/admin/pms \
  -H "Content-Type: application/json" \
  -d '{
    "type": "opera_fias",
    "config": {
      "host": "192.168.50.10",
      "port": "10000",
      "auth_key": "YOUR_AUTH_KEY",
      "vendor_id": "WIFI_PORTAL"
    }
  }'
```

**Cloudbeds:**
```bash
curl -X PUT http://192.168.1.1:8080/admin/pms \
  -H "Content-Type: application/json" \
  -d '{
    "type": "cloudbeds",
    "config": {
      "api_url": "https://api.cloudbeds.com",
      "api_key": "your_api_key",
      "property_id": "your_property_id"
    }
  }'
```

**Mews:**
```bash
curl -X PUT http://192.168.1.1:8080/admin/pms \
  -H "Content-Type: application/json" \
  -d '{
    "type": "mews",
    "config": {
      "api_url": "https://www.mews.li",
      "client_token": "your_client_token",
      "access_token": "your_access_token"
    }
  }'
```

**Custom REST PMS:**
```bash
curl -X PUT http://192.168.1.1:8080/admin/pms \
  -H "Content-Type: application/json" \
  -d '{
    "type": "custom",
    "config": {
      "api_url": "https://pms.yourhotal.com",
      "auth_type": "bearer",
      "token": "your_api_token",
      "verify_endpoint": "/api/guest/verify",
      "guest_by_room_endpoint": "/api/guest/by-room",
      "checkouts_endpoint": "/api/guest/checkouts",
      "health_endpoint": "/api/health",
      "field_map": {
        "pms_id": "data.reservationId",
        "room_number": "data.roomNumber",
        "last_name": "data.guest.lastName",
        "first_name": "data.guest.firstName",
        "check_in": "data.checkInDate",
        "check_out": "data.checkOutDate"
      }
    }
  }'
```

**Standalone (ไม่มี PMS):**
```bash
curl -X PUT http://192.168.1.1:8080/admin/pms \
  -H "Content-Type: application/json" \
  -d '{"type": "standalone", "config": {}}'
```

---

#### ทดสอบการเชื่อมต่อ PMS

```bash
curl -X POST http://192.168.1.1:8080/admin/pms/test \
  -H "Content-Type: application/json" \
  -d '{
    "type": "cloudbeds",
    "config": {
      "api_url": "https://api.cloudbeds.com",
      "api_key": "your_api_key",
      "property_id": "your_property_id"
    }
  }'
```

**ผลลัพธ์ (เชื่อมต่อได้):**
```json
{"ok": true, "latency_ms": 145.3, "error": null}
```

**ผลลัพธ์ (เชื่อมต่อไม่ได้):**
```json
{"ok": false, "latency_ms": 5002.1, "error": "Connection timeout"}
```

---

### 2.5 ตั้งค่า Webhook สำหรับ Opera Cloud / Mews

Webhook ทำให้ระบบทราบการเช็คเอาท์แบบ real-time โดยไม่ต้อง poll

**ขั้นตอน:**

**1. สร้าง webhook secret**
```bash
# สร้าง random secret
SECRET=$(openssl rand -hex 32)
echo "Webhook Secret: $SECRET"

# คำนวณ hash ที่จะเก็บใน DB
SECRET_HASH=$(echo -n "$SECRET" | sha256sum | cut -d' ' -f1)
echo "Hash to store: $SECRET_HASH"
```

**2. บันทึก hash ลงใน database**
```sql
-- เชื่อมต่อ DB แล้วรัน:
UPDATE pms_adapters
SET webhook_secret = 'SECRET_HASH_ที่คำนวณได้'
WHERE is_active = true;
```

**3. ตั้งค่า Webhook URL ใน PMS ของคุณ**

| PMS | Webhook URL |
|-----|-------------|
| Opera Cloud | `http://YOUR_PORTAL_IP:8080/internal/pms/webhook/{adapter_uuid}` |
| Mews | `http://YOUR_PORTAL_IP:8080/internal/pms/webhook/{adapter_uuid}` |

**4. ตั้งค่า Header ใน PMS**
- Header: `X-PMS-Secret`
- Value: ค่า Secret (ไม่ใช่ hash) ที่สร้างในขั้นตอนที่ 1

**5. ทดสอบ Webhook**
```bash
# ค้นหา adapter_id
psql -U captive -d captive_portal -c "SELECT id FROM pms_adapters WHERE is_active = true;"

# ทดสอบ Opera Cloud event
curl -X POST http://192.168.1.1:8080/internal/pms/webhook/YOUR_ADAPTER_UUID \
  -H "Content-Type: application/json" \
  -H "X-PMS-Secret: YOUR_SECRET" \
  -d '{"eventType": "CHECKED_OUT", "roomNumber": "101"}'

# ผลลัพธ์ที่ถูกต้อง:
# {"ok": true}
```

---

### 2.6 จัดการข้อมูลแขก (Standalone Mode)

ในกรณีที่ใช้ Standalone adapter (ไม่มี PMS) ต้องเพิ่มข้อมูลแขกในฐานข้อมูลเอง:

```sql
-- เชื่อมต่อ database
psql -h localhost -U captive -d captive_portal

-- เพิ่มแขก
INSERT INTO guests (id, room_number, last_name, first_name, check_in, check_out, max_devices)
VALUES (
    gen_random_uuid(),
    '101',
    'Smith',
    'John',
    '2026-03-21 14:00:00+07',
    '2026-03-23 12:00:00+07',
    3
);

-- ดูรายการแขกที่เช็คอินอยู่
SELECT room_number, last_name, first_name, check_in, check_out
FROM guests
WHERE check_in <= now() AND check_out >= now()
ORDER BY room_number;
```

---

### 2.7 จัดการ Voucher

Voucher ต้องจัดการผ่าน Database โดยตรง (Admin UI สำหรับ Voucher อยู่ใน roadmap):

```sql
-- สร้าง Voucher แบบ 2 ชั่วโมง (120 นาที)
INSERT INTO vouchers (id, code, type, duration_minutes, max_devices, created_by, max_uses)
VALUES (
    gen_random_uuid(),
    'WELCOME1',       -- รหัส (เปลี่ยนได้)
    'time',
    120,              -- 2 ชั่วโมง
    2,                -- ใช้ได้ 2 อุปกรณ์
    (SELECT id FROM admin_users LIMIT 1),
    1                 -- ใช้ได้ 1 ครั้ง
);

-- สร้าง Voucher แบบ 24 ชั่วโมง ใช้ได้ 50 คน (Day Pass)
INSERT INTO vouchers (id, code, type, duration_minutes, max_devices, created_by, max_uses, expires_at)
VALUES (
    gen_random_uuid(),
    'DAYPASS1',
    'time',
    1440,             -- 24 ชั่วโมง
    1,
    (SELECT id FROM admin_users LIMIT 1),
    50,               -- ใช้ได้ 50 ครั้ง
    '2026-12-31 23:59:59+07'  -- หมดอายุสิ้นปี
);

-- ดูรายการ Voucher ทั้งหมด
SELECT code, type, duration_minutes, used_count, max_uses, expires_at
FROM vouchers
ORDER BY created_at DESC;
```

**สร้าง Voucher Code แบบ Random:**
```bash
# ใช้ Python generator ของระบบ
cd /opt/captive-portal
.venv/bin/python -c "from app.voucher.generator import generate_code; print(generate_code())"
```

---

### 2.8 ดู Logs

```bash
# ดู logs แบบ real-time
journalctl -u captive-portal -f

# ดู logs ย้อนหลัง 1 ชั่วโมง
journalctl -u captive-portal --since "1 hour ago"

# ดู logs วันนี้
journalctl -u captive-portal --since today

# ดู error logs เท่านั้น
journalctl -u captive-portal -p err

# ตัวอย่าง log ที่ควรเห็น:
# INFO  Session created: ip=192.168.1.105 guest=101/Smith expires=2026-03-23T12:00:00
# INFO  Scheduler expired 2 sessions
# INFO  Poll checkout: room=205, expired 1 sessions
# INFO  Webhook checkout: room=302, expired 2 sessions
```

---

### 2.9 Monitoring และ Health Check

**ตรวจสอบสถานะระบบ:**
```bash
# ใช้ test script
bash /opt/captive-portal/scripts/test.sh

# ผลลัพธ์ตัวอย่าง:
#   ── System ──
#   ✓  python3 >= 3.12 available
#   ✓  iptables available
#   ✓  tc (iproute2) available
#   ✓  psql client available
#   ✓  redis-cli available
#
#   ── PostgreSQL ──
#   ✓  PostgreSQL service running
#   ✓  DB host reachable (localhost:5432)
#   ✓  DB 'captive_portal' exists
#   ✓  Table 'guests' exists
#   ✓  Table 'sessions' exists
#   ✓  Admin user exists (1 user(s))
#
#   ── Redis ──
#   ✓  Redis service running
#   ✓  Redis responds to PING
#
#   ── Network Rules ──
#   ✓  iptables FORWARD rules present
#   ✓  iptables NAT PREROUTING redirect present
#   ✓  tc HTB qdisc on eth0
#
#   ── HTTP Endpoints ──
#   ✓  Portal root / responds (HTTP 2xx/3xx)
#   ✓  Admin /admin/sessions endpoint exists
#
#   ━━━ Result: ALL TESTS PASSED (21/21) ━━━
```

**ตรวจสอบ Active Sessions:**
```bash
# ผ่าน API
curl -s http://localhost:8080/admin/sessions | python3 -m json.tool

# ผ่าน Database โดยตรง
psql -U captive -d captive_portal -c "
  SELECT s.ip_address, g.room_number, g.last_name,
         s.connected_at, s.expires_at, s.status
  FROM sessions s
  LEFT JOIN guests g ON s.guest_id = g.id
  WHERE s.status = 'active'
  ORDER BY s.connected_at DESC;
"
```

---

## ส่วนที่ 3: การ Configure ขั้นสูง

### 3.1 Bandwidth Policy

กำหนด bandwidth limit ตามประเภทห้อง:

```sql
-- สร้าง Policy สำหรับห้อง Standard (5 Mbps download)
INSERT INTO policies (id, name, bandwidth_up_kbps, bandwidth_down_kbps, session_duration_min, max_devices)
VALUES (
    gen_random_uuid(),
    'Standard Room Policy',
    0,      -- Upload: ไม่จำกัด (ยังไม่รองรับ)
    5120,   -- Download: 5 Mbps (5120 kbps)
    0,      -- Duration: ถึง check-out
    3       -- Max 3 devices
);

-- สร้าง Policy สำหรับ Suite (ไม่จำกัด)
INSERT INTO policies (id, name, bandwidth_up_kbps, bandwidth_down_kbps, session_duration_min, max_devices)
VALUES (
    gen_random_uuid(),
    'Suite Policy',
    0,
    0,      -- ไม่จำกัด
    0,
    5
);

-- เชื่อม Policy กับห้อง
UPDATE rooms SET policy_id = 'POLICY_UUID' WHERE number = '101';

-- หรือเชื่อมทุกห้องประเภท standard
UPDATE rooms r
SET policy_id = p.id
FROM policies p
WHERE p.name = 'Standard Room Policy'
AND r.room_type = 'standard';
```

---

### 3.2 Environment Variables ขั้นสูง

แก้ไขไฟล์ `.env`:

```bash
sudo nano /opt/captive-portal/.env
```

**ตัวอย่างการปรับค่า:**
```bash
# เพิ่มจำนวนครั้ง login ต่อ 10 นาที (default: 5)
AUTH_RATE_LIMIT_ATTEMPTS=10

# เปลี่ยน window เป็น 5 นาที
AUTH_RATE_LIMIT_WINDOW_SECONDS=300

# ปรับ port (ถ้าต้องการ)
PORTAL_PORT=80
```

หลังแก้ไข `.env` ต้อง restart service:
```bash
sudo systemctl restart captive-portal
```

---

### 3.3 Backup Database

```bash
# Backup
PGPASSWORD=your_password pg_dump \
    -h localhost -U captive captive_portal \
    > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore
PGPASSWORD=your_password psql \
    -h localhost -U captive captive_portal \
    < backup_20260321_120000.sql
```

---

### 3.4 ตั้งค่า SSL/HTTPS (Production)

แนะนำให้ใช้ Nginx เป็น reverse proxy:

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx

# ตั้งค่า Nginx
sudo tee /etc/nginx/sites-available/captive-portal <<'EOF'
server {
    listen 80;
    server_name portal.yourhotal.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/captive-portal /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# SSL Certificate (ถ้ามี domain)
sudo certbot --nginx -d portal.yourhotal.com
```

---

## ส่วนที่ 4: ข้อมูลอ้างอิง

### 4.1 Error Codes

| Code | ความหมาย | วิธีแก้ |
|------|---------|---------|
| `guest_not_checked_in` | แขกไม่พบในระบบ PMS | ตรวจสอบชื่อ/ห้องกับ Front Desk |
| `rate_limited` | Login มากเกินไป | รอ 10 นาทีแล้วลองใหม่ |
| `invalid_code` | Voucher ไม่ถูกต้อง | ตรวจสอบรหัสกับเจ้าหน้าที่ |
| `expired` | Voucher/Session หมดอายุ | ขอรหัสใหม่ |
| `no_uses_remaining` | Voucher ใช้ครบแล้ว | ขอรหัสใหม่ |
| `pms_unavailable` | PMS ไม่ตอบสนอง | ติดต่อ IT หรือใช้ Standalone mode |
| `adapter_not_found` | Webhook ID ไม่ถูกต้อง | ตรวจสอบ UUID ใน URL |
| `invalid_secret` | Webhook secret ไม่ตรง | ตรวจสอบ X-PMS-Secret header |
| `no_active_adapter` | ไม่มี PMS ที่ active | ตั้งค่า PMS ผ่าน PUT /admin/pms |
| `not_found` | Session ไม่พบ | Session อาจหมดอายุไปแล้ว |

---

### 4.2 PMS Config Keys Reference

**Opera Cloud:**
| Key | จำเป็น | รายละเอียด |
|-----|--------|-----------|
| `api_url` | ✅ | OHIP API base URL |
| `client_id` | ✅ | OAuth2 client ID |
| `client_secret` | ✅ | OAuth2 client secret |
| `hotel_id` | ✅ | Hotel code ใน Opera |

**Opera FIAS:**
| Key | จำเป็น | รายละเอียด |
|-----|--------|-----------|
| `host` | ✅ | IP ของ Opera FIAS server |
| `port` | ✅ | TCP port (มักจะเป็น 10000) |
| `auth_key` | ✅ | Authentication key |
| `vendor_id` | ✅ | Vendor identifier string |

**Cloudbeds:**
| Key | จำเป็น | รายละเอียด |
|-----|--------|-----------|
| `api_key` | ✅ | Cloudbeds API key |
| `property_id` | ✅ | Property ID |
| `api_url` | — | default: `https://api.cloudbeds.com` |

**Mews:**
| Key | จำเป็น | รายละเอียด |
|-----|--------|-----------|
| `client_token` | ✅ | Client token |
| `access_token` | ✅ | Access token |
| `api_url` | — | default: `https://www.mews.li` |

**Custom:**
| Key | จำเป็น | รายละเอียด |
|-----|--------|-----------|
| `api_url` | ✅ | Base URL ของ PMS |
| `auth_type` | ✅ | `bearer` หรือ `basic` |
| `token` | ✅* | Bearer token (ถ้า auth_type=bearer) |
| `username` | ✅* | Username (ถ้า auth_type=basic) |
| `password` | ✅* | Password (ถ้า auth_type=basic) |
| `verify_endpoint` | ✅ | Path สำหรับ verify_guest |
| `guest_by_room_endpoint` | ✅ | Path สำหรับ get_guest_by_room |
| `checkouts_endpoint` | — | Path สำหรับ get_checkouts |
| `health_endpoint` | — | Path สำหรับ health_check |
| `field_map` | ✅ | JSON mapping PMS fields → GuestInfo |

---

### 4.3 Session Status Values

| Status | ความหมาย |
|--------|---------|
| `active` | Session กำลังใช้งาน |
| `expired` | หมดอายุตามเวลา หรือ checkout |
| `kicked` | ถูก Admin หรือแขกตัดเอง |

---

### 4.4 คำสั่งฉุกเฉิน

```bash
# ปิด WiFi ทุกคน (emergency)
sudo iptables -P FORWARD DROP
sudo iptables -F FORWARD

# เปิด WiFi ทุกคน (ไม่มี auth)
sudo iptables -P FORWARD ACCEPT

# Reset กลับเป็นปกติ
sudo bash /opt/captive-portal/scripts/setup-iptables.sh

# ลบ session ทั้งหมดออกจาก DB
psql -U captive -d captive_portal -c "
  UPDATE sessions SET status='expired' WHERE status='active';
"
# แล้ว restart service เพื่อ reset iptables
sudo systemctl restart captive-portal
```
