from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.database import engine
from app.portal.router import router as portal_router
from app.admin.router import router as admin_router
from app.pms.webhook_router import router as webhook_router
from app.network.scheduler import start_scheduler, stop_scheduler
from app.network.tc import ensure_ifb_ready
from app.network.https_redirect import start_https_redirect_server
from app.network.dns_proxy import start_auth_dns_proxy

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        ensure_ifb_ready()
    except Exception:
        pass
    # HTTPS redirect server — intercepts port 443 for unauthenticated clients
    _https_server = None
    try:
        _https_server = await start_https_redirect_server(settings.PORTAL_IP, settings.PORTAL_PORT)
    except Exception as _e:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"HTTPS redirect server failed to start: {_e}")
    # Auth DNS proxy — handles 'logout' resolution for authenticated (dns_bypass) clients
    _dns_proxy = None
    try:
        _dns_proxy = await start_auth_dns_proxy(settings.PORTAL_IP, settings.DNS_UPSTREAM_IP)
    except Exception as _e:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"Auth DNS proxy failed to start: {_e}")
    # Restore dnsmasq config from DB
    try:
        from app.core.database import AsyncSessionFactory
        from app.core.models import DhcpConfig
        from app.network import dnsmasq as _dnsmasq
        from sqlalchemy import select as _select
        async with AsyncSessionFactory() as _db:
            _result = await _db.execute(_select(DhcpConfig))
            _dhcp = _result.scalar_one_or_none()
            if _dhcp and _dhcp.enabled:
                _dnsmasq.write_config(_dhcp)
                _dnsmasq.reload_dnsmasq()
    except Exception as _e:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"dnsmasq startup restore failed: {_e}")
    # Load PMS adapter from DB on startup
    try:
        from app.core.database import AsyncSessionFactory
        from app.pms.factory import load_adapter as _load_adapter
        async with AsyncSessionFactory() as _db:
            await _load_adapter(_db)
    except Exception as _e:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"PMS adapter startup load failed: {_e}")
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    if _dns_proxy:
        _dns_proxy.close()
    if _https_server:
        _https_server.close()
        await _https_server.wait_closed()
    await app.state.redis.aclose()
    await engine.dispose()

app = FastAPI(title="Hotel WiFi Captive Portal", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(admin_router)
app.include_router(webhook_router)
app.include_router(portal_router)

@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    if "text/html" in request.headers.get("accept", ""):
        request.session["flash"] = "Access denied: superadmin required"
        return RedirectResponse(url="/admin/", status_code=302)
    return JSONResponse({"error": "forbidden"}, status_code=403)
