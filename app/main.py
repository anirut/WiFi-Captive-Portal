from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.database import engine
from app.portal.router import router as portal_router
from app.admin.router import router as admin_router
from app.pms.webhook_router import router as webhook_router
from app.network.scheduler import start_scheduler, stop_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    await app.state.redis.aclose()
    await engine.dispose()

app = FastAPI(title="Hotel WiFi Captive Portal", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(portal_router)
app.include_router(admin_router)
app.include_router(webhook_router)

@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    if "text/html" in request.headers.get("accept", ""):
        request.session["flash"] = "Access denied: superadmin required"
        return RedirectResponse(url="/admin/", status_code=302)
    return JSONResponse({"error": "forbidden"}, status_code=403)
