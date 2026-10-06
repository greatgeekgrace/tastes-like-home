import asyncio
import os
import time

import httpx

BASE = os.environ.get("QLOO_API_BASE", "https://hackathon.api.qloo.com")
KEY = os.environ.get("QLOO_API_KEY", "")

_http = httpx.AsyncClient(base_url=BASE, timeout=30, headers={"X-Api-Key": KEY})
_cache: dict = {}
TTL = 6 * 3600

TYPES = {
    "place": "urn:entity:place", "artist": "urn:entity:artist", "movie": "urn:entity:movie",
    "tv_show": "urn:entity:tv_show", "book": "urn:entity:book", "podcast": "urn:entity:podcast",
    "brand": "urn:entity:brand", "destination": "urn:entity:destination", "person": "urn:entity:person",
    "video_game": "urn:entity:video_game",
}


class QlooError(Exception):
    pass


async def get(path, params):
    params = {k: v for k, v in params.items() if v not in (None, "", [])}
    key = (path, tuple(sorted((k, str(v)) for k, v in params.items())))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    for attempt in range(3):
        r = await _http.get(path, params=params)
        if r.status_code == 429 and attempt < 2:
            await asyncio.sleep(1.5 * (attempt + 1))
            continue
        break
    if r.status_code >= 400:
        raise QlooError(f"Qloo {r.status_code} on {path}: {r.text[:300]}")
    j = r.json()
    _cache[key] = (time.time(), j)
    return j


def _img(e):
    return ((e.get("properties") or {}).get("image") or {}).get("url")


def slim(e, explain=None):
    p = e.get("properties") or {}
    loc = e.get("location") or {}
    tags = [t.get("name") for t in (e.get("tags") or []) if t.get("name")]
    out = {
        "id": e.get("entity_id") or e.get("id"),
        "name": e.get("name"),
        "type": (e.get("subtype") or (e.get("types") or [""])[0] or e.get("type") or "").replace("urn:entity:", ""),
        "image": _img(e),
        "popularity": round(e.get("popularity") or 0, 3),
        "tags": tags[:8],
    }
    if p.get("address"):
        out["address"] = p["address"]
    if loc.get("lat") is not None:
        out["lat"], out["lon"] = loc.get("lat"), loc.get("lon")
    for k in ("business_rating", "price_level", "phone", "website", "release_year", "publication_year", "description"):
        if p.get(k) not in (None, ""):
            v = p[k]
            out[k] = str(v)[:240] if k == "description" else (round(v, 1) if isinstance(v, float) else v)
    if p.get("short_description") and "description" not in out:
        out["description"] = str(p["short_description"])[:240]
    if isinstance(p.get("geocode"), dict):
        out["neighborhood"] = p["geocode"].get("name")
    if p.get("is_closed"):
        out["closed"] = True
    if explain:
        out["because"] = explain
    q = e.get("query") or {}
    if q.get("affinity") is not None:
        out["affinity"] = round(q["affinity"], 3)
    return out


async def search(query, kind=None, take=5):
    params = {"query": query, "take": take}
    if kind and kind in TYPES:
        params["types"] = TYPES[kind]
    j = await get("/search", params)
    return [slim(e) for e in j.get("results", [])]


async def entities(ids):
    if not ids:
        return []
    j = await get("/entities", {"entity_ids": ",".join(ids)})
    return j.get("results", [])


def cuisine_tags(raw_entities):
    from collections import Counter
    c = Counter()
    for e in raw_entities:
        for t in e.get("tags") or []:
            tid = t.get("id") or t.get("tag_id") or ""
            if tid.startswith("urn:tag:cuisine:qloo:") and not tid.endswith((":asian", ":international")):
                c[tid] += 1
    return [t for t, _ in c.most_common(5)]


async def find_tags(query, parent_kind=None, take=6):
    params = {"filter.query": query, "feature.semantic_search": "true", "take": take}
    if parent_kind in TYPES:
        params["filter.parents.types"] = TYPES[parent_kind]
    j = await get("/v2/tags", params)
    tags = j.get("results", {}).get("tags", []) if isinstance(j.get("results"), dict) else j.get("results", [])
    return [{"id": t.get("id") or t.get("tag_id"), "name": t.get("name"), "type": t.get("subtype") or t.get("type")} for t in tags]


def _explain(e, names):
    ex = (e.get("query") or {}).get("explainability") or {}
    rows = ex.get("signal.interests.entities") or ex.get("entities") or []
    if isinstance(rows, dict):
        rows = [{"entity_id": k, "score": v} for k, v in rows.items()]
    out = []
    for r in rows:
        eid = r.get("entity_id") or r.get("id")
        if eid in names and (r.get("score") or 0) >= 0.1:
            out.append({"name": names[eid], "score": round(r.get("score") or 0, 2)})
    return sorted(out, key=lambda x: -x["score"])[:3]


async def recommend(kind, *, signal_ids=(), names=None, city=None, tag_ids=(), take=8, price_max=None,
                    open_day=None, min_rating=None, exclude_ids=()):
    names = names or {}
    params = {
        "filter.type": TYPES[kind],
        "take": take,
        "feature.explainability": "true",
    }
    if signal_ids:
        params["signal.interests.entities"] = ",".join(signal_ids)
    if city:
        if kind in ("place", "destination"):
            params["filter.location.query"] = city
        else:
            params["signal.location.query"] = city
    if tag_ids:
        params["filter.tags"] = ",".join(tag_ids)
        params["operator.filter.tags"] = "union"
    if price_max and kind == "place":
        params["filter.price_level.max"] = int(price_max)
    if open_day and kind == "place":
        params["filter.hours"] = open_day
    if min_rating and kind == "place":
        params["filter.properties.business_rating.min"] = float(min_rating)
    if exclude_ids:
        params["filter.exclude.entities"] = ",".join(exclude_ids)
    j = await get("/v2/insights", params)
    ents = j.get("results", {}).get("entities", [])
    return [slim(e, _explain(e, names)) for e in ents]


async def taste_dna(signal_ids, parent_kind="place", city=None, take=12):
    params = {"filter.type": "urn:tag", "signal.interests.entities": ",".join(signal_ids), "take": take}
    if parent_kind in TYPES:
        params["filter.parents.types"] = TYPES[parent_kind]
    if city:
        params["signal.location.query"] = city
    j = await get("/v2/insights", params)
    tags = j.get("results", {}).get("tags", [])
    return [{"id": t.get("tag_id") or t.get("id"), "name": t.get("name"), "type": (t.get("subtype") or "").split(":")[-1],
             "affinity": round((t.get("query") or {}).get("affinity") or 0, 3)} for t in tags]
