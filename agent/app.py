"""HTTPS webhook service for Cody's three Cal.com tools (SPEC §4.1, §7).

    POST /tools/check_availability       Noel Sesto's Cal.com slots (X-Cody-Secret)
    POST /tools/book_meeting             books a discovery call with Noel Sesto (X-Cody-Secret)
    POST /tools/take_message             returns a message_id; no storage (X-Cody-Secret)
    POST /lines/resolve                  which line a call came in on + its greeting and variables
                                         (X-Cody-Secret; called by n8n's conversation-init)
    GET  /healthz

The service holds no state. Conversation-init (caller lookup) and post-call (Notion, Apollo, Slack)
run in n8n.

    uv run uvicorn agent.app:create_app --factory --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from agent import lines as line_config
from agent import log, tools
from agent.security import SECRET_HEADER, secret_ok
from agent.settings import Settings


def create_app(
    settings: Settings | None = None, *, calcom=None, line_map: line_config.LineMap | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
    log.configure()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.calcom is None:
            from agent.calcom import CalComClient

            app.state.calcom = CalComClient.from_env()
        yield

    app = FastAPI(title="Cody webhook service", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.calcom = calcom
    app.state.line_map = line_map or line_config.load_line_map()
    greeting = line_config.load_greeting()
    sections = line_config.load_prompt_sections()

    def require_secret(request: Request) -> None:
        if not secret_ok(request.headers.get(SECRET_HEADER), settings.tool_secret):
            raise HTTPException(status_code=401, detail="unauthorised")

    async def json_body(request: Request) -> dict:
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise HTTPException(status_code=400, detail="invalid JSON") from e
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="expected a JSON object")
        return body

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.post("/tools/check_availability")
    async def check_availability(request: Request):
        require_secret(request)
        return await tools.check_availability(app.state.calcom, await json_body(request))

    @app.post("/tools/book_meeting")
    async def book_meeting(request: Request):
        require_secret(request)
        return await tools.book_meeting(
            app.state.calcom, await json_body(request), app.state.line_map
        )

    @app.post("/tools/take_message")
    async def take_message(request: Request):
        require_secret(request)
        return tools.take_message(await json_body(request))

    @app.post("/lines/resolve")
    async def resolve_line(request: Request):
        require_secret(request)
        body = await json_body(request)
        result = line_config.resolve_call(
            body.get("called_number"),
            body.get("caller_id"),
            line_map=app.state.line_map,
            greeting=greeting,
            sections=sections,
        )
        log.event(
            "line_resolved",
            call_id=body.get("conversation_id"),
            line=result["line_key"],
        )
        return result

    return app
