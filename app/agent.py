import asyncio
import json
from datetime import date

from . import llm, qloo

CATEGORIES = [
    ("eat", "Restaurants that taste like home", "restaurant"),
    ("cafe", "Cafés to make your own", "cafe coffee shop"),
    ("night", "Evenings out", "bar cocktail lounge"),
    ("culture", "Culture & browsing", "bookstore museum gallery"),
]
_cat_tags: dict = {}


async def category_tags(query):
    if query not in _cat_tags:
        try:
            tags = await qloo.find_tags(query, "place", take=6)
        except qloo.QlooError:
            tags = []
        _cat_tags[query] = [t["id"] for t in tags if t.get("id") and ":place" in t["id"]][:4]
    return _cat_tags[query]


def _profile(p):
    favs = [f for f in p.get("favorites", []) if f.get("id")]
    return favs, [f["id"] for f in favs], {f["id"]: f["name"] for f in favs}


async def build_guide(profile):
    favs, ids, names = _profile(profile)
    city = profile["city"]
    exclude = [f["id"] for f in favs if f.get("type") == "place"]

    async def section(key, title, q):
        tags = await category_tags(q)
        try:
            items = await qloo.recommend("place", signal_ids=ids, names=names, city=city, tag_ids=tags, take=6,
                                         price_max=profile.get("price_max"), exclude_ids=exclude)
        except qloo.QlooError:
            items = []
        return {"key": key, "title": title, "items": [i for i in items if not i.get("closed")][:5]}

    async def culture(kind, title):
        try:
            items = await qloo.recommend(kind, signal_ids=ids, names=names, city=city, take=5)
        except qloo.QlooError:
            items = []
        return {"key": kind, "title": title, "items": items}

    async def dna():
        try:
            return await qloo.taste_dna(ids, "place", city=city, take=12)
        except qloo.QlooError:
            return []

    results = await asyncio.gather(
        dna(),
        *[section(k, t, q) for k, t, q in CATEGORIES],
        culture("artist", "Artists people like you are playing here"),
        culture("podcast", "Podcasts to get your bearings"),
    )
    guide = {"dna": results[0], "sections": [s for s in results[1:] if s["items"]]}
    guide["plan"] = await first_week(profile, guide)
    return guide


