const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ICON = { place: "🍜", artist: "🎵", movie: "🎬", tv_show: "📺", book: "📚", brand: "🛍️", podcast: "🎙️", destination: "🧭" };
const LABEL = { place: "Spot", artist: "Music", movie: "Film", tv_show: "TV", book: "Book", brand: "Brand" };

let kind = "place";
let favs = [];
let resolved = [];
let PROFILE = null;
let HISTORY = [];
let map = null, markers = null;

function toast(t) { const d = document.createElement("div"); d.className = "toast"; d.textContent = t; $("#toasts").append(d); setTimeout(() => d.remove(), 6000); }
function loading(on, text) { $("#loading").hidden = !on; if (text) $("#loadingText").textContent = text; }
async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail?.[0]?.msg || j.detail || `Request failed (${r.status})`);
  return j;
}
function md(text) {
  const lines = esc(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").split("\n");
  let h = "", list = false;
  for (const l of lines) {
    const m = l.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)/);
    if (m) { if (!list) { h += "<ul>"; list = true; } h += `<li>${m[1]}</li>`; continue; }
    if (list) { h += "</ul>"; list = false; }
    if (l.trim()) h += `<p>${l}</p>`;
  }
  return h + (list ? "</ul>" : "");
}

// ---------- step 1 ----------
$("#kinds").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  kind = b.dataset.k;
  document.querySelectorAll("#kinds button").forEach((x) => x.classList.toggle("on", x === b));
  const ph = { place: "e.g. Chen Mapo Tofu", artist: "e.g. Jay Chou", movie: "e.g. In the Mood for Love", tv_show: "e.g. Nirvana in Fire", book: "e.g. The Three-Body Problem", brand: "e.g. Uniqlo" };
  $("#favInput").placeholder = ph[kind];
  $("#favInput").focus();
});
function renderFavs() {
  $("#favs").innerHTML = favs.map((f, i) => `<li>${ICON[f.kind]} ${esc(f.name)}<button type="button" data-i="${i}" aria-label="Remove ${esc(f.name)}">×</button></li>`).join("");
}
function addFav() {
  const v = $("#favInput").value.trim();
  if (!v || favs.length >= 10) return;
  favs.push({ name: v, kind }); $("#favInput").value = ""; renderFavs();
}
$("#addFav").addEventListener("click", addFav);
$("#favInput").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addFav(); } });
$("#favs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { favs.splice(+b.dataset.i, 1); renderFavs(); } });
$("#sample").addEventListener("click", () => {
  $("#home").value = "Chengdu"; $("#city").value = "Los Angeles";
  favs = [
    { name: "Chen Mapo Tofu", kind: "place" }, { name: "Haidilao Hot Pot", kind: "brand" }, { name: "Jay Chou", kind: "artist" },
    { name: "In the Mood for Love", kind: "movie" }, { name: "The Three-Body Problem", kind: "book" }, { name: "Studio Ghibli Spirited Away", kind: "movie" },
  ];
  $("#needs").value = "I miss really spicy food, need a quiet place to study on weekends, and want to meet people who like film.";
  renderFavs();
});

$("#setup").addEventListener("submit", async (e) => {
  e.preventDefault();
  if ($("#favInput").value.trim()) addFav();
  if (!favs.length) { toast("Add at least one thing you love back home."); return; }
  loading(true, "Looking up your favourites in Qloo's taste graph…");
  try {
    resolved = await api("/api/resolve", { favorites: favs, home: $("#home").value.trim() || null });
    renderMatches();
    $("#setup").hidden = true; $("#confirm").hidden = false;
  } catch (err) { toast(err.message); }
  loading(false);
});

function renderMatches() {
  $("#matches").innerHTML = resolved.map((r, i) => {
    const m = r.matches[0];
    if (!m) return `<div class="match missing"><div class="thumb">${ICON[r.kind] || "?"}</div><div><div class="nm">${esc(r.input)}</div><div class="sub">Not found in Qloo — we'll skip it</div></div><span></span></div>`;
    const opts = r.matches.map((x, j) => `<option value="${j}">${esc(x.name)}${x.address ? " — " + esc(x.address).slice(0, 40) : x.release_year ? " (" + x.release_year + ")" : ""}</option>`).join("") + `<option value="-1">✕ Skip this one</option>`;
    return `<div class="match" data-i="${i}">
      ${m.image ? `<img src="${esc(m.image)}" alt="" loading="lazy">` : `<div class="thumb">${ICON[r.kind] || "★"}</div>`}
      <div><div class="nm">${esc(r.input)}</div><div class="sub">${LABEL[r.kind] || ""}</div>
      ${r.matches.length ? `<select data-i="${i}" aria-label="Match for ${esc(r.input)}">${opts}</select>` : ""}</div><span></span></div>`;
  }).join("");
}
$("#matches").addEventListener("change", (e) => {
  const s = e.target.closest("select"); if (!s) return;
  const r = resolved[+s.dataset.i]; const j = +s.value;
  r.pick = j;
  const row = s.closest(".match"); row.classList.toggle("missing", j < 0);
  const m = r.matches[j]; const img = row.querySelector("img, .thumb");
  if (m && img) img.outerHTML = m.image ? `<img src="${esc(m.image)}" alt="" loading="lazy">` : `<div class="thumb">${ICON[r.kind] || "★"}</div>`;
});
$("#back").addEventListener("click", () => { $("#confirm").hidden = true; $("#setup").hidden = false; });

$("#build").addEventListener("click", async () => {
  const picked = resolved.map((r) => ({ r, m: r.matches[r.pick ?? 0] })).filter((x) => x.m && (x.r.pick ?? 0) >= 0)
    .map(({ r, m }) => ({ id: m.id, name: m.name, type: m.type || r.kind, image: m.image }));
  if (!picked.length) { toast("None of your favourites were found — try adding a few more well-known ones."); return; }
  PROFILE = { home: $("#home").value.trim() || null, city: $("#city").value.trim(), needs: $("#needs").value.trim() || null,
              price_max: $("#price").value ? +$("#price").value : null, favorites: picked };
  try { localStorage.setItem("tlh-profile", JSON.stringify(PROFILE)); } catch {}
  await buildGuide();
});

// ---------- step 2 ----------
async function buildGuide() {
  loading(true, `Translating your taste to ${PROFILE.city}…`);
  try {
    const p = await api("/api/guide", PROFILE);
    renderGuide(p);
    $("#start").hidden = true; $("#guide").hidden = false;
    window.scrollTo(0, 0);
  } catch (err) { toast(err.message); }
  loading(false);
}

function placeCard(i) {
  const meta = [i.neighborhood, i.business_rating ? `★ ${i.business_rating}` : null, i.price_level ? "$".repeat(i.price_level) : null, i.release_year].filter(Boolean).join(" · ");
  const img = i.image ? `style="background-image:url('${encodeURI(i.image)}')"` : "";
  return `<article class="place">
    <div class="img" ${img}>${i.image ? "" : ICON[i.type] || "✦"}</div>
    <div class="body"><div class="nm">${esc(i.name)}</div>
      ${meta ? `<div class="meta">${esc(meta)}</div>` : ""}
      ${i.tags?.length ? `<div class="ttags">${esc(i.tags.slice(0, 3).join(" · "))}</div>` : ""}
      ${i.because?.length ? `<div class="because">${i.because.map((b) => `<span>because you love ${esc(b.name)}</span>`).join("")}</div>` : ""}
    </div></article>`;
}

function renderGuide(p) {
  $("#ppRoute").textContent = `${PROFILE.home ? PROFILE.home + " → " : ""}${PROFILE.city}`;
  $("#ppTitle").textContent = `${PROFILE.city}, to your taste`;
  $("#ppWelcome").textContent = p.plan?.welcome || `Built from ${PROFILE.favorites.map((f) => f.name).join(", ")}.`;
  $("#dna").innerHTML = p.dna.length ? p.dna.map((t) => `<span>${esc(t.name)}</span>`).join("") : `<span>${PROFILE.favorites.map((f) => esc(f.name)).join(" · ")}</span>`;
  const all = Object.fromEntries(p.sections.flatMap((s) => s.items.map((i) => [i.id, i])));
  if (p.plan?.days?.length) {
    $("#planCard").hidden = false;
    $("#plan").innerHTML = p.plan.days.map((d) => `<li><span class="day">${esc(d.day)}</span><div><div class="th">${esc(d.theme)} — ${esc(all[d.place_id]?.name || "")}</div><div class="why">${esc(d.why)}</div></div></li>`).join("");
  } else $("#planCard").hidden = true;
  $("#sections").innerHTML = p.sections.map((s) => `<section class="section"><h3>${esc(s.title)}</h3><div class="cards">${s.items.map(placeCard).join("")}</div></section>`).join("")
    || `<div class="card">Qloo didn't return places for ${esc(PROFILE.city)} yet — try a bigger nearby city name.</div>`;
  drawMap(p.sections.flatMap((s) => s.items));
  $("#log").innerHTML = "";
  HISTORY = [];
  addMsg("bot", `<p>I'm your ${esc(PROFILE.city)} guide. Ask me for anything — a study spot, a dish you miss, people to meet.</p>`);
}

function drawMap(items) {
  const pts = items.filter((i) => i.lat != null && i.lon != null);
  if (!window.L) return;
  if (!map) {
    map = L.map("map", { scrollWheelZoom: false });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap" }).addTo(map);
    markers = L.layerGroup().addTo(map);
  }
  markers.clearLayers();
  pts.forEach((i) => L.circleMarker([i.lat, i.lon], { radius: 7, color: "#c2410c", weight: 2, fillColor: "#e8b04a", fillOpacity: .9 })
    .bindPopup(`<b>${esc(i.name)}</b>${i.because?.length ? "<br>because you love " + esc(i.because.map((b) => b.name).join(", ")) : ""}`).addTo(markers));
  $(".mapcard").hidden = !pts.length;
  if (pts.length) setTimeout(() => { map.invalidateSize(); map.fitBounds(L.latLngBounds(pts.map((i) => [i.lat, i.lon])).pad(0.15)); }, 50);
}

function addMsg(role, html) {
  const d = document.createElement("div"); d.className = `msg ${role}`; d.innerHTML = html;
  $("#log").append(d); $("#log").scrollTop = $("#log").scrollHeight; return d;
}
async function ask(q) {
  HISTORY.push({ role: "user", content: q });
  addMsg("user", esc(q));
  const t = addMsg("bot", `<span class="typing">Checking the taste graph…</span>`);
  try {
    const r = await api("/api/chat", { profile: PROFILE, history: HISTORY });
    HISTORY.push({ role: "assistant", content: r.reply });
    t.innerHTML = md(r.reply) + (r.cards.length ? `<div class="minicards">${r.cards.slice(0, 6).map(placeCard).join("")}</div>` : "");
    if (r.cards.some((c) => c.lat != null)) drawMap(r.cards);
  } catch (err) { t.innerHTML = `<p>Sorry — ${esc(err.message)}</p>`; HISTORY.pop(); }
  $("#log").scrollTop = $("#log").scrollHeight;
}
$("#chips").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) ask(b.textContent); });
$("#chatForm").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#chatInput").value.trim(); if (v) { $("#chatInput").value = ""; ask(v); } });
$("#restart").addEventListener("click", () => { $("#guide").hidden = true; $("#start").hidden = false; $("#confirm").hidden = true; $("#setup").hidden = false; });

try {
  const saved = JSON.parse(localStorage.getItem("tlh-profile") || "null");
  if (saved?.city) { $("#home").value = saved.home || ""; $("#city").value = saved.city; $("#needs").value = saved.needs || ""; }
} catch {}
