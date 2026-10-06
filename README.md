# Tastes Like Home

**New city, same you.** An AI agent that turns what you love back home — your spots, music, films and books — into the places you'll love where you live now, grounded in Qloo's cultural taste graph.

**Live demo:** https://tastes-like-home.onrender.com (free instance — the first load can take ~50 s to wake up)

## Why

Moving to a new city for study or work is lonely partly because none of *your* places exist yet. Generic "top 10" lists and plain LLM answers recommend what's popular, not what fits you. Tastes Like Home starts from the concrete things a person already loves and uses Qloo's cross-domain affinity data to find what people with that same taste love in the new city — and it can tell you *why* each pick fits ("because you love Chen Mapo Tofu and Haidilao").

It would not work without Qloo: the cross-domain jump (a film and a novel you love → a café you'll like), the per-pick explanations, and the local grounding all come from the taste graph.

## What it does

1. **Tell it about home.** Where you're from, where you live now, 3–8 favourites (a restaurant, a singer, a film, a TV show, a book, a brand), what you need right now, and a budget.
2. **Confirm the matches.** Each favourite is resolved to a Qloo entity (with an alternative picker). Restaurants from cities Qloo doesn't cover still work through their branches elsewhere.
3. **Get a city guide:**
   - **A taste of home** — restaurants in the new city filtered by the *cuisines of your favourite places* (read from their Qloo tags, e.g. Sichuan, hot pot, dim sum), ranked by affinity to those places.
   - **Cafés, evenings out, books & culture** — ranked by your whole taste profile, within budget.
   - **Artists and podcasts** people with your taste are into, to get your bearings.
   - **Your taste in Qloo's words** — tag-level taste analysis of your favourites, localised to the city.
   - **A first-week plan** — five days that ease homesickness first, then build a routine, using only the places Qloo returned.
   - Every pick shows **"because you love …"** from Qloo's explainability, and places are on a map.
4. **Ask your guide.** A tool-calling agent refines anything: "somewhere quiet to study on Sunday", "comfort food under $$", "where would I meet people with my taste?".

## How Qloo is used

| Feature | Qloo API |
|---|---|
| Resolve favourites to entities | `GET /search` (typed: place, artist, movie, tv_show, book, brand) |
| Home cuisines | `GET /entities` → `urn:tag:cuisine:qloo:*` tags of your favourite places |
| Recommendations in the new city | `GET /v2/insights` with `filter.type=urn:entity:place`, `filter.location.query`, `signal.interests.entities`, `filter.tags` + `operator.filter.tags=union`, `filter.price_level.max`, `filter.hours`, `filter.exclude.entities` |
| "Because you love …" | `feature.explainability=true` |
| Artists / podcasts with local flavour | `/v2/insights` with `signal.location.query` |
| Taste profile | `/v2/insights` with `filter.type=urn:tag`, `filter.parents.types=urn:entity:place` |
| Turning needs into filters | `GET /v2/tags` with `feature.semantic_search=true` |

## How the agent works

`app/agent.py` gives the model four tools over Qloo — `search_entities`, `find_tags`, `recommend`, `taste_profile`. The system prompt forbids inventing venues: every place it mentions must come from a tool result, and the explanation comes from Qloo's explainability. The first-week plan is generated from a closed list of Qloo results and validated against their ids. The model is Google Gemini through its OpenAI-compatible API (swap with `LLM_BASE_URL` / `LLM_MODEL`).

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export QLOO_API_KEY=...   # hackathon key, works only against https://hackathon.api.qloo.com
export LLM_API_KEY=...    # Google AI Studio key
.venv/bin/uvicorn app.main:app --reload
```

Open http://localhost:8000 and click **Try a sample profile**.

## Deploy

`render.yaml` deploys a free Render web service; set `QLOO_API_KEY` and `LLM_API_KEY` in the dashboard.

## License

MIT — see [LICENSE](LICENSE).
