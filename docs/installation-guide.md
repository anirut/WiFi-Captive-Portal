# คู่มือการติดตั้ง WiFi Captive Portal

> ระบบปฏิบัติการที่รองรับ: **Ubuntu 22.04 LTS / Ubuntu 24.04 LTS**
> เวอร์ชัน: Phase 3 (Admin Dashboard + DHCP/DNS)
> ต้องใช้สิทธิ์ root

---

## ข้อกำหนดของระบบ (System Requirements)

### Hardware
| รายการ | ขั้นต่ำ | แนะนำ |
|--------|--------|-------|
| CPU | 1 core | 2 cores |
| RAM | 1 GB | 2 GB |
| Disk | 10 GB | 20 GB |
| Network Interface | 2 NICs | 2 NICs |

### Network Interfaces ที่ต้องการ
- **WiFi Interface** (เช่น `wlan0`) — ฝั่งแขก (AP/hotspot)
- **WAN Interface** (เช่น `eth0`) — ฝั่งอินเทอร์เน็ต

### Software
| Package | เวอร์ชันขั้นต่ำ |
|---------|--------------|
| Ubuntu | 22.04 LTS |
| Python | 3.12+ |
| PostgreSQL | 12+ |
| Redis | 6+ |
| nftables | 0.9.3+ (kernel 4.16+) |
| iproute2 (tc) | (pre-installed) |
| dnsmasq | 2.x |

---

## วิธีที่ 1: ติดตั้งอัตโนมัติ (แนะนำ)

### ขั้นตอน

**1. Clone โปรเจกต์หรือคัดลอกไฟล์ไปที่เซิร์ฟเวอร์**

```bash
# ตัวอย่าง: clone จาก repository
git clone https://github.com/your-org/wifi-captive-portal.git /opt/captive-portal
cd /opt/captive-portal
```

**2. รัน install script**

```bash
sudo bash scripts/install.sh
```

**3. ตอบคำถามการตั้งค่า**

Script จะถามข้อมูลดังนี้:

```
━━━ CONFIGURATION ━━━

Network Interfaces
  Available interfaces:
   1. eth0
   2. wlan0
   3. lo

[?] WiFi interface (AP/hotspot side) [wlan0]: wlan0
[?] WAN interface (internet/uplink side) [eth0]: eth0
[?] Portal gateway IP (this server's IP on WiFi network) [192.168.1.1]: 192.168.1.1
[?] Portal application port [8080]: 8080

PostgreSQL Database
[?] PostgreSQL host [localhost]: localhost
[?] PostgreSQL port [5432]: 5432
[?] Database name [captive_portal]: captive_portal
[?] Database user [captive]: captive
[?] Database password [auto-generate]: (กด Enter เพื่อสร้างอัตโนมัติ)

Redis
[?] Redis host [localhost]: localhost
[?] Redis port [6379]: 6379
[?] Redis database number [0]: 0

Initial Admin Account
[?] Admin username [admin]: admin
[?] Admin password (min 8 chars): ●●●●●●●●

Deployment
[?] Environment [production]: production
```

**4. รอจนติดตั้งเสร็จ**

```
━━━ ✓  Installation Complete! ━━━

  Portal URL:    http://192.168.1.1:8080
  Admin URL:     http://192.168.1.1:8080/admin
  Admin login:   admin

  Service:       systemctl status captive-portal
  Logs:          journalctl -u captive-portal -f
  Config:        /opt/captive-portal/.env

  Test install:  bash scripts/test.sh
```

**5. ตรวจสอบการติดตั้ง**

```bash
sudo bash scripts/test.sh
```

---

## วิธีที่ 2: ติดตั้งเอง (Manual)

### ขั้นตอนที่ 1: ติดตั้ง System Packages

```bash
# อัปเดต package list
sudo apt-get update

# ติดตั้ง dependencies
sudo apt-get install -y \
    python3.12 python3.12-venv python3.12-dev \
    postgresql postgresql-contrib \
    redis-server \
    iptables iptables-persistent netfilter-persistent \
    iproute2 \
    dnsmasq

# หาก Ubuntu ไม่มี Python 3.12 ให้ใช้ deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
```

### ขั้นตอนที่ 2: ตั้งค่า PostgreSQL