async def first_week(profile, guide):
    favs, _, _ = _profile(profile)
    menu = [{"id": i["id"], "name": i["name"], "section": s["title"], "because": [b["name"] for b in i.get("because", [])],
             "neighborhood": i.get("neighborhood"), "tags": i.get("tags", [])[:4]}
            for s in guide["sections"] if s["key"] in ("eat", "cafe", "night", "culture") for i in s["items"]]
    if not menu:
        return None
    prompt = f"""Someone just moved from {profile.get('home') or 'abroad'} to {profile['city']}.
They love: {', '.join(f"{f['name']} ({f.get('type')})" for f in favs)}.
What they said they need: {profile.get('needs') or 'feel at home, meet people, find their spots'}.
Their taste profile tags: {', '.join(t['name'] for t in guide['dna'][:10])}.
Candidate places (only use these, by id): {json.dumps(menu)}

Write a gentle first-week plan that eases homesickness first and builds a routine. Return JSON:
{{"welcome": "2 sentences, warm, specific to their tastes",
  "days": [{{"day": "Day 1", "theme": "3-5 words", "place_id": "...", "why": "one sentence linking to what they love back home"}}]}}
Use 5 days, each a different place, mix sections. Output JSON only."""
    msg = await llm.chat([{"role": "system", "content": "You are a thoughtful relocation concierge. Output strict JSON."},
                          {"role": "user", "content": prompt}], temperature=0.6)
    txt = (msg.get("content") or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        plan = json.loads(txt)
    except json.JSONDecodeError:
        return None
    ok = {m["id"] for m in menu}
    plan["days"] = [d for d in plan.get("days", []) if d.get("place_id") in ok]
    return plan


TOOLS = [
    {"type": "function", "function": {
        "name": "search_entities",
        "description": "Look up real-world things in Qloo's taste graph by name (a restaurant back home, a singer, a film, a book, a brand...). Returns Qloo entity ids you can use as taste signals.",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string"},
            "kind": {"type": "string", "enum": list(qloo.TYPES)}}}}},
    {"type": "function", "function": {
        "name": "find_tags",
        "description": "Turn a plain-language need into Qloo tag ids (cuisine, vibe, amenity, genre). E.g. 'quiet cafe with wifi', 'Sichuan', 'late night', 'vegetarian', 'live jazz'.",
        "parameters": {"type": "object", "required": ["query"], "properties": {
            "query": {"type": "string"},
            "for_kind": {"type": "string", "enum": list(qloo.TYPES)}}}}},
    {"type": "function", "function": {
        "name": "recommend",
        "description": "Get taste-matched recommendations from Qloo. Uses the user's favourites as signals unless you pass other ids. For places, results are restricted to the city; each result says which favourites drove it ('because').",
        "parameters": {"type": "object", "required": ["kind"], "properties": {
            "kind": {"type": "string", "enum": list(qloo.TYPES)},
            "tag_ids": {"type": "array", "items": {"type": "string"}, "description": "From find_tags"},
            "extra_signal_ids": {"type": "array", "items": {"type": "string"}, "description": "Extra entity ids to steer taste"},
            "only_signal_ids": {"type": "array", "items": {"type": "string"}, "description": "Use ONLY these ids as signals (e.g. 'places like X')"},
            "city": {"type": "string", "description": "Defaults to the user's new city"},
            "price_max": {"type": "integer", "description": "1-4"},
            "open_day": {"type": "string", "description": "e.g. Sunday"},
            "take": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "taste_profile",
        "description": "Describe the user's taste as Qloo tags (what their favourites have in common), optionally localised to the city.",
        "parameters": {"type": "object", "properties": {
            "for_kind": {"type": "string", "enum": list(qloo.TYPES)}}}}},
]

SYSTEM = """You are Tastes Like Home, a relocation companion for people who just moved to a new city (students, new hires, anyone starting over somewhere new).
Today is {today}. The user moved from {home} to {city}. Their favourites from home (Qloo ids): {favs}.
What they told you they need: {needs}.

You ground every suggestion in Qloo's taste graph via tools — never invent venues, addresses or ratings. If Qloo returns nothing, say so and try a broader query (fewer tags, different wording).
Explain picks through the user's own tastes ("because you love …" comes from the tool's 'because' field). Think about what a newcomer actually needs: familiar comfort first, then routine spots near daily life, then ways to meet people with similar tastes.
Keep replies short: a sentence of framing, then up to 5 picks as bullets with **name** — neighbourhood — one-line why. The app shows cards with details, so don't repeat addresses."""


async def run_chat(profile, history, max_steps=6):
    favs, ids, names = _profile(profile)
    msgs = [{"role": "system", "content": SYSTEM.format(
        today=date.today().isoformat(), home=profile.get("home") or "abroad", city=profile["city"],
        favs=json.dumps([{"id": f["id"], "name": f["name"], "type": f.get("type")} for f in favs]),
        needs=profile.get("needs") or "not stated")}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in history[-16:] if m.get("role") in ("user", "assistant")]
    cards, trace = [], []
    for _ in range(max_steps):
        msg = await llm.chat(msgs, tools=TOOLS)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"reply": msg.get("content") or "", "cards": cards[:12], "trace": trace}
        msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            name = c["function"]["name"]
            try:
                a = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                a = {}
            try:
                if name == "search_entities":
                    res = await qloo.search(a["query"], a.get("kind"), take=5)
                elif name == "find_tags":
                    res = await qloo.find_tags(a["query"], a.get("for_kind"), take=6)
                elif name == "recommend":
                    sig = a.get("only_signal_ids") or (ids + (a.get("extra_signal_ids") or []))
                    nm = dict(names)
                    res = await qloo.recommend(a["kind"], signal_ids=sig, names=nm, city=a.get("city") or profile["city"],
                                               tag_ids=a.get("tag_ids") or [], take=min(int(a.get("take") or 6), 10),
                                               price_max=a.get("price_max"), open_day=a.get("open_day"))
                    res = [r for r in res if not r.get("closed")]
                    cards.extend(res)
                elif name == "taste_profile":
                    res = await qloo.taste_dna(ids, a.get("for_kind") or "place", city=profile["city"])
                else:
                    res = {"error": "unknown tool"}
            except (qloo.QlooError, KeyError) as e:
                res = {"error": str(e)}
            trace.append({"tool": name, "args": a, "n": len(res) if isinstance(res, list) else 0})
            msgs.append({"role": "tool", "tool_call_id": c.get("id", name), "name": name, "content": json.dumps(res)[:20000]})
    return {"reply": "Here's what I found so far.", "cards": cards[:12], "trace": trace}
