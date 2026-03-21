# คู่มือการใช้งาน WiFi Captive Portal

> สำหรับ: ผู้ดูแลระบบ (Admin) และ เจ้าหน้าที่โรงแรม
> เวอร์ชัน: Phase 3 (Admin Dashboard + DHCP/DNS)
> อัปเดต: 2026-03-21

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

1. เลือกแท็บ **"Room Login"** (หรือ "เข้าสู่ระบบด้วยห้องพัก
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
  - `max_devices_reached` — ถึงจำนวนอุปกรณ์สูงสุดที่อนุญาต

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
- **Time-based voucher**: ตามระยะเวลาที่กำหนด (เช่น 2 ชม., 24 ชม.)
- **Data-based voucher**: ใช้ได้จนกว่าจะถึงโควต้าข้อมูล (เช่น 500MB) — ระบบจะตัด session อัตโนมัติเมื่อใช้ครบ

---

### 1.4 ตัดการเชื่อมต่อ

หากต้องการตัดการเชื่อมต่อก่อนหมดอายุ:

1. เปิดหน้า Portal อีกครั้งที่ `http://192.168.1.1:8080`
2. กดปุ่ม **"Disconnect"** (หรือ "ตัดการเชื่อมต่อ")

---

## ส่วนที่ 2: สำหรับผู้ดูแลระบบ (Admin)

### 2.1 เข้าสู่ Admin Panel

**URL:** `http://192.168.1.1:8080/admin`

**การ Login:**
1. กรอก Username และ Password
2. กด **"Login"**
3. ระบบจะจดจำ session ไว้ 8 ชั่วโมง (ตาม `JWT_EXPIRE_HOURS`)

**Roles และสิทธิ์:**
| Role | สิทธิ์การเข้าถึง |
|------|------------------|
| **superadmin** | เข้าได้ทุก menu |
| **staff** | Dashboard, Sessions, Vouchers เท่านั้น |

---

### 2.2 Dashboard

**Menu:** Dashboard
**Role:** staff + superadmin

แสดงข้อมูลภาพรวมระบบ:

| Card | รายละเอียด |
|------|-----------|
| 📊 **Active Sessions** | จำนวนแขกที่กำลังใช้งาน WiFi |
| 🎟️ **Vouchers Used Today** | Voucher ที่ถูกใช้วันนี้ |
| 📥 **Total Bytes Down Today** | ปริมาณข้อมูลที่โหลดวันนี้ |
| 📋 **Recent Sessions** | 10 sessions ล่าสุด พร้อมปุ่ม Kick |

---

### 2.3 Sessions Management

**Menu:** Sessions
**Role:** staff + superadmin

#### รายการ Active Sessions

ตารางแสดงข้อมูล:

| Column | รายละเอียด |
|--------|-----------|
| IP Address | IP ของอุปกรณ์แขก |
| Room / Voucher | หมายเลขห้อง หรือ voucher code |
| Connected At | เวลาเริ่มเชื่อมต่อ |
| Expires At | เวลาหมดอายุ session |
| Bytes Down | ปริมาณข้อมูลที่โหลด (human-readable) |
| Status | สถานะ (active) |
| Action | ปุ่ม Kick |

#### Kick Session
1. กดปุ่ม **"Kick"** ที่แถวของ session นั้น
2. ระบบจะ:
   - ลบ nftables whitelist entry
   - ลบ tc bandwidth limit
   - ลบ DNS bypass rule
   - อัปเดต status เป็น `kicked`
3. แขกจะถูกตัดการเชื่อมต่อทันที

#### Auto-refresh
- รายการ refresh อัตโนมัติทุก 30 วินาที

---

### 2.4 Vouchers Management

**Menu:** Vouchers
**Role:** staff + superadmin

#### สร้าง Voucher เดี่ยว

1. กด **"New Voucher"**
2. กรอกข้อมูล:
   - **Type**:
     - `time` — กำหนดระยะเวลา
     - `data` — กำหนดปริมาณข้อมูล
   - **Duration (minutes)**: ระยะเวลา (ถ้า type=time)
   - **Data Limit (MB)**: โควต้าข้อมูล (ถ้า type=data)
   - **Max Uses**: ใช้ได้กี่ครั้ง (default: 1)
   - **Max Devices**: อุปกรณ์ต่อ session (default: 1)
   - **Expires At**: วันหมดอายุ voucher (optional)
3. กด **"Create"**
4. ระบบจะ generate code อัตโนมัติ

#### Batch Generate Vouchers

1. กด **"Batch Generate"**
2. กรอก **Count** (1-100)
3. ตั้งค่าอื่น ๆ เหมือน voucher เดี่ยว
4. กด **"Generate"**
5. ระบบจะสร้าง vouchers หลายตัวพร้อม codes ที่ generate อัตโนมัติ

#### Export Voucher PDF

1. กดปุ่ม **"PDF"** ที่ voucher ที่ต้องการ
2. เลือก **QR Mode**:
   - **URL** — QR code = portal URL (แนะนำ แขกแสกนแล้วเปิดหน้า login)
   - **Code** — QR code = voucher code เฉย ๆ
3. PDF จะ download อัตโนมัติ
4. PDF ประกอบด้วย:
   - Voucher code (ข้อความ)
   - QR code
   - ระยะเวลา/โควต้า
   - ชื่อโรงแรม

#### รายการ Vouchers

ตารางแสดง:
- Code
- Type (time/data)
- Duration / Data Limit
- Used Count / Max Uses
- Max Devices
- Expires At
- Created At
- Actions (PDF, Delete)

---

### 2.5 Rooms & Policies

**Menu:** Rooms & Policies
**Role:** superadmin only

#### Policies Tab

**สร้าง Policy:**
Policy คือชุดการตั้งค่า bandwidth และอุปกรณ์สำหรับห้องประเภทต่าง ๆ

1. กด **"New Policy"**
2. กรอก:
   - **Name**: ชื่อ policy (เช่น "Standard Room", "VIP Suite")
   - **Upload Bandwidth (kbps)**: 0 = ไม่จำกัด
   - **Download Bandwidth (kbps)**: 0 = ไม่จำกัด
   - **Session Duration (min)**: 0 = ถึง check-out
   - **Max Devices**: จำนวนอุปกรณ์สูงสุด (default: 3)
3. กด **"Save"**

**ตัวอย่าง Policies:**
| Policy | Upload | Download | Duration | Max Devices |
|--------|--------|----------|----------|-------------|
| Standard | 0 | 5120 (5 Mbps) | 0 | 3 |
| Deluxe | 0 | 10240 (10 Mbps) | 0 | 4 |
| Suite | 0 | 0 (unlimited) | 0 | 5 |
| Meeting Room | 0 | 2048 (2 Mbps) | 120 (2 ชม.) | 10 |

#### Rooms Tab

**Assign Policy ให้ห้อง:**
1. ดูรายการห้องทั้งหมด
2. เลือก **Policy** จาก dropdown ที่แถวของห้องนั้น
3. ระบบจะบันทึกอัตโนมัติ (HTMX)
4. Policy จะมีผลกับ session ใหม่เท่านั้น (session เดิมไม่เปลี่ยน)

---

### 2.6 Analytics

**Menu:** Analytics
**Role:** superadmin only

#### Time Range Selector
เลือกช่วงเวลา: **24h**, **7d**, **30d**

#### Charts (Chart.js)

**1. Sessions Over Time** (Line Chart)
- แกน X: เวลา
- แกน Y: จำนวน active sessions
- แสดงแนวโน้มการใช้งาน

**2. Bandwidth Per Hour** (Stacked Bar Chart)
- แกน X: เวลา
- แกน Y: bytes (up + down stacked)
- แสดงปริมาณการใช้ข้อมูล

**3. Peak Hours Heatmap**
- แกน X: ชั่วโมง (0-23)
- แกน Y: วันในสัปดาห์ (Sun-Sat)
- สี: ความเข้ม = จำนวน sessions
- ช่วยวางแผน capacity

**4. Auth Breakdown** (Pie Chart)
- Room Authentication vs Voucher Authentication
- แสดงสัดส่วนวิธี login

---

### 2.7 PMS Settings

**Menu:** PMS Settings
**Role:** superadmin only

#### เลือก PMS Type

| Type | Protocol | Checkout Sync |
|------|----------|---------------|
| Opera Cloud | REST/OAuth2 | Webhook |
| Opera FIAS | TCP/XML | Polling (5 min) |
| Cloudbeds | REST/API Key | Polling (5 min) |
| Mews | REST | Webhook |
| Custom | REST | Polling (5 min) |
| Standalone | Local DB | N/A |

#### Configuration Fields

**Opera Cloud:**
| Field | รายละเอียด |
|-------|-----------|
| API URL | OHIP API base URL |
| Client ID | OAuth2 client ID |
| Client Secret | OAuth2 client secret |
| Hotel ID | Hotel code |

**Opera FIAS:**
| Field | รายละเอียด |
|-------|-----------|
| Host | FIAS server IP |
| Port | TCP port (usually 10000) |
| Auth Key | Authentication key |
| Vendor ID | Vendor identifier |

**Cloudbeds:**
| Field | รายละเอียด |
|-------|-----------|
| API URL | API base URL (default: api.cloudbeds.com) |
| API Key | API key |
| Property ID | Property ID |

**Mews:**
| Field | รายละเอียด |
|-------|-----------|
| API URL | API base URL (default: www.mews.li) |
| Client Token | Client token |
| Access Token | Access token |

**Custom:**
| Field | รายละเอียด |
|-------|-----------|
| API URL | Base URL |
| Auth Type | bearer / basic |
| Token/Username/Password | Credentials |
| Verify Endpoint | Path for guest verification |
| Field Map | JSON path mapping |

#### Test Connection
- กด **"Test Connection"**
- ระบบจะทดสอบการเชื่อมต่อและแสดง:
  - Status: OK / Failed
  - Latency (ms)
  - Error message (ถ้า failed)

---

### 2.8 Brand & Config

**Menu:** Brand & Config
**Role:** superadmin only

#### Brand Settings

| Field | รายละเอียด | Default |
|-------|-----------|---------|
| Hotel Name | ชื่อโรงแรม (แสดงใน portal) | Hotel WiFi |
| Primary Color | สีหลัก (hex code) | #3B82F6 |
| Language | ภาษาหลัก | th |

#### Logo Upload

1. กด **"Choose File"** ในส่วน Logo
2. เลือกรูป (รองรับ: PNG, JPG, WebP)
3. ขนาดสูงสุด: **2 MB**
4. กด **"Upload"**
5. Logo จะแสดงใน:
   - Portal login page
   - Admin sidebar
   - Voucher PDF

#### Terms & Conditions

- กรอกข้อความสำหรับ:
  - **ภาษาไทย** (tc_text_th)
  - **ภาษาอังกฤษ** (tc_text_en)
- แขกต้องติ๊กยอมรับก่อน login ได้

---

### 2.9 Admin Users

**Menu:** Admin Users
**Role:** superadmin only

#### รายการ Users

ตารางแสดง:
| Column | รายละเอียด |
|--------|-----------|
| Username | ชื่อผู้ใช้ |
| Role | superadmin / staff |
| Last Login | เวลา login ล่าสุด |
| Actions | Delete (ไม่มี edit) |

#### สร้าง User ใหม่

1. กด **"New User"**
2. กรอก:
   - **Username**: ชื่อผู้ใช้ (unique)
   - **Password**: รหัสผ่าน (อย่างน้อย 8 ตัวอักษร)
   - **Role**:
     - `superadmin` — เข้าได้ทุก menu
     - `staff` — เข้าได้เฉพาะ Dashboard, Sessions, Vouchers
3. กด **"Create"**

**⚠️ ข้อควรระวัง:**
- ควรมี superadmin อย่างน้อย 1 คนเสมอ
- Staff ไม่สามารถสร้าง/ลบ users ได้
- Password ถูก hash ด้วย bcrypt

---

### 2.10 DHCP Settings

**Menu:** DHCP
**Role:** superadmin only

#### Service Status Card

แสดงข้อมูล:
| Item | รายละเอียด |
|------|-----------|
| Status Badge | 🟢 Running / 🔴 Stopped |
| Active Leases | จำนวน DHCP leases ปัจจุบัน |
| Config File | มี/ไม่มี config file |
| Reload Button | กดเพื่อ reload dnsmasq |

#### Configuration Card

| Field | รายละเอียด | Default |
|-------|-----------|---------|
| **Enabled** | เปิด/ปิด dnsmasq | ✅ |
| **Interface** | Interface สำหรับ DHCP | wlan0 |
| **Gateway IP** | IP ของ gateway (server) | 192.168.1.1 |
| **Subnet** | Subnet in CIDR | 192.168.1.0/24 |
| **DHCP Range Start** | IP เริ่มต้นสำหรับแจก | 192.168.1.10 |
| **DHCP Range End** | IP สุดท้ายสำหรับแจก | 192.168.1.250 |
| **Lease Time** | ระยะเวลา lease | 8h |
| **DNS Upstream 1** | Primary upstream DNS | 8.8.8.8 |
| **DNS Upstream 2** | Secondary upstream DNS | 8.8.4.4 |
| **DNS Mode** | redirect / forward | redirect |
| **Log Queries** | เปิด DNS/DHCP logging | ❌ |

#### DNS Mode อธิบาย

| Mode | พฤติกรรม | แนะนำเมื่อ |
|------|----------|----------|
| **redirect** | dnsmasq ตอบทุก DNS query ด้วย portal IP; authenticated guests ได้รับ DNS bypass | Captive portal มาตรฐาน, ต้องการให้ portal detection ทำงานดี |
| **forward** | dnsmasq ส่ง DNS queries ต่อไป upstream DNS | มีปัญหากับบางอุปกรณ์, ต้องการความเรียบง่าย |

#### Active Leases Card

ตารางแสดง DHCP leases ปัจจุบัน:

| Column | รายละเอียด |
|--------|-----------|
| MAC Address | MAC ของอุปกรณ์ |
| IP Address | IP ที่ได้รับ |
| Hostname | ชื่ออุปกรณ์ (ถ้ามี) |
| Expires At | เวลา lease หมดอายุ |

- Auto-refresh ทุก 30 วินาที
- มี search box สำหรับ filter

---

### 2.11 Logout

- กด **"Logout"** ที่มุมขวาบน (top bar)
- Token จะถูกเพิ่มเข้า Redis blocklist
- Cookie จะถูกลบ
- ต้อง login ใหม่เพื่อเข้าใช้งาน

---

## ส่วนที่ 3: การ Configure ขั้นสูง

### 3.1 Webhook Setup (Opera Cloud / Mews)

Webhook ทำให้ระบบรับ checkout event แบบ real-time (ไม่ต้องรอ polling)

**ขั้นตอน:**

1. **สร้าง webhook secret:**
```bash
SECRET=$(openssl rand -hex 32)
echo "Webhook Secret: $SECRET"
```

2. **ตั้งค่าใน PMS:**
   - Webhook URL: `http://YOUR_PORTAL_IP:8080/internal/pms/webhook/{adapter_id}`
   - Header: `X-PMS-Secret`
   - Value: secret จากขั้นตอนที่ 1

3. **หา adapter_id:**
```bash
psql -U captive -d captive_portal -c "SELECT id FROM pms_adapters WHERE is_active = true;"
```

4. **ทดสอบ:**
```bash
curl -X POST http://192.168.1.1:8080/internal/pms/webhook/YOUR_ADAPTER_UUID \
  -H "Content-Type: application/json" \
  -H "X-PMS-Secret: YOUR_SECRET" \
  -d '{"eventType": "CHECKED_OUT", "roomNumber": "101"}'
```

---

### 3.2 Backup & Restore

**Backup:**
```bash
PGPASSWORD=your_password pg_dump \
    -h localhost -U captive captive_portal \
    > backup_$(date +%Y%m%d_%H%M%S).sql
```

**Restore:**
```bash
PGPASSWORD=your_password psql \
    -h localhost -U captive captive_portal \
    < backup_20260321_120000.sql
```

---

### 3.3 SSL/HTTPS Setup

แนะนำให้ใช้ Nginx reverse proxy:

```bash
# Install Nginx
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Create config
sudo tee /etc/nginx/sites-available/captive-portal <<'EOF'
server {
    listen 80;
    server_name portal.yourhotel.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/captive-portal /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx

# Get SSL certificate
sudo certbot --nginx -d portal.yourhotel.com
```

---

## ส่วนที่ 4: ข้อมูลอ้างอิง

### 4.1 Error Codes

| Code | ความหมาย | วิธีแก้ |
|------|---------|---------|
| `guest_not_checked_in` | แขกไม่พบในระบบ PMS | ตรวจสอบชื่อ/ห้องกับ Front Desk |
| `rate_limited` | Login มากเกินไป | รอ 10 นาทีแล้วลองใหม่ |
| `max_devices_reached` | ถึงจำนวนอุปกรณ์สูงสุด | รอ session เก่าหมดอายุ หรือติดต่อ Admin |
| `invalid_code` | Voucher ไม่ถูกต้อง | ตรวจสอบรหัสกับเจ้าหน้าที่ |
| `expired` | Voucher/Session หมดอายุ | ขอรหัสใหม่ |
| `no_uses_remaining` | Voucher ใช้ครบแล้ว | ขอรหัสใหม่ |
| `pms_unavailable` | PMS ไม่ตอบสนอง | ติดต่อ IT หรือใช้ Standalone mode |
| `unauthorized` | Admin token ไม่ถูกต้อง/หมดอายุ | Login ใหม่ |
| `forbidden` | ไม่มีสิทธิ์เข้าถึงหน้านี้ | ติดต่อ superadmin |

---

### 4.2 Session Status Values

| Status | ความหมาย |
|--------|---------|
| `active` | Session กำลังใช้งาน |
| `expired` | หมดอายุตามเวลา, checkout, หรือ data quota ครบ |
| `kicked` | ถูก Admin หรือแขกตัดเอง |

---

### 4.3 Voucher Types

| Type | ความหมาย | การตัด session |
|------|---------|---------------|
| `time` | กำหนดระยะเวลา (นาที) | เมื่อถึงเวลาที่กำหนด |
| `data` | กำหนดปริมาณข้อมูล (MB) | เมื่อ bytes_down >= quota (ตรวจทุก 60 วินาที) |

---

### 4.4 คำสั่งฉุกเฉิน

```bash
# ปิด WiFi ทุกคน (emergency)
sudo nft delete table inet captive_portal
sudo iptables -P FORWARD DROP

# เปิด WiFi ทุกคน (ไม่มี auth - ใช้เฉพาะกรณีฉุกเฉิน)
sudo nft delete table inet captive_portal
sudo iptables -P FORWARD ACCEPT

# Reset กลับเป็นปกติ
sudo bash /opt/captive-portal/scripts/setup-nftables.sh

# ลบ session ทั้งหมด (force logout ทุกคน)
psql -U captive -d captive_portal -c "
  UPDATE sessions SET status='expired' WHERE status='active';
"
# แล้ว restart service
sudo systemctl restart captive-portal

# ดู whitelist ปัจจุบัน
sudo nft list set inet captive_portal whitelist

# ดู logs แบบ real-time
journalctl -u captive-portal -f

# ดู dnsmasq logs
journalctl -u dnsmasq -f
```

---

### 4.5 การดูแลระบบประจำวัน

**แนะนำให้ตรวจสอบ:**
1. จำนวน active sessions (ผ่าน Dashboard)
2. ปริมาณ bandwidth ที่ใช้ (ผ่าน Analytics)
3. Error logs: `journalctl -u captive-portal -p err`
4. พื้นที่ดิสก์: `df -h`
5. สถานะ services: `systemctl status captive-portal postgresql redis-server dnsmasq`

**แนะนำให้ทำประจำสัปดาห์:**
1. Backup database
2. ตรวจสอบ analytics หา outlier
3. ลบ vouchers ที่หมดอายุแล้ว