```bash
# เริ่ม service
sudo systemctl enable postgresql
sudo systemctl start postgresql

# สร้าง user และ database
sudo -u postgres psql <<SQL
CREATE USER captive WITH PASSWORD 'your_secure_password';
CREATE DATABASE captive_portal OWNER captive;
GRANT ALL PRIVILEGES ON DATABASE captive_portal TO captive;
SQL
```

### ขั้นตอนที่ 3: ตั้งค่า Redis

```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server

# ทดสอบ
redis-cli ping
# ควรได้: PONG
```

### ขั้นตอนที่ 4: ตั้งค่า dnsmasq

```bash
# หยุด dnsmasq ชั่วคราว (จะถูกจัดการโดย portal app)
sudo systemctl stop dnsmasq

# ตั้งค่าให้โหลดเฉพาะ config ใน drop-in directory
echo "conf-dir=/etc/dnsmasq.d/,*.conf" | sudo tee /etc/dnsmasq.conf

# สร้าง drop-in directory
sudo mkdir -p /etc/dnsmasq.d

# enable service (แต่ยังไม่ start)
sudo systemctl enable dnsmasq
```

### ขั้นตอนที่ 5: ตั้งค่า Python Environment

```bash
cd /opt/captive-portal

# สร้าง virtual environment
python3.12 -m venv .venv

# ติดตั้ง dependencies
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### ขั้นตอนที่ 6: สร้างไฟล์ .env

```bash
# Generate secrets
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')

cat > .env <<EOF
SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY
ENVIRONMENT=production

DATABASE_URL=postgresql+asyncpg://captive:your_secure_password@localhost:5432/captive_portal
REDIS_URL=redis://localhost:6379/0

WIFI_INTERFACE=wlan0
WAN_INTERFACE=eth0
PORTAL_IP=192.168.1.1
PORTAL_PORT=8080

JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=8
AUTH_RATE_LIMIT_ATTEMPTS=5
AUTH_RATE_LIMIT_WINDOW_SECONDS=600
EOF

# ตั้ง permission
chmod 600 .env
```

### ขั้นตอนที่ 7: รัน Database Migration

```bash
cd /opt/captive-portal
.venv/bin/alembic upgrade head
```

ผลลัพธ์ที่ควรได้:
```
INFO  [alembic.runtime.migration] Running upgrade  -> f0b338e7, add opera_fias opera_cloud adapter types
INFO  [alembic.runtime.migration] Running upgrade f0b338e7 -> xxxx, phase3 tables
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

### ขั้นตอนที่ 8: สร้าง Admin User

```bash
cd /opt/captive-portal
.venv/bin/python - <<'PYEOF'
import asyncio, os, sys
os.chdir("/opt/captive-portal")
sys.path.insert(0, "/opt/captive-portal")

async def create_admin():
    from app.core.database import AsyncSessionFactory
    from app.core.models import AdminUser, AdminRole
    from passlib.context import CryptContext
    from sqlalchemy import select

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_ctx.hash("your_admin_password")

    async with AsyncSessionFactory() as db:
        admin = AdminUser(
            username="admin",
            password_hash=hashed,
            role=AdminRole.superadmin,
        )
        db.add(admin)
        await db.commit()
        print("Admin user created.")

asyncio.run(create_admin())
PYEOF
```

### ขั้นตอนที่ 9: ตั้งค่า Network Rules

```bash
# nftables + flowtables + tc (ต้องรัน root)
sudo bash scripts/setup-nftables.sh \
    --wifi wlan0 \
    --wan eth0 \
    --portal-ip 192.168.1.1 \
    --portal-port 8080 \
    --dns-ip 8.8.8.8

# dnsmasq (ต้องรัน root)
sudo bash scripts/setup-dnsmasq.sh
```

### ขั้นตอนที่ 10: สร้าง systemd Service

```bash
sudo tee /etc/systemd/system/captive-portal.service <<EOF
[Unit]
Description=WiFi Captive Portal
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/captive-portal
EnvironmentFile=/opt/captive-portal/.env
ExecStartPre=/opt/captive-portal/scripts/setup-nftables.sh
ExecStart=/opt/captive-portal/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable captive-portal
sudo systemctl start captive-portal
```

