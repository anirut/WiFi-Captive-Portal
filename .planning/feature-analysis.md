# WiFi Captive Portal Feature Analysis

**Analysis Date:** 2026-03-25  
**Purpose:** Compare current implementation against industry standards to identify missing features

---

## Executive Summary

This document analyzes the WiFi Captive Portal project against common features found in open-source captive portals (openNDS, NoDogSplash, CoovaChilli) and commercial solutions. The project is well-architected for hotel use cases with comprehensive PMS integrations, but lacks several features common in modern captive portals that could enhance commercial viability.

---

## Current Implementation Status

### ✅ Already Implemented

| Feature | Description | Implementation |
|---------|-------------|----------------|
| **Room Authentication** | Guest login via room number + last name | PMS verification (Opera FIAS/Cloud, Cloudbeds, Mews) |
| **Voucher Authentication** | Prepaid access codes with duration/data limits | Full CRUD, PDF generation with QR codes |
| **Bandwidth Shaping** | Per-session rate limiting | Linux TC with HTB, per-client classes |
| **Traffic Control** | Network access enforcement | nftables (whitelist, DNS bypass sets) |
| **DHCP Server** | IP address assignment | dnsmasq integrated |
| **DNS Server** | Name resolution with captive redirect | dnsmasq (redirect/forward modes) |
| **Captive Portal Detection** | Auto-trigger login on connect | Multi-OS support (Android, iOS, Windows, Firefox) |
| **Session Management** | Create, expire, kick, self-disconnect | APScheduler (expire every 60s) |
| **Policy System** | Per-room-type bandwidth/duration limits | Policy model → Room assignment |
| **Analytics** | Usage tracking and visualization | Hourly snapshots, peak hours, auth breakdown |
| **Multi-language** | Thai/English support | BrandConfig.language (th/en) |
| **Rate Limiting** | Brute-force protection | Redis-based per-IP auth rate limiting |
| **Admin Dashboard** | Full management interface | FastAPI + Jinja2 templates |
| **Brand Customization** | Logo, colors, terms & conditions | BrandConfig model + logo upload |
| **Guest Device Limits** | Max concurrent devices per guest | Policy.max_devices enforcement |
| **Logout via Domain** | Special `logout.wifi` domain detection | dnsmasq-auth resolves logout.wifi → portal IP |

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Guest Device                              │
│                     (CPD Detection)                              │
└─────────────────────┬───────────────────────────────────────────┘
                      │ HTTP Request (any URL)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Portal (FastAPI)                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │/auth     │  │/session  │  │/admin/*  │  │ CPD Probes│        │
│  │room      │  │disconnect│  │ Dashboard │  │ (Android │        │
│  │voucher   │  │          │  │ Sessions  │  │ iOS etc) │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       │             │              │              │              │
│  ┌────▼─────┐  ┌────▼─────┐  ┌────▼─────┐  ┌────▼─────┐        │
│  │PMSAdapter│  │Session   │  │AdminUser │  │Redirect  │        │
│  │(Opera/   │  │Manager   │  │(JWT auth)│  │to /login │        │
│  │Cloudbeds)│  │          │  │          │  │          │        │
│  └──────────┘  └────┬─────┘  └──────────┘  └──────────┘        │
└─────────────────────┼───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Network Layer                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │nftables  │  │ tc (HTB) │  │ dnsmasq  │  │ dnsmasq  │        │
│  │whitelist │  │ bandwidth│  │ (DHCP+   │  │ -auth    │        │
│  │ DNS bypass│ │ shaping  │  │  DNS)    │  │(logout)  │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│       │              │              │              │              │
│       └──────────────┴──────────────┴──────────────┘              │
│                              │                                   │
│                              ▼                                   │
│                      Internet Gateway                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Missing Features Analysis

### Category: Authentication & Identity

#### 1. Social WiFi Login (High Priority)

**What it is:** Allow guests to authenticate using Facebook, Google, LINE, or other social accounts.

**Why other portals have it:**
- Marketing data collection (email, demographics)
- Reduced friction (no typing room numbers)
- Common in cafes, retail, hotels seeking guest engagement
- Lead generation for email marketing

**Implementation approach:**
```
OAuth 2.0 flow:
1. Guest clicks "Login with Facebook/Google/LINE"
2. Redirect to OAuth provider
3. Provider returns email, name, profile
4. Create session linked to social profile
5. Store marketing-consented data
```

**Files to add:**
- `app/auth/social.py` - OAuth handlers
- `app/models.py` - Add `SocialProvider`, `GuestAuthMethod` models
- `app/portal/templates/social_login.html`

---

#### 2. SMS/Email OTP Verification (High Priority)

**What it is:** One-time password sent via SMS or email for authentication.

**Why other portals have it:**
- Legal compliance in many countries (data retention laws)
- Identity verification for public venues
- Alternative to room-based auth for non-guests
- Can charge for SMS verification (monetization)

**Implementation approach:**
```
OTP Flow:
1. Guest enters phone/email
2. Server generates OTP (6 digits, 5-min expiry)
3. Send via SMS gateway (Twilio, Vonage) or SMTP
4. Guest enters OTP
5. Create session on success
```

**Files to add:**
- `app/auth/otp.py` - OTP generation/validation
- `app/services/sms.py` - SMS gateway integration
- `app/services/email.py` - Email sender
- `app/models.py` - Add `OTPVerification` model

---

#### 3. Click-to-Continue (TOS Acceptance Only) (Medium Priority)

**What it is:** Simple splash page with "Accept Terms & Continue" button.

**Why other portals have it:**
- Simplest user experience
- Free WiFi without PMS dependency
- Common for lobbies, restaurants, public areas
- Fallback when PMS is unavailable

**Implementation approach:**
```
Flow:
1. Guest connects to WiFi
2. Portal shows TOS + "Continue" button
3. Client submits form
4. Server creates session (with optional duration limit)
5. Redirect to success page

Already partially implemented:
- TOS text stored in BrandConfig.tc_text_th/tc_text_en
- Schema validation exists for terms acceptance
- Need: authentication mode toggle (room/voucher/click-to-continue)
```

**Files to modify:**
- `app/portal/router.py` - Add `/auth/accept` endpoint
- `app/portal/schemas.py` - Add `TOSAuthRequest`
- `app/portal/templates/login.html` - Add TOS-only mode

---

#### 4. Payment Gateway Integration (Medium Priority)

**What it is:** Pay for WiFi access via credit card or digital payment.

**Why other portals have it:**
- Monetization for premium WiFi
- Tiered pricing (basic/free vs premium/paid)
- Common in airports, convention centers, resorts

**Implementation approach:**
```
Payment Flow:
1. Guest selects plan (hourly/daily/weekly)
2. Redirect to Stripe/PayPal checkout
3. Webhook confirms payment
4. Create session with paid duration/bandwidth
```

**Files to add:**
- `app/payments/stripe_router.py` - Stripe webhook handler
- `app/models.py` - Add `PaymentPlan`, `PaymentTransaction` models
- `app/portal/templates/plans.html` - Plan selection UI

---

### Category: Security & Compliance

#### 5. Data Volume Quota Enforcement (High Priority)

**What it is:** Enforce `data_limit_mb` stored in Voucher model.

**Current gap:** Vouchers have `data_limit_mb` field but no enforcement logic.

**Implementation approach:**
```python
# In session_manager.py or scheduler job
async def enforce_data_quotas():
    sessions = get_active_sessions()
    for session in sessions:
        if session.voucher and session.voucher.data_limit_mb:
            used_mb = (session.bytes_up + session.bytes_down) / (1024 * 1024)
            if used_mb >= session.voucher.data_limit_mb:
               await expire_session(session,reason="data_quota_exceeded")
```

**Files to modify:**
- `app/network/session_manager.py` - Add quota check
- `app/network/scheduler.py` - Add quota enforcement job

---

#### 6. Walled Garden / Domain Allowlist (Medium Priority)

**What it is:** Allow access to specified domains without authentication.

**Why other portals have it:**
- Allow hotel website for reservations before login
- Enable emergency services websites
- Partner services access

**Implementation approach:**
```bash
# nftables DNS bypass for walled garden domains
# Resolve allowed domains to IPs, add to bypass set
for domain in $WALLED_GARDEN_DOMAINS; do
    IPs=$(dig +short $domain)
    for ip in $IPs; do
        nft add element inet captive dns_bypass {$ip}
    done
done
```

**Files to add:**
- `app/models.py` - Add `WalledGardenDomain` model
- `app/network/nftables.py` - Add `add_walled_garden()` function
- `app/admin/router.py` - CRUD for allowed domains

---

#### 7. MAC Address Bypass List (Medium Priority)

**What it is:** Allowlist specific MAC addresses to bypass authentication.

**Why other portals have it:**
- IoT devices (smart TVs, printers, thermostats)
- Staff devices
- POS systems
- Security cameras

**Implementation approach:**
```python
# In Session creation
async def should_bypass_auth(mac_address: str) -> bool:
    bypass = await db.execute(
        select(MacBypass).where(MacBypass.mac == mac_address, MacBypass.active == True)
    )
    return bypass.scalar_one_or_none() is not None
```

**Files to add:**
- `app/models.py` - Add `MacBypass` model
- `app/admin/router.py` - CRUD for MAC bypass
- `app/portal/router.py` - Check bypass before showing login

---

#### 8. Captive Portal API - RFC 8910/8908 (Low Priority)

**What it is:** Modern standard for captive portal detection (replaces CPD probing).

**Why other portals have it:**
- Cleaner detection than HTTP redirects
- Future-proof (operating systems moving toward this)
- Better battery life on mobile devices

**Implementation approach:**
```
RFC 8910: DHCP option to announce portal URL
RFC 8908: JSON API for captive portal state

DHCP Option:
option captive-portal-url code 114 = text;
option captive-portal-url "http://portal.ip/";

API Endpoint:
GET /captive-portal/api/v1/{"user-portal-url": "http://..."}
```

**Note:** Low priority - most devices still use CPD. Implement when major OS support improves.

---

### Category: User Experience

#### 9. Guest Self-Service Portal (Medium Priority)

**What it is:** Allow guests to view their session info, usage, and extend time.

**Why other portals have it:**
- Transparency builds trust
- Reduce front deskcalls about WiFi issues
- Upsell opportunity for paid extensions

**Features:**
- View current session duration remaining
- View data usage (up/down)
- View connected devices
- Extend session (if voucher available)
- Disconnect devices

**Files to add:**
- `app/portal/templates/my_session.html`
- `app/portal/router.py` - Add `/my-session` endpoint

---

#### 10. Pre-Auth Landing Page / Marketing Splash (Medium Priority)

**What it is:** Customizable splash page before/during authentication.

**Why other portals have it:**
- Display hotel promotions
- Advertisements from partners
- Event announcements
- Restaurant specials

**Implementation approach:**
```
Page flow:
1. Connect to WiFi
2. Pre-auth splash (hotel info, promotions)→ "Connect" button
3. Auth page (room/voucher/social)
4. Success page
```

**Files to add:**
- `app/models.py` - Add `SplashContent` model (title, body, image)
- `app/portal/templates/pre_auth_splash.html`
- `app/admin/router.py` - CRUD for splash content

---

### Category: Multi-Property / Enterprise

#### 11. Multi-Tenant Support (Highfor Chains)

**What it is:** Single platform managing multiple hotel properties.

**Why other portals have it:**
- Chain hotels have 10-100+ properties
- Centralized management reduces IT overhead
- Cross-property guest profiles
- Chain-wide policies

**Implementation approach:**
```python
# Add property_id to all models
class Property(Base):
    __tablename__ = "properties"
    id: UUID
    name: str
    subdomain: str
    brand_config: relationship

class Session(Base):
    property_id: UUID  # Add to all tenant-scoped tables
```

**Files to modify:**
- `app/core/models.py` - Add `Property` model, add `property_id` to all models
- `app/core/database.py` - Multi-tenant query filtering
- `app/admin/router.py` - Property scoping for all endpoints

---

#### 12. Usage Reports Export (Medium Priority)

**What it is:** Export analytics data as CSV/PDF.

**Why other portals have it:**
- Accounting and auditing requirements
- Compliance with data retention laws
- Management reporting

**Implementation approach:**
```python
@router.get("/api/analytics/export")
async def export_analytics(
    format: str = Query("csv", regex="^(csv|pdf)$"),
    start_date: date, end_date: date,
    db: AsyncSession = Depends(get_db)
):
    # Fetch data
    sessions = await get_sessions_in_range(db, start_date, end_date)
    
    if format == "csv":
        return CSVResponse(generate_csv(sessions))
    else:
        return PDFResponse(generate_pdf(sessions))
```

---

### Category: Network Features

#### 13. VLAN Tagging/SSID Support (Low Priority)

**What it is:** Separate networks for different guest tiers.

**Why other portals have it:**
- Isolate premium guests from basic guests
- Separate staff network
- Floor-by-floor isolation

**Implementation approach:**
- Use 802.1Q VLAN tags on network interface
- Map VLAN to policy/bandwidth limits
- Requires switch/AP configuration

---

#### 14. High Availability / Failover (Mediumfor 24/7 Ops)

**What it is:** Redundantportal servers with automatic failover.

**Why other portals have it:**
- 99.9%+ uptime requirement
- No single point of failure
- Automatic recovery

**Implementation approach:**
- Deploy multiple portal instances behind load balancer
- Shared PostgreSQL replica
- Redis Sentinel for cache HA
- Keepalived for gateway failover

---

### Category: Data & Marketing

#### 15. Guest Session Linking (Cross-Visit Profile) (LowPriority)

**What it is:** Link sessions across multiple visits for same guest.

**Why other portals have it:**
- Loyalty recognition
- Personalized experience
- Targeted marketing

**Implementation approach:**
- Use PMS guest ID to link sessions
- Track total visits, total data usage
- Return guest recognition (welcome back message)

---

## Priority Matrix

| Feature | Business Value | Implementation Effort | Priority |
|---------|---------------|---------------------|----------|
| Social WiFi Login | High | Medium | **P0** |
| SMS/Email OTP | High | Medium | **P0** |
| Data Quota Enforcement | High | Low | **P0** |
| Multi-Property Support | High | High | **P1** |
| Click-to-Continue | Medium | Low | **P1** |
| MAC Bypass | Medium | Low | **P1** |
| Walled Garden Domains | Medium | Low | **P1** |
| Payment Gateway | Medium | Medium | **P2** |
| Guest Self-Service | Medium | Low | **P2** |
| Usage Export | Low | Low | **P2** |
| Pre-Auth Splash | Medium | Low | **P2** |
| RFC 8910/8908 | Low | Medium | **P3** |
| VLAN Support | Low | High | **P3** |
| HA/Failover | Medium | High | **P3** |

---

## Recommended Implementation Order

### Phase 1: Security & Compliance (High Priority)
1. **Data quota enforcement** - Fix existing `data_limit_mb` gap
2. **SMS OTP authentication** - Legal compliance in many regions
3. **Social WiFi (Facebook/Google/LINE)** - Marketing data collection

### Phase 2: User Experience (Medium Priority)
4. **Click-to-Continue TOS mode** - Fallback for non-guests
5. **MAC bypass list** - IoT and staff devices
6. **Walled garden domains** - Hotel website access
7. **Guest self-service portal** - View usage, manage devices

### Phase 3: Enterprise Features (If Chain Client)
8. **Multi-tenant support** - Manage multiple properties
9. **Payment gateway** - Monetization option
10. **Usage export (CSV/PDF)** - Reporting compliance

### Phase 4: Nice-to-Have (Low Priority)
11. 1. **Pre-auth splash page** - Marketing
12. **High availability setup** - 24/7 operations
13. **RFC8910/8908 support** - Future standard
14. **VLAN support** - Network isolation

---

## Competitive Landscape

| Feature | Your System | openNDS | CoovaChilli | pfSense | UniFi |
|---------|-------------|---------|--------------|---------|-------|
| Room Auth (PMS) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Voucher Auth | ✅ | ✅ | ✅ | ✅ | ✅ |
| Bandwidth Shaping | ✅ | ✅ | ✅ | ✅ | ✅ |
| Social Login | ❌ | ✅ (FAS) | ❌ | ❌ | ❌ |
| SMS OTP | ❌ | ✅ (FAS) | ❌ | ❌ | ❌ |
| RADIUS | ❌ | ✅ | ✅ | ✅ | ✅ |
| Payment Gateway | ❌ | ✅ (FAS) | ❌ | ❌ | ❌ |
| Multi-tenant | ❌ | ❌ | ❌ | ❌ | ✅ |
| Analytics | ✅ | ❌ | ❌ | ✅ | ✅ |
| Walled Garden | ❌ | ✅ | ✅ | ✅ | ✅ |
| MAC Bypass | ❌ | ✅ | ✅ | ✅ | ✅ |
| RFC 8910 | ❌ | ✅ | ❌ | ❌ | ❌ |

**Key Differentiators:**
- Your system uniquely integrates with hotel PMS systems
- Purpose-built for hospitality use case
- Already has analytics and multi-language support

**Competitive Gaps:**
- Social/SMS authentication (addressable)
- Multi-tenant support (critical for chains)
- Walled garden/MAC bypass (simple additions)

---

## References

- [Wikipedia: Captive Portal](https://en.wikipedia.org/wiki/Captive_portal)
- [openNDS Documentation](https://opennds.readthedocs.io/)
- [CoovaChilli Documentation](https://coova.github.io/)
- [RFC 8910: Captive-Portal Identification](https://www.rfc-editor.org/rfc/rfc8910)
- [RFC 8908: Captive Portal API](https://www.rfc-editor.org/rfc/rfc8908)

---

## Quick Reference: Missing Features Summary

### Must Have (P0)
- [ ] Social WiFi Login (Facebook/Google/LINE OAuth)
- [ ] SMS/Email OTP Verification
- [ ] Data Volume Quota Enforcement (fix existing gap)

### Should Have (P1)
- [ ] Multi-Property/Tenant Support
- [ ] Click-to-Continue (TOS-only) authentication mode
- [ ] MAC Address Bypass List
- [ ] Walled Garden Domain Allowlist

### Nice to Have (P2)
- [ ] Payment Gateway Integration
- [ ] Guest Self-Service Portal
- [ ] Usage Reports Export (CSV/PDF)
- [ ] Pre-Auth Marketing Splash

### Future (P3)
- [ ] RFC 8910/8908 Captive Portal API
- [ ] VLAN Tagging Support
- [ ] HighAvailability/Failover Setup
- [ ] Cross-Visit Guest Profile Linking