import asyncio
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, llm, qloo

STATIC = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(title="Tastes Like Home")
HITS = defaultdict(deque)
LIMIT = int(os.environ.get("REQUESTS_PER_HOUR", "80"))


def limit(request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    q, now = HITS[ip], time.time()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= LIMIT:
        raise HTTPException(429, "Demo rate limit reached — please try again later.")
    q.append(now)


class Fav(BaseModel):
    name: str = Field(max_length=120)
    kind: str | None = None


class ResolveIn(BaseModel):
    favorites: list[Fav] = Field(max_length=12)
    home: str | None = None


class Profile(BaseModel):
    home: str | None = Field(default=None, max_length=80)
    city: str = Field(max_length=80)
    needs: str | None = Field(default=None, max_length=400)
    price_max: int | None = None
    favorites: list[dict] = Field(max_length=12)


class ChatIn(BaseModel):
    profile: Profile
    history: list[dict]


@app.get("/api/health")
async def health():
    return {"ok": True, "model": llm.MODEL, "qloo": qloo.BASE}


@app.post("/api/resolve")
async def resolve(body: ResolveIn, request: Request):
    limit(request)

    async def one(f: Fav):
        q = f.name
        if f.kind == "place" and body.home and body.home.lower() not in q.lower():
            q = f"{q} {body.home}"
        try:
            hits = await qloo.search(q, f.kind, take=4)
            if not hits and q != f.name:
                hits = await qloo.search(f.name, f.kind, take=4)
        except qloo.QlooError:
            hits = []
        return {"input": f.name, "kind": f.kind, "matches": hits}

    return await asyncio.gather(*[one(f) for f in body.favorites])


@app.post("/api/guide")
async def guide(body: Profile, request: Request):
    limit(request)
    if not any(f.get("id") for f in body.favorites):
        raise HTTPException(400, "Add at least one favourite we could find.")
    return await agent.build_guide(body.model_dump())


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    limit(request)
    return await agent.run_chat(body.profile.model_dump(), body.history)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")