### ขั้นตอนที่ 11: ตรวจสอบ

```bash
# ดู service status
systemctl status captive-portal

# ดู logs
journalctl -u captive-portal -f

# ทดสอบ HTTP
curl -s -o /dev/null -w "%{http_code}" http://192.168.1.1:8080/
# ควรได้: 200

# ทดสอบ Admin
curl -s -o /dev/null -w "%{http_code}" http://192.168.1.1:8080/admin/login
# ควรได้: 200
```

---

## การตั้งค่า Network (สำคัญมาก)

### IP Forwarding

ต้องเปิด IP forwarding เพื่อให้ gateway ส่ง traffic ต่อได้:

```bash
# เปิดทันที
sysctl -w net.ipv4.ip_forward=1

# เปิดถาวร (หลัง reboot)
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p
```

### Network Topology แนะนำ

```
Internet
    │
   [eth0] ← WAN Interface
    │
 [Ubuntu Server / Gateway]
    │
   [wlan0] ← WiFi Interface (AP Mode)
    │
[WiFi AP] ← Access Point (ถ้า AP แยก)
    │
[Guest Devices]
```

**กรณีใช้ Router / AP แยก:**
- เซ็ต Default Gateway ของ WiFi network ให้ชี้มาที่ IP ของ Portal server
- เช่น: WiFi subnet `192.168.1.0/24`, Gateway = `192.168.1.1` (IP ของ server)

### ตรวจสอบ nftables rules

```bash
# ดู nftables table
sudo nft list table inet captive_portal

# ดู whitelist set
sudo nft list set inet captive_portal whitelist

# ดู flowtable
sudo nft list flowtable inet captive_portal ft

# ดู tc rules
sudo tc qdisc show dev eth0
sudo tc class show dev eth0
```

### ตรวจสอบ dnsmasq

```bash
# ดู status
sudo systemctl status dnsmasq

# ดู config
cat /etc/dnsmasq.d/captive-portal.conf

# ดู leases
cat /var/lib/misc/dnsmasq.leases
```

---

## การตั้งค่า DHCP/DNS

หลังติดตั้งเสร็จ ให้ตั้งค่า DHCP ผ่าน Admin UI:

1. เข้า Admin Panel: `http://192.168.1.1:8080/admin`
2. Login ด้วย admin account
3. ไปที่ **DHCP** menu
4. ตั้งค่า:
   - **Interface**: wlan0
   - **Gateway IP**: 192.168.1.1
   - **Subnet**: 192.168.1.0/24
   - **DHCP Range**: 192.168.1.10 - 192.168.1.250
   - **Lease Time**: 8h
   - **DNS Mode**: redirect (แนะนำสำหรับ captive portal)
5. กด **Save**

### DNS Mode

| Mode | พฤติกรรม | แนะนำเมื่อ |
|------|----------|----------|
| **redirect** | ตอบทุก DNS query ด้วย portal IP | Captive portal มาตรฐาน |
| **forward** | ส่ง DNS ต่อไป upstream | มีปัญหากับบางอุปกรณ์ |

---

## การ Uninstall

```bash
sudo bash scripts/uninstall.sh
```

Script จะถามว่าจะลบอะไรบ้าง:
- Service
- iptables / tc rules
- dnsmasq config
- Database และ user (optional)
- Virtual environment (optional)
- .env file (optional)
- Application directory (optional — ต้องพิมพ์ `DELETE` ยืนยัน)

---

## การอัปเดต

```bash
# 1. หยุด service
sudo systemctl stop captive-portal

# 2. อัปเดต code
cd /opt/captive-portal
git pull

# 3. อัปเดต dependencies
.venv/bin/pip install -r requirements.txt

# 4. รัน migration
.venv/bin/alembic upgrade head

# 5. เริ่ม service
sudo systemctl start captive-portal
```

---

## Troubleshooting

### Service ไม่สตาร์ท

```bash
# ดู log ล่าสุด
journalctl -u captive-portal -n 50 --no-pager

# ปัญหาที่พบบ่อย:
# - .env หาไม่เจอ: ตรวจว่าไฟล์อยู่ใน WorkingDirectory
# - Port ถูกใช้: lsof -i :8080
# - PostgreSQL ไม่ได้รัน: systemctl start postgresql
# - Redis ไม่ได้รัน: systemctl start redis-server
# - dnsmasq config error: dnsmasq --test
```

