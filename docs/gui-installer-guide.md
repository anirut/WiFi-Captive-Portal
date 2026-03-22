# GUI Installer คู่มือการใช้งาน

คู่มือนี้อธิบายวิธีการใช้งาน GUI Installer สำหรับ WiFi Captive Portal

## สารบัญ

- [ความต้องการของระบบ](#ความต้องการของระบบ)
- [การดาวน์โหลดและติดตั้ง](#การดาวน์โหลดและติดตั้ง)
- [การใช้งาน GUI Installer](#การใช้งาน-gui-installer)
- [โหมดการทำงาน](#โหมดการทำงาน)
- [การแก้ไขปัญหา](#การแก้ไขปัญหา)
- [การ Build จาก Source](#การ-build-จาก-source)

---

## ความต้องการของระบบ

### Hardware
| รายการ | ขั้นต่ำ | แนะนำ |
|--------|---------|-------|
| CPU | 1 core | 2 cores |
| RAM | 1 GB | 2 GB |
| Disk | 10 GB | 20 GB |
| Network Interface Cards | 2 ตัว | 2 ตัว |

### Software
| รายการ | เวอร์ชัน |
|--------|----------|
| Operating System | Ubuntu 22.04 LTS หรือ 24.04 LTS |
| Network Interfaces | WiFi (wlan0) + WAN (eth0) |

### Network Topology
```
Internet
    │
[WAN Interface - eth0]
    │
┌─────────────────────┐
│   Ubuntu Server     │
│  (Captive Portal)   │
│   Portal IP: 8080   │
└─────────────────────┘
    │
[WiFi Interface - wlan0]
    │
┌─────────────────────┐
│   Guest Devices     │
│  DHCP: 192.168.4.x  │
└─────────────────────┘
```

---

## การดาวน์โหลดและติดตั้ง

### วิธีที่ 1: ใช้ Executable (แนะนำ)

1. ดาวน์โหลดไฟล์ `wifi-portal-installer`
2. ตั้งค่า permission:
   ```bash
   chmod +x wifi-portal-installer
   ```
3. รันด้วย sudo:
   ```bash
   sudo ./wifi-portal-installer
   ```

### วิธีที่ 2: รันจาก Source

```bash
# Clone repository
git clone https://github.com/anirut/WiFi-Captive-Portal.git
cd WiFi_Captive_Portal/installer

# ติดตั้ง dependencies
pip install -r requirements.txt

# รัน installer
sudo python3 main.py
```

---

## การใช้งาน GUI Installer

### ขั้นตอนที่ 1: Welcome Page

![Welcome Page](images/welcome-page.png)

หน้าแรกจะแสดง:
- รายละเอียดของ WiFi Captive Portal
- ปุ่มเลือกโหมดการทำงาน:
  - **Install** - ติดตั้งใหม่
  - **Update** - อัพเดทจากเวอร์ชันเก่า
  - **Reconfigure** - แก้ไขการตั้งค่า
  - **Uninstall** - ถอนการติดตั้ง

> **หมายเหตุ:** ต้องรันด้วย `sudo` เท่านั้น

---

### ขั้นตอนที่ 2: System Check

![System Check Page](images/system-check-page.png)

ระบบจะตรวจสอบอัตโนมัติ:

| รายการ | คำอธิบาย | ค่าที่ต้องการ |
|--------|----------|---------------|
| Operating System | ตรวจสอบ OS | Ubuntu 22.04/24.04 |
| Root Privileges | ตรวจสอบสิทธิ์ | ต้องเป็น root |
| Memory | ตรวจสอบ RAM | ขั้นต่ำ 1 GB |
| Disk Space | ตรวจสอบพื้นที่ดิสก์ | ขั้นต่ำ 10 GB |
| Network Interfaces | ตรวจสอบ NICs | ต้องมี 2 ตัวขึ้นไป |
| Internet Connection | ตรวจสอบอินเทอร์เน็ต | ต้องเชื่อมต่อได้ |

หากตรวจสอบไม่ผ่าน จะแสดงข้อความแจ้งเตือนสีแดง ให้แก้ไขก่อนกด Next

---

### ขั้นตอนที่ 3: Network Configuration

![Network Page](images/network-page.png)

#### Network Interfaces
| ช่องกรอก | คำอธิบาย | ตัวอย่าง |
|----------|----------|----------|
| WiFi Interface | Interface สำหรับ Guest devices | wlan0, wlp2s0 |
| WAN Interface | Interface สำหรับ Internet | eth0, enp1s0 |

#### Portal Settings
| ช่องกรอก | คำอธิบาย | ค่า default |
|----------|----------|-------------|
| Portal IP | IP ที่ guests เชื่อมต่อ | 192.168.4.1 |
| Portal Port | Port ของ portal | 8080 |

#### DHCP Configuration
| ช่องกรอก | คำอธิบาย | ค่า default |
|----------|----------|-------------|
| DHCP Start | IP เริ่มต้นของ DHCP range | 192.168.4.10 |
| DHCP End | IP สุดท้ายของ DHCP range | 192.168.4.254 |
| Lease Time | ระยะเวลา DHCP lease | 12 hours |

> **คำแนะนำ:** Portal IP ไม่ควรอยู่ใน DHCP range

---

### ขั้นตอนที่ 4: Security Configuration

![Security Page](images/security-page.png)

#### Admin Credentials
| ช่องกรอก | คำอธิบาย | ข้อกำหนด |
|----------|----------|----------|
| Admin Username | ชื่อผู้ใช้ admin | 3-32 ตัวอักษร, a-z, 0-9, _ |
| Admin Password | รหัสผ่าน admin | ขั้นต่ำ 8 ตัวอักษร |
| Confirm Password | ยืนยันรหัสผ่าน | ต้องตรงกับ Password |

#### Security Keys
| ช่องกรอก | คำอธิบาย |
|----------|----------|
| JWT Secret Key | Key สำหรับ signing JWT tokens (auto-generated) |
| Encryption Key | Fernet key สำหรับ encrypt credentials (auto-generated) |

> **คำแนะนำ:** กดปุ่ม "Generate" เพื่อสร้าง keys อัตโนมัติ

#### Session Settings
| ช่องกรอก | คำอธิบาย | ค่า default |
|----------|----------|-------------|
| Session Duration | อายุ session ชั่วโมง | 24 |
| Auth Rate Limit | จำกัดครั้ง login ต่อนาที | 5 |

---

### ขั้นตอนที่ 5: Installation Progress

![Install Page](images/install-page.png)

ระบบจะติดตั้งอัตโนมัติ แสดง progress bar และ log:

#### ขั้นตอนการติดตั้ง
1. **Installing system packages** (0-20%)
   - apt update
   - install PostgreSQL, Redis, nftables, dnsmasq, Python

2. **Setting up PostgreSQL** (20-40%)
   - Start PostgreSQL service
   - Create database user
   - Create database
   - Grant privileges

3. **Setting up Redis** (40-50%)
   - Start Redis service
   - Test connection

4. **Setting up application** (50-70%)
   - Create application directory (/opt/wifi-portal)
   - Create Python virtual environment
   - Install Python dependencies

5. **Generating configuration** (70-75%)
   - Create .env file
   - Generate security keys

6. **Running migrations** (75-85%)
   - Run Alembic migrations
   - Create database tables

7. **Creating admin user** (85-88%)
   - Create admin user in database

8. **Configuring network** (88-95%)
   - Enable IP forwarding
   - Configure WiFi interface
   - Setup nftables rules
   - Configure dnsmasq DHCP/DNS
   - Setup traffic control

9. **Creating service** (95-100%)
   - Create systemd service
   - Start wifi-portal service

> **หมายเหตุ:** หากเกิดข้อผิดพลาด ระบบจะ rollback การเปลี่ยนแปลงอัตโนมัติ

---

### ขั้นตอนที่ 6: Finish

![Finish Page](images/finish-page.png)

หน้าสุดท้ายแสดง:
- สรุปการติดตั้ง
- Portal URL และ Admin URL
- ปุ่ม "Open Portal" และ "Open Admin Panel"

#### Next Steps
1. เชื่อมต่อ device เข้า WiFi network
2. Device จะถูก redirect ไปที่ portal อัตโนมัติ
3. ทดสอบ authentication ด้วย room number หรือ voucher code
4. เข้า Admin Panel เพื่อจัดการ sessions และ vouchers
5. ตั้งค่า PMS adapter ใน Admin settings

---

## โหมดการทำงาน

### 1. Install (ติดตั้งใหม่)
ติดตั้ง WiFi Captive Portal ทั้งหมด:
- System packages
- Database (PostgreSQL)
- Redis
- Application
- Network configuration
- Systemd service

### 2. Update (อัพเดท)
อัพเดทเวอร์ชันที่ติดตั้งแล้ว:
- Pull latest code
- Update Python dependencies
- Run database migrations
- Restart service

### 3. Reconfigure (แก้ไขการตั้งค่า)
แก้ไขการตั้งค่าโดยไม่ติดตั้งใหม่:
- Network settings (interfaces, IP, DHCP)
- รีสตาร์ท service

### 4. Uninstall (ถอนการติดตั้ง)
ลบ WiFi Captive Portal ทั้งหมด:
- Stop services
- Remove network configuration
- Drop database
- Remove application files
- Remove systemd service

> **คำเตือน:** Uninstall จะลบข้อมูลทั้งหมด รวมถึง database!

---

## การแก้ไขปัญหา

### ตรวจสอบ Service Status

```bash
# ตรวจสอบ portal service
sudo systemctl status wifi-portal

# ตรวจสอบ PostgreSQL
sudo systemctl status postgresql

# ตรวจสอบ Redis
sudo systemctl status redis-server

# ตรวจสอบ dnsmasq
sudo systemctl status dnsmasq
```

### ดู Logs

```bash
# Portal logs
sudo journalctl -u wifi-portal -f

# Installation logs
sudo tail -f /var/log/wifi-portal-installer.log

# Application logs
sudo tail -f /opt/wifi-portal/logs/portal.log
```

### ปัญหาที่พบบ่อย

#### 1. "Must run as root"
**ปัญหา:** รัน installer โดยไม่ใช้ sudo

**แก้ไข:**
```bash
sudo ./wifi-portal-installer
```

#### 2. "Only 1 interface found"
**ปัญหา:** มี network interface ไม่พอ

**แก้ไข:**
- ตรวจสอบว่ามี 2 NICs (WiFi + WAN)
- ตรวจสอบด้วย `ip link show`

#### 3. "PostgreSQL connection failed"
**ปัญหา:** ไม่สามารถเชื่อมต่อ PostgreSQL

**แก้ไข:**
```bash
# Start PostgreSQL
sudo systemctl start postgresql

# Check status
sudo systemctl status postgresql
```

#### 4. "Portal not accessible"
**ปัญหา:** เข้า portal ไม่ได้

**แก้ไข:**
```bash
# Check if service is running
sudo systemctl status wifi-portal

# Check if port is listening
sudo netstat -tlnp | grep 8080

# Check firewall
sudo nft list table inet captive_portal
```

#### 5. "Guests not redirected to portal"
**ปัญหา:** Guest devices ไม่ถูก redirect

**แก้ไข:**
```bash
# Check dnsmasq
sudo systemctl status dnsmasq

# Check nftables rules
sudo nft list table inet captive_portal

# Check IP forwarding
cat /proc/sys/net/ipv4/ip_forward
# Should be 1
```

### Reset Installation

หากต้องการติดตั้งใหม่ทั้งหมด:

```bash
# Run uninstall
sudo ./wifi-portal-installer
# Select "Uninstall" mode

# Then install again
sudo ./wifi-portal-installer
# Select "Install" mode
```

---

## การ Build จาก Source

### Prerequisites
```bash
# Install Python 3.10+
sudo apt install python3 python3-pip python3-venv
```

### Build Steps

```bash
# Navigate to installer directory
cd installer

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Build executable
bash build.sh

# Output: dist/wifi-portal-installer
```

### Build Options

แก้ไข `wifi-portal-installer.spec` เพื่อ custom build:

```python
# Add icon
exe = EXE(
    ...
    icon='resources/icons/app.ico',
)

# Include additional files
datas=[
    ('resources/*', 'resources'),
    ('../docs', 'docs'),  # Include docs
],
```

---

## ไฟล์ที่เกี่ยวข้อง

| Path | คำอธิบาย |
|------|----------|
| `/opt/wifi-portal/` | Application directory |
| `/opt/wifi-portal/.env` | Configuration file |
| `/opt/wifi-portal/.venv/` | Python virtual environment |
| `/opt/wifi-portal/logs/` | Application logs |
| `/etc/systemd/system/wifi-portal.service` | Systemd service |
| `/etc/nftables.d/captive-portal.conf` | nftables rules |
| `/etc/dnsmasq.d/captive-portal` | dnsmasq config |
| `/var/log/wifi-portal-installer.log` | Installation log |

---

## การสนับสนุน

หากพบปัญหาหรือต้องการความช่วยเหลือ:
1. ดู logs ใน `/var/log/wifi-portal-installer.log`
2. ตรวจสอบ service status
3. ดู documentation ใน `docs/` directory
4. สร้าง issue ใน repository

---

## License

ดูรายละเอียดใน LICENSE file
