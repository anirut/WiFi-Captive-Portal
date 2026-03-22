# 🏨 WiFi Captive Portal

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-blue.svg)](https://www.postgresql.org/)

A production-ready **Hotel WiFi Captive Portal** system with enterprise-grade features, PMS integrations, bandwidth management, and a modern admin dashboard.

---

## ✨ Key Features

- 🔐 **Multiple Authentication Methods** - Room + Last Name, Voucher Codes
- 🏨 **PMS Integrations** - Opera Cloud, Opera FIAS, Cloudbeds, Mews, Custom REST
- 📊 **Bandwidth Management** - Traffic Control (tc) with HTB shaping
- 🛡️ **Modern Firewall** - nftables with O(1) set lookups and flowtables
- 📱 **Responsive Admin Dashboard** - Real-time analytics, session management
- 🎫 **Voucher System** - PDF generation with QR codes
- 🌐 **Multi-language Support** - Thai/English localization
- 🔧 **GUI Installer** - PyQt6 desktop installer for easy deployment

---

## 📋 Table of Contents

- [System Architecture](#-system-architecture)
- [Authentication Flow](#-authentication-flow)
- [Session Lifecycle](#-session-lifecycle)
- [Network Topology](#-network-topology)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Technology Stack](#-technology-stack)
- [Documentation](#-documentation)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🏗 System Architecture

```mermaid
graph TB
    subgraph "Guest Devices"
        G1[📱 Phone]
        G2[💻 Laptop]
        G3[📺 Smart TV]
    end

    subgraph "Gateway Server"
        subgraph "Network Layer"
            NF[nftables<br/>Firewall]
            TC[tc HTB<br/>Bandwidth]
            DNS[dnsmasq<br/>DHCP/DNS]
        end

        subgraph "Application Layer"
            FP[FastAPI Portal<br/>:8080]
            AD[Admin Dashboard<br/>:8080/admin]
            SM[Session Manager]
            SCH[APScheduler]
        end

        subgraph "Data Layer"
            PG[(PostgreSQL)]
            RD[(Redis)]
        end

        subgraph "PMS Adapters"
            OP[Opera Cloud]
            OF[Opera FIAS]
            CB[Cloudbeds]
            MW[Mews]
            SA[Standalone DB]
        end
    end

    subgraph "External"
        WAN[🌐 Internet]
    end

    G1 & G2 & G3 --> DNS
    DNS --> FP
    FP --> SM
    SM --> NF & TC
    SM --> PG & RD
    SM --> OP & OF & CB & MW & SA
    SCH --> SM
    NF --> WAN
    AD --> SM
```

---

## 🔐 Authentication Flow

```mermaid
flowchart TD
    A[📱 Guest connects to WiFi] --> B[DNS Query Redirected]
    B --> C[🌐 Portal Page Loaded]
    C --> D{Choose Auth Method}

    D -->|Room Auth| E[Enter Room + Last Name]
    D -->|Voucher| F[Enter Voucher Code]

    E --> G[PMS Lookup]
    G --> H{Valid Guest?}
    H -->|No| I[❌ Access Denied]
    H -->|Yes| J[✅ Create Session]

    F --> K[Voucher Validation]
    K --> L{Valid Voucher?}
    L -->|No| I
    L -->|Yes| J

    J --> M[Add to nftables Whitelist]
    M --> N[Apply Bandwidth Limits]
    N --> O[🌐 Internet Access Granted]

    O --> P[Session Active]
    P --> Q{Expiration Trigger}
    Q -->|Timeout| R[Remove from Whitelist]
    Q -->|Checkout Sync| R
    Q -->|Manual Kick| R
    Q -->|Data Limit| R
    R --> S[❌ Session Expired]
```

---

## 🔄 Session Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Connecting: Guest connects to WiFi

    Connecting --> Portal: DNS redirect

    Portal --> Authenticating: Submit credentials

    Authenticating --> Validating: PMS/Voucher check

    Validating --> Active: ✅ Auth success
    Validating --> Portal: ❌ Auth failed

    Active --> Active: Data tracking
    Active --> Active: Bandwidth applied

    Active --> Expiring: Time limit reached
    Active --> Expiring: Checkout detected
    Active --> Expiring: Manual kick
    Active --> Expiring: Data limit reached

    Expiring --> Expired: Remove from whitelist
    Expiring --> Expired: Remove bandwidth limits

    Expired --> [*]: Session closed

    note right of Active
        - nftables whitelist active
        - tc bandwidth shaping
        - Byte counter tracking
        - Auto-renewal possible
    end note
```

---

## 🌐 Network Topology

```mermaid
flowchart LR
    subgraph Internet
        WWW[🌐 Internet]
    end

    subgraph Gateway["Ubuntu Gateway Server"]
        WAN[eth0<br/>WAN Interface]
        WIFI[wlan0<br/>WiFi Interface]

        subgraph Portal["Captive Portal :8080"]
            HTTP[FastAPI Server]
        end

        subgraph NetStack["Network Stack"]
            NFT[nftables<br/>Filtering]
            HTC[tc HTB<br/>QoS]
            DNSM[dnsmasq<br/>DHCP + DNS]
        end
    end

    subgraph Guests["Guest Network"]
        D1[📱 Device 1]
        D2[💻 Device 2]
        D3[📱 Device 3]
    end

    WWW <--> WAN
    WAN --> NFT
    NFT <--> HTC
    HTC <--> WIFI
    WIFI <--> D1 & D2 & D3
    D1 & D2 & D3 --> DNSM
    DNSM --> Portal
    Portal --> NFT
```

---

## 🚀 Quick Start

### Prerequisites

- Ubuntu 22.04 LTS or 24.04 LTS
- Python 3.12+
- PostgreSQL 14+
- Redis 6+
- Two network interfaces (WiFi + WAN)

### Option 1: GUI Installer (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-org/wifi-captive-portal.git
cd wifi-captive-portal

# Run the GUI installer
python installer/main.py
```

The PyQt6 installer provides:
- ✅ System validation
- ✅ Dependency installation
- ✅ Database setup
- ✅ Service configuration
- ✅ Automatic rollback on failure

### Option 2: Command Line

```bash
# Clone and enter directory
git clone https://github.com/your-org/wifi-captive-portal.git
cd wifi-captive-portal

# Run installation script
sudo bash scripts/install.sh

# Configure environment
cp .env.example .env
nano .env

# Start the service
sudo systemctl start captive-portal
```

---

## 📁 Project Structure

```
wifi-captive-portal/
├── app/
│   ├── core/              # Config, database, auth, models
│   ├── network/           # nftables, tc, session management
│   ├── pms/               # PMS adapters (Opera, Cloudbeds, Mews)
│   ├── voucher/           # Voucher generation & validation
│   ├── portal/            # Guest-facing routes & templates
│   ├── admin/             # Admin dashboard routes & templates
│   └── main.py            # FastAPI entry point
├── docs/                  # Documentation
├── scripts/               # Installation & setup scripts
├── installer/             # PyQt6 GUI installer
├── static/                # CSS, JS, images
├── tests/                 # Test suite
├── alembic/               # Database migrations
├── .env.example           # Environment template
└── requirements.txt       # Python dependencies
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file from the template:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key (≥32 chars) | - |
| `ENCRYPTION_KEY` | Fernet key for credentials | - |
| `DATABASE_URL` | PostgreSQL connection string | - |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `WIFI_INTERFACE` | WiFi interface name | `wlan0` |
| `WAN_INTERFACE` | WAN interface name | `eth0` |
| `PORTAL_IP` | Portal IP address | `10.0.0.1` |
| `PORTAL_PORT` | Portal port | `8080` |

### Network Modes

```mermaid
flowchart TB
    subgraph DNSModes["DNS Mode Selection"]
        mode{DNS_MODE}
        mode -->|redirect| RED[Redirect Mode<br/>All DNS → Portal IP]
        mode -->|forward| FWD[Forward Mode<br/>DNS → Upstream Server]
    end

    subgraph RedirectFlow["Redirect Mode Flow"]
        R1[Guest DNS Query] --> R2[dnsmasq intercepts]
        R2 --> R3[Returns Portal IP]
        R3 --> R4[Guest loads portal]
    end

    subgraph ForwardFlow["Forward Mode Flow"]
        F1[Guest DNS Query] --> F2[dnsmasq forwards]
        F2 --> F3[Upstream DNS resolves]
        F3 --> F4[Returns real IP]
    end

    RED --> RedirectFlow
    FWD --> ForwardFlow
```

---

## 🏨 PMS Integration

```mermaid
flowchart TB
    subgraph Portal["Captive Portal"]
        AUTH[Authentication Request]
        SM[Session Manager]
    end

    subgraph Factory["PMS Factory"]
        LF[load_adapter]
        CACHE[Cached Adapter]
        LF --> CACHE
    end

    subgraph Adapters["PMS Adapters"]
        subgraph Opera["Opera PMS"]
            OC[Opera Cloud<br/>REST + OAuth2]
            OF[Opera FIAS<br/>TCP/XML]
        end

        subgraph Cloud["Cloud PMS"]
            CB[Cloudbeds<br/>REST API]
            MW[Mews<br/>REST + Webhook]
        end

        subgraph Custom["Custom"]
            CR[Custom REST<br/>Configurable Mapping]
            SA[Standalone<br/>Local Database]
        end
    end

    subgraph Data["Guest Data"]
        GI[GuestInfo Dataclass]
        GI --> |room_number| R1[Room Number]
        GI --> |last_name| R2[Last Name]
        GI --> |check_in| R3[Check-in Date]
        GI --> |check_out| R4[Check-out Date]
        GI --> |room_type| R5[Room Type]
    end

    AUTH --> SM
    SM --> LF
    CACHE --> OC & OF & CB & MW & CR & SA
    OC & OF & CB & MW & CR & SA --> GI
```

### Supported PMS Systems

| PMS | Protocol | Webhook | Polling |
|-----|----------|---------|---------|
| Opera Cloud | REST/OAuth2 | ✅ | - |
| Opera FIAS | TCP/XML | - | ✅ |
| Cloudbeds | REST API | - | ✅ |
| Mews | REST API | ✅ | - |
| Custom REST | Configurable | ✅ | ✅ |
| Standalone | Local DB | - | - |

---

## 📊 Admin Dashboard

The admin dashboard provides comprehensive management:

```mermaid
mindmap
  root((Admin Dashboard))
    Dashboard
      Real-time Statistics
      Active Sessions
      Recent Activity
    Sessions
      View All Sessions
      Kick Sessions
      Filter by Status
    Vouchers
      Create Single
      Batch Generate
      PDF Export
      QR Codes
    Policies
      Bandwidth Limits
      Device Limits
      Room Type Mapping
    Analytics
      Session Charts
      Bandwidth Usage
      Peak Hours
      Auth Breakdown
    Settings
      PMS Configuration
      Branding
      Terms & Conditions
      Languages
    Network
      DHCP Config
      DNS Config
      Interface Status
```

---

## 🧪 Development

### Setup Development Environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Run single test
pytest tests/test_portal/test_portal_routes.py::test_room_auth_success -v
```

---

## 🛡️ Security Features

```mermaid
flowchart LR
    subgraph Security["Security Layers"]
        RL[Rate Limiting<br/>5 attempts/10 min]
        JWT[JWT Auth<br/>with jti revocation]
        ENC[Fernet Encryption<br/>for credentials]
        HMAC[HMAC-SHA256<br/>Webhook signatures]
        HASH[bcrypt<br/>Password hashing]
    end

    subgraph Network["Network Security"]
        NF[nftables<br/>Stateful filtering]
        WLIST[Whitelist<br/>IP-based access]
        ISOL[Client Isolation<br/>No inter-device traffic]
    end

    Security --> Network
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Features](docs/features.md) | Complete feature documentation |
| [Installation Guide](docs/installation-guide.md) | Step-by-step installation |
| [User Manual](docs/user-manual.md) | Guest & Admin user guide |
| [GUI Installer Guide](docs/gui-installer-guide.md) | Desktop installer usage |
| [CLAUDE.md](CLAUDE.md) | Development guidance |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [nftables](https://netfilter.org/projects/nftables/) - Linux packet filtering
- [HTMX](https://htmx.org/) - Modern HTML-first frontend
- [Tailwind CSS](https://tailwindcss.com/) - Utility-first CSS framework

---

<p align="center">
  <strong>Made with ❤️ for the hospitality industry</strong>
</p>
