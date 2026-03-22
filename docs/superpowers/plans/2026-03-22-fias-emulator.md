# FIAS Emulator Implementation Plan

> **for agentic workers:** Required sub-skill: use superpowers:subagent-driven-development
**Goal:** Build Opera FIAS emulator as standalone tool with realistic FIAS server and web dashboard for development/testing

**Architecture:** Monolithic FastAPI app with TCP server + HTTP management UI + SQLite database
**Tech Stack:** Python 3.12, FastAPI, uvicorn, HTMX, Tailwind, Jinja2, SQLAlchemy, aiosqlite

---
```
## Task Structure

```
### Task 1: Project Setup
- [ ] Create `tools/fias-emulator/` directory
- [ ] Create `pyproject.toml` with dependencies
- [ ] Create virtualenv
- [ ] Initialize git repository
- [ ] Commit: "chore: init fias-emulator project structure"

### Task 2: Database Layer
- [ ] Create `emulator/database.py` - SQLAlchemy async engine setup
- [ ] Create `emulator/models.py` - all database models
- [ ] Create initial migration
- [ ] Test database connection
- [ ] Commit: "feat: add database layer"

### Task 3: FIAS TCP Server
- [ ] Create `emulator/fias_server.py` - TCP server implementation
  [ ] Implement FIAS protocol handlers (LR, KA, GIQ, DRQ, LD)
- [ ] Add failure injection logic
- [ ] Test FIAS server with mock connections
- [ ] Commit: "feat: add FIAS TCP server"

### Task 4: Management API
- [ ] Create `emulator/management.py` - FastAPI router with REST endpoints
- [ ] Create Pydantic schemas for request/response validation
- [ ] Test management API endpoints
- [ ] Commit: "feat: add management API"

### Task 5: HTMX Dashboard
- [ ] Create base template `emulator/templates/base.html`
- [ ] Create dashboard page `emulator/templates/dashboard.html`
- [ ] Create guests page `emulator/templates/guests.html`
- [ ] Create scenarios page `emulator/templates/scenarios.html`
- [ ] Create failures page `emulator/templates/failures.html`
- [ ] Create activity page `emulator/templates/activity.html`
- [ ] Test HTMX endpoints manually
- [ ] Commit: "feat: add HTMX dashboard"

### Task 6: Pre-configured Scenarios
- [ ] Create seed data script to populate database
- [ ] Add happy_path scenario (5 guests, no failures)
- [ ] Add connection_failures scenario (3 guests, 3 failures)
- [ ] Add protocol_errors scenario (2 guests, 4 failures)
- [ ] Add edge_cases scenario (8 guests, no failures)
- [ ] Add business_logic scenario (4 guests, 2 failures)
- [ ] Test scenario loading
- [ ] Commit: "feat: add pre-configured scenarios"

### Task 7: Dev Script Integration
- [ ] Create `scripts/dev-with-emulator.sh`
- [ ] Test script starts both services
- [ ] Update main project `.env.example`
- [ ] Commit: "feat: add dev script integration"
### Task 8: Integration Tests
- [ ] Create end-to-end test connecting main project to emulator
- [ ] Test happy_path scenario
- [ ] Test connection_failures scenario
- [ ] Test protocol_errors scenario
- [ ] Commit: "feat: add integration tests"
### Task 9: Documentation
- [ ] Create `tools/fias-emulator/README.md`
- [ ] Document usage instructions
- [ ] Document API reference
- [ ] Commit: "docs: add fias-emulator README"
```

## Execution Approach
**Subagent-driven** - Each task is independent and can be worked on by separate agents in parallel.
- **Fresh subagent per task** - No shared state between tasks
- **Review checkpoints** - After tasks 3, 4, 5, 6 complete, pause for review
- **Final integration** - Tasks 7, 8, 9 run after all others complete
