"""
Main FastAPI application for FIAS Emulator.

This module provides the entry point for the FIAS Emulator, including:
- FIAS TCP server lifecycle management
- HTTP Management API
- SSE endpoint for real-time activity feed
- Page routes for HTMX dashboard
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from emulator.config import settings
from emulator.database import AsyncSessionFactory, close_db, get_db, init_db
from emulator.fias_server import FIASServer
from emulator.management import router as management_router
from emulator.models import ActivityLog, Connection, Guest, Scenario

logger = logging.getLogger(__name__)

# Global FIAS server instance
fias_server: FIASServer | None = None
fias_task: asyncio.Task | None = None

# SSE subscribers for activity feed
_sse_subscribers: list[asyncio.Queue] = []

# Templates directory (will be created in Task 5)
templates = Jinja2Templates(directory="emulator/templates")


async def broadcast_activity(activity: ActivityLog) -> None:
    """Broadcast an activity log entry to all SSE subscribers."""
    message = {
        "id": activity.id,
        "timestamp": activity.timestamp.isoformat(),
        "direction": activity.direction,
        "record_type": activity.record_type,
        "raw_content": activity.raw_content[:200] + "..." if len(activity.raw_content) > 200 else activity.raw_content,
    }

    # Put message in all subscriber queues
    dead_queues = []
    for queue in _sse_subscribers:
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            dead_queues.append(queue)

    # Remove dead queues
    for queue in dead_queues:
        _sse_subscribers.remove(queue)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    global fias_server, fias_task

    # Startup
    logger.info("Starting FIAS Emulator...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Start FIAS TCP server as background task
    fias_server = FIASServer(
        host=settings.fias_tcp_host,
        port=settings.fias_tcp_port,
    )
    fias_task = asyncio.create_task(fias_server.start())
    logger.info(f"FIAS TCP server starting on {settings.fias_tcp_host}:{settings.fias_tcp_port}")

    yield

    # Shutdown
    logger.info("Shutting down FIAS Emulator...")

    # Stop FIAS server
    if fias_server:
        await fias_server.stop()
    if fias_task:
        fias_task.cancel()
        try:
            await fias_task
        except asyncio.CancelledError:
            pass

    # Close database
    await close_db()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="FIAS Emulator",
    description="Opera FIAS TCP protocol emulator for testing captive portal PMS integration",
    version="0.1.0",
    lifespan=lifespan,
)

# Include management API router
app.include_router(management_router)


# ============ SSE Endpoint ============


@app.get("/api/activity/stream")
async def activity_stream():
    """
    Server-Sent Events endpoint for real-time activity feed.

    Clients can connect to this endpoint to receive real-time updates
    about FIAS activity (logins, queries, etc.).
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _sse_subscribers.append(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send initial connection message
            yield "event: connected\ndata: {\"message\": \"Connected to FIAS activity stream\"}\n\n"

            while True:
                try:
                    # Wait for new activity with timeout
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    import json
                    yield f"event: activity\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield "event: keepalive\ndata: {\"message\": \"keepalive\"}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _sse_subscribers.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============ Page Routes for HTMX Dashboard ============
# These routes render HTML fragments for the HTMX dashboard


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    try:
        # Gather dashboard statistics
        async with AsyncSessionFactory() as db:
            # Connection counts
            connection_count = await db.scalar(
                select(func.count()).select_from(Connection).where(Connection.is_active == True)
            ) or 0
            total_connections = await db.scalar(
                select(func.count()).select_from(Connection)
            ) or 0

            # Guest counts
            guest_count = await db.scalar(select(func.count()).select_from(Guest)) or 0
            active_guest_count = await db.scalar(
                select(func.count()).select_from(Guest).where(Guest.is_active == True)
            ) or 0

            # Scenario info
            scenario_count = await db.scalar(select(func.count()).select_from(Scenario)) or 0
            active_scenario = await db.scalar(
                select(Scenario.name).where(Scenario.is_active == True)
            )

        context = {
            "request": request,
            "tcp_port": settings.fias_tcp_port,
            "connection_count": connection_count,
            "total_connections": total_connections,
            "guest_count": guest_count,
            "active_guest_count": active_guest_count,
            "scenario_count": scenario_count,
            "active_scenario": active_scenario or "None",
        }
        return templates.TemplateResponse("dashboard.html", context)
    except Exception as e:
        logger.error(f"Error rendering dashboard: {e}")
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head><title>FIAS Emulator</title></head>
            <body>
                <h1>FIAS Emulator</h1>
                <p>Dashboard templates will be added in Task 5.</p>
                <p>Use the <a href="/docs">API Documentation</a> to manage the emulator.</p>
            </body>
            </html>
            """,
            status_code=200,
        )


@app.get("/pages/guests", response_class=HTMLResponse)
async def guests_page(request: Request):
    """Guests management page fragment."""
    try:
        return templates.TemplateResponse("pages/guests.html", {"request": request})
    except Exception:
        return HTMLResponse(content="<p>Guests page - templates coming in Task 5</p>")


@app.get("/pages/scenarios", response_class=HTMLResponse)
async def scenarios_page(request: Request):
    """Scenarios management page fragment."""
    try:
        return templates.TemplateResponse("pages/scenarios.html", {"request": request})
    except Exception:
        return HTMLResponse(content="<p>Scenarios page - templates coming in Task 5</p>")


@app.get("/pages/failure-rules", response_class=HTMLResponse)
async def failure_rules_page(request: Request):
    """Failure rules management page fragment."""
    try:
        return templates.TemplateResponse("pages/failure_rules.html", {"request": request})
    except Exception:
        return HTMLResponse(content="<p>Failure rules page - templates coming in Task 5</p>")


@app.get("/pages/connections", response_class=HTMLResponse)
async def connections_page(request: Request):
    """Connections page fragment."""
    try:
        return templates.TemplateResponse("pages/connections.html", {"request": request})
    except Exception:
        return HTMLResponse(content="<p>Connections page - templates coming in Task 5</p>")


@app.get("/pages/activity", response_class=HTMLResponse)
async def activity_page(request: Request):
    """Activity log page fragment."""
    try:
        return templates.TemplateResponse("pages/activity.html", {"request": request})
    except Exception:
        return HTMLResponse(content="<p>Activity page - templates coming in Task 5</p>")


# ============ Health Check ============


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "fias_server_running": fias_server is not None and fias_server._running,
        "tcp_port": settings.fias_tcp_port,
        "http_port": settings.http_port,
    }


def run():
    """Run the FastAPI application with uvicorn."""
    import uvicorn

    uvicorn.run(
        "emulator.main:app",
        host=settings.http_host,
        port=settings.http_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