### Database Connection Error

```bash
# ทดสอบ connection โดยตรง
PGPASSWORD=your_password psql -h localhost -U captive -d captive_portal -c "SELECT 1"

# ดู pg_hba.conf
sudo cat $(find /etc/postgresql -name pg_hba.conf)

# ตรวจว่ามี rule สำหรับ user captive
grep captive /etc/postgresql/*/main/pg_hba.conf
```

### nftables ไม่ทำงาน

```bash
# ตรวจว่า nftables ติดตั้ง
nft --version

# ตรวจ kernel version (ต้อง >= 4.16 สำหรับ flowtables)
uname -r

# ตรวจว่า table มีอยู่
nft list tables

# ตรวจว่า IP Forwarding เปิดอยู่
cat /proc/sys/net/ipv4/ip_forward
# ต้องได้ 1

# ตรวจว่า WIFI_INTERFACE ถูกต้อง
ip link show

# รัน setup-nftables.sh ใหม่
sudo WIFI_IF=wlan0 PORTAL_IP=192.168.1.1 PORTAL_PORT=8080 bash scripts/setup-nftables.sh
```

### dnsmasq ไม่ทำงาน

```bash
# ทดสอบ config
sudo dnsmasq --test -C /etc/dnsmasq.d/captive-portal.conf

# ดู status
sudo systemctl status dnsmasq

# ดู logs
journalctl -u dnsmasq -n 50

# รัน manual
sudo dnsmasq -d -C /etc/dnsmasq.d/captive-portal.conf
```

### แขก Login ไม่ได้ (PMS ไม่ response)

```bash
# ทดสอบ PMS connection ผ่าน admin UI
# ไปที่ /admin/pms แล้วกด "Test Connection"

# หรือใช้ API
curl -X POST http://localhost:8080/admin/pms/test \
  -H "Content-Type: application/json" \
  -H "Cookie: admin_token=YOUR_TOKEN" \
  -d '{"type": "cloudbeds", "config": {"api_key": "xxx", "property_id": "yyy"}}'
```

### ตรวจสอบ Rate Limit

```bash
# ดู keys ใน Redis
redis-cli keys "rate_limit:*"

# ลบ rate limit สำหรับ IP หนึ่ง (กรณี test)
redis-cli del "rate_limit:192.168.1.100"
```

### Admin Login ไม่ได้

```bash
# รีเซ็ต password
cd /opt/captive-portal
.venv/bin/python - <<'PYEOF'
import asyncio, os, sys
os.chdir("/opt/captive-portal")
sys.path.insert(0, "/opt/captive-portal")

async def reset_password():
    from app.core.database import AsyncSessionFactory
    from app.core.models import AdminUser
    from passlib.context import CryptContext
    from sqlalchemy import select

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    new_hash = pwd_ctx.hash("new_password_here")

    async with AsyncSessionFactory() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.username == "admin"))
        admin = result.scalar_one_or_none()
        if admin:
            admin.password_hash = new_hash
            await db.commit()
            print("Password reset.")
        else:
            print("Admin user not found.")

asyncio.run(reset_password())
PYEOF
```

---

## สรุปคำสั่งสำคัญ

```bash
# Service management
systemctl start|stop|restart|status captive-portal

# Logs
journalctl -u captive-portal -f
journalctl -u captive-portal --since "1 hour ago"

# Database
psql -h localhost -U captive -d captive_portal

# Test installation
bash /opt/captive-portal/scripts/test.sh
bash /opt/captive-portal/scripts/test.sh --quick    # เร็ว ข้าม HTTP check
bash /opt/captive-portal/scripts/test.sh --verbose  # แสดง error detail

# Reset network rules
sudo bash /opt/captive-portal/scripts/setup-nftables.sh
sudo bash /opt/captive-portal/scripts/setup-dnsmasq.sh

# Run migrations
cd /opt/captive-portal && .venv/bin/alembic upgrade head

# dnsmasq
sudo systemctl restart dnsmasq
cat /var/lib/misc/dnsmasq.leases
```
