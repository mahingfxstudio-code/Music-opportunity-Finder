
import re
import time
from urllib.parse import quote_plus, urlparse

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

try:
    import yt_dlp
except Exception:
    yt_dlp = None

VERSION = "V2.1"
APP_TITLE = f"🎵 Music Opportunity Finder {VERSION}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36"

st.set_page_config(page_title=APP_TITLE, page_icon="🎵", layout="wide")

# ---------- Styling: V1-inspired UI ----------
st.markdown("""
<style>
.stApp { background: #0b0d12; color: #f5f7fb; }
section[data-testid="stSidebar"] { background:#171923; }
.block-container { max-width: 1180px; padding-top: 1.2rem; }
.v1hero {
    background: linear-gradient(110deg,#0d1422,#211d48);
    border:1px solid #293653; border-radius:0 0 28px 28px;
    padding:25px 30px; margin-bottom:24px;
}
.v1hero h1 { margin:0; font-size:38px; font-weight:800; }
.v1hero .v { color:#8c69ff; }
.sub { color:#b9c1d4; margin-top:12px; }
.bigbtn button {
    width:100%; height:52px; background:#ff4d52 !important;
    color:white !important; border:0 !important; border-radius:9px !important;
    font-weight:800 !important;
}
.card {
    background:#101620; border:1px solid #2c3850; border-radius:13px;
    padding:17px; min-height:105px;
}
.card .n { font-size:32px; font-weight:800; margin-top:4px; }
.smallmuted { color:#8f99ad; font-size:13px; }
.resultbox {
    background:#0f141c; border:1px solid #303b51; border-radius:12px;
    padding:15px; margin:9px 0;
}
.badge { display:inline-block; padding:4px 9px; border-radius:12px; font-size:12px; font-weight:800; }
.dist { background:#193d2b; color:#6ff0a3; }
.notdist { background:#4b2427; color:#ff9ba0; }
.linkrow a { margin-right:10px; }
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="v1hero">
  <h1>🎵 Music Opportunity Finder <span class="v">{VERSION}</span></h1>
  <div class="sub">Viral • Old • High-View • Artist • Channel • Lyrics • Public Catalog Research</div>
</div>
""", unsafe_allow_html=True)

# ---------- Helpers ----------
@st.cache_data(ttl=900, show_spinner=False)
def yt_search(query, limit=20):
    """YouTube public search through yt-dlp; no API key required."""
    if not yt_dlp:
        return []
    opts = {
        "quiet": True, "skip_download": True, "extract_flat": True,
        "noplaylist": False, "playlistend": max(1, min(int(limit), 50)),
        "socket_timeout": 12, "retries": 1,
        "user_agent": UA,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        entries = (info or {}).get("entries") or []
        out = []
        for e in entries:
            if not e:
                continue
            vid = e.get("id") or ""
            url = e.get("webpage_url") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")
            out.append({
                "title": e.get("title") or "",
                "channel": e.get("channel") or e.get("uploader") or "",
                "channel_id": e.get("channel_id") or "",
                "views": int(e.get("view_count") or 0),
                "published": e.get("upload_date") or "",
                "url": url,
                "video_id": vid,
            })
        return out
    except Exception:
        return []

@st.cache_data(ttl=900, show_spinner=False)
def web_search(query, limit=8):
    """Public DuckDuckGo HTML search; no API key required."""
    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": UA},
            timeout=12,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rows = []
        for a in soup.select("a.result__a")[:limit]:
            href = a.get("href", "")
            title = a.get_text(" ", strip=True)
            parent = a.find_parent(class_="result")
            snippet = ""
            if parent:
                s = parent.select_one(".result__snippet")
                snippet = s.get_text(" ", strip=True) if s else ""
            rows.append({"title": title, "url": href, "snippet": snippet})
        return rows
    except Exception:
        return []

def fmt_views(n):
    try:
        n = int(n)
    except Exception:
        return "—"
    if n >= 1_000_000_000: return f"{n/1e9:.1f}B"
    if n >= 1_000_000: return f"{n/1e6:.1f}M"
    if n >= 1_000: return f"{n/1e3:.1f}K"
    return str(n)

def normalize(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

def match_score(title, artist, song):
    t, a, s = normalize(title), normalize(artist), normalize(song)
    score = 0
    if s and s in t: score += 60
    if a and a in t: score += 35
    if s and a:
        parts = set(s.split()) & set(t.split())
        score += min(5, len(parts))
    return score

@st.cache_data(ttl=1800, show_spinner=False)
def apple_search(title, artist):
    """Apple/iTunes public catalog lookup. No API key required."""
    try:
        q = f"{title} {artist}".strip()
        r = requests.get(
            "https://itunes.apple.com/search",
            params={"term": q, "media": "music", "entity": "song", "limit": 10, "country": "US"},
            headers={"User-Agent": UA}, timeout=10
        )
        r.raise_for_status()
        data = r.json()
        wanted_t = normalize(title)
        wanted_a = normalize(artist)
        best = None
        best_score = 0
        for item in data.get("results", []):
            ts = normalize(item.get("trackName",""))
            aa = normalize(item.get("artistName",""))
            score = 0
            if wanted_t and (wanted_t == ts or wanted_t in ts or ts in wanted_t): score += 70
            if wanted_a and (wanted_a == aa or wanted_a in aa or aa in wanted_a): score += 30
            if score > best_score:
                best_score, best = score, item
        if best_score >= 80:
            return {"state":"MATCH", "detail":"MATCH FOUND", "url":best.get("trackViewUrl","")}
        return {"state":"NO_MATCH", "detail":"NO MATCH", "url":""}
    except Exception as e:
        return {"state":"ERROR", "detail":"CHECK FAILED", "url":""}

@st.cache_data(ttl=1800, show_spinner=False)
def spotify_search_public(title, artist):
    """
    Optional Spotify Web API check.
    If credentials are not configured, do NOT guess or mark as no match.
    """
    client_id = st.secrets.get("SPOTIFY_CLIENT_ID", "")
    client_secret = st.secrets.get("SPOTIFY_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return {"state":"UNVERIFIED", "detail":"NOT CHECKED (API key not configured)", "url":""}
    try:
        token = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={
                "Authorization": "Basic " + base64.b64encode(
                    f"{client_id}:{client_secret}".encode()
                ).decode(),
                "Content-Type":"application/x-www-form-urlencoded",
            },
            data={"grant_type":"client_credentials"},
            timeout=10
        )
        token.raise_for_status()
        access = token.json()["access_token"]
        r = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization":f"Bearer {access}"},
            params={"q":f'track:"{title}" artist:"{artist}"', "type":"track", "limit":10, "market":"US"},
            timeout=10
        )
        r.raise_for_status()
        items = r.json().get("tracks",{}).get("items",[])
        wanted_t, wanted_a = normalize(title), normalize(artist)
        for item in items:
            tt = normalize(item.get("name",""))
            names = [normalize(x.get("name","")) for x in item.get("artists",[])]
            if (wanted_t == tt or wanted_t in tt or tt in wanted_t) and any(
                wanted_a == a or wanted_a in a or a in wanted_a for a in names
            ):
                return {"state":"MATCH","detail":"MATCH FOUND","url":item.get("external_urls",{}).get("spotify","")}
        return {"state":"NO_MATCH","detail":"NO MATCH","url":""}
    except Exception:
        return {"state":"ERROR","detail":"CHECK FAILED","url":""}

@st.cache_data(ttl=1800, show_spinner=False)
def youtube_music_public(title, artist):
    """
    Public web evidence for YouTube Music. This is deliberately conservative:
    if the public page cannot be verified, return UNVERIFIED rather than
    incorrectly saying the song is not distributed.
    """
    q = f'site:music.youtube.com "{title}" "{artist}"'
    hits = web_search(q, 6)
    wanted_t, wanted_a = normalize(title), normalize(artist)
    for h in hits:
        text = normalize(h.get("title","") + " " + h.get("snippet",""))
        if wanted_t and wanted_t in text and (not wanted_a or wanted_a in text):
            return {"state":"MATCH","detail":"MATCH FOUND","url":h["url"]}
    if hits:
        return {"state":"NO_MATCH","detail":"NO MATCH IN PUBLIC SEARCH","url":""}
    return {"state":"UNVERIFIED","detail":"CHECK FAILED","url":""}

def distribution_check(title, artist):
    """
    Conservative catalog checker:
    - DISTRIBUTED only when at least one reliable catalog match is found.
    - NOT DISTRIBUTION only when all enabled checks completed successfully and
      none found a match.
    - Otherwise CHECK UNVERIFIED, never a guessed negative.
    """
    apple = apple_search(title, artist)
    spotify = spotify_search_public(title, artist)
    ytm = youtube_music_public(title, artist)

    checks = [apple, spotify, ytm]
    positive = [x for x in checks if x["state"] == "MATCH"]
    enabled = [x for x in checks if x["state"] != "UNVERIFIED"]
    failures = [x for x in checks if x["state"] == "ERROR"]
    if positive:
        status = "DISTRIBUTED / MATCH FOUND"
    elif enabled and len(failures) == 0 and len(enabled) == len(checks):
        status = "NOT DISTRIBUTION"
    else:
        status = "CHECK UNVERIFIED"

    return {
        "status": status,
        "apple": apple["detail"],
        "spotify": spotify["detail"],
        "youtube_music": ytm["detail"],
        "apple_url": apple.get("url",""),
        "spotify_url": spotify.get("url",""),
        "youtube_music_url": ytm.get("url",""),
        "evidence": [],
    }

def render_result(row, check=True):
    title = row.get("title","")
    artist = row.get("artist") or row.get("channel") or ""
    views = row.get("views", 0)
    url = row.get("url","")
    if check:
        c = distribution_check(title, artist)
    else:
        c = {"status":"NOT CHECKED","apple":"—","spotify":"—","youtube_music":"—","evidence":[]}
    badge_cls = "dist" if c["status"].startswith("DISTRIBUTED") else "notdist"
    st.markdown(f"""
    <div class="resultbox">
      <div><b>🎵 {title}</b> <span class="badge {badge_cls}">{c["status"]}</span></div>
      <div class="smallmuted">Artist: {artist} • Views: {fmt_views(views)}</div>
      <div style="margin-top:7px">
        Catalog: <b>{c["status"]}</b> &nbsp;|&nbsp;
        Apple: <b>{c["apple"]}</b> &nbsp;|&nbsp;
        Spotify: <b>{c["spotify"]}</b> &nbsp;|&nbsp;
        YouTube Music: <b>{c["youtube_music"]}</b>
      </div>
      <div class="linkrow" style="margin-top:9px">
        <a href="{url}" target="_blank">▶ YouTube</a>
        <a href="https://www.google.com/search?q={quote_plus(title+' '+artist+' lyrics')}" target="_blank">📝 Lyrics Search</a>
        <a href="https://www.google.com/search?q={quote_plus(title+' '+artist)}" target="_blank">🔎 Web Search</a>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ---------- Sidebar ----------
st.sidebar.markdown("## 🎯 Research Center")
mode = st.sidebar.radio(
    "Research mode",
    ["🔥 Song Discovery", "🔎 Artist Finder", "📺 Channel Scanner", "📝 Lyrics Finder", "📚 History"],
    index=0,
)
st.sidebar.markdown("---")

if mode == "🔥 Song Discovery":
    song = st.sidebar.text_input("Song name (optional)", placeholder="e.g. Kahani Suno")
    artist = st.sidebar.text_input("Singer / Artist (optional)", placeholder="e.g. Kaifi Khalil")
    keyword = st.sidebar.text_input("Keyword / genre / language", placeholder="Any keyword")
    results_n = st.sidebar.number_input("Results", min_value=5, max_value=50, value=30, step=5)
    min_views = st.sidebar.number_input("Minimum views", min_value=0, value=100000, step=10000)
    max_views = st.sidebar.number_input("Maximum views (0 = unlimited)", min_value=0, value=0, step=10000)
    year = st.sidebar.number_input("Year / Old-song cutoff (0 = Any Year)", min_value=0, max_value=2100, value=0, step=1)
    noise = st.sidebar.checkbox("🚫 Hide remix/cover/reaction/movie noise", True)
    parallel = st.sidebar.slider("⚡ Parallel research", 1, 8, 4)
    st.sidebar.caption("YouTube + Apple checks work without keys. Spotify is checked only when optional Spotify credentials are configured; otherwise it is shown as UNVERIFIED, never as NOT DISTRIBUTION.")

    st.markdown("## 🔎 Viral Song Discovery")
    if song or artist:
        search_text = f"{song} {artist}".strip()
        hint = "Exact Song + Singer/Artist matching"
    else:
        search_text = keyword
        hint = "Keyword / genre / language search"
    st.caption(hint)
    st.markdown('<div class="bigbtn">', unsafe_allow_html=True)
    go = st.button("🚀 FAST FIND & RESEARCH SONGS", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if go:
        if not search_text.strip():
            st.warning("Enter a song name + artist, or a keyword.")
            st.stop()
        queries = []
        if song and artist:
            queries = [f'"{song}" "{artist}"', f'{song} {artist} official', f'{song} {artist} song']
        elif song:
            queries = [song, f'{song} official song']
        else:
            queries = [keyword, f'{keyword} official song', f'{keyword} music']
        raw = []
        for q in queries[:3]:
            raw.extend(yt_search(q, int(results_n)))
        seen = set(); rows=[]
        for x in raw:
            key = x["video_id"] or x["url"]
            if key in seen: continue
            seen.add(key)
            if x["views"] < min_views: continue
            if max_views and x["views"] > max_views: continue
            if noise and any(k in x["title"].lower() for k in ["reaction","cover","remix","lyrics video","trailer"]):
                continue
            if song and artist:
                x["score"] = match_score(x["title"], x["channel"], song)
            else:
                x["score"] = 0
            x["artist"] = x["channel"]
            rows.append(x)
        rows.sort(key=lambda z: (z["score"], z["views"]), reverse=True)
        rows = rows[:int(results_n)]

        # Fast first: show YouTube candidates, then optional catalog checks
        c1 = sum(1 for _ in rows)
        checks = []
        progress = st.progress(0)
        for i, row in enumerate(rows):
            try:
                checks.append(distribution_check(row["title"], row["artist"]))
            except Exception:
                checks.append({"status":"NOT CHECKED","apple":"—","spotify":"—","youtube_music":"—","evidence":[]})
            progress.progress((i+1)/max(1,len(rows)))
        progress.empty()

        distributed = sum(c["status"].startswith("DISTRIBUTED") for c in checks)
        notdist = len(rows)-distributed
        million = sum(r["views"] >= 1_000_000 for r in rows)

        cols = st.columns(4)
        for col, label, value in zip(cols, ["🎵 Songs","📁 Distributed","📁 Not Distribution","🔥 1M+"], [len(rows),distributed,notdist,million]):
            col.markdown(f'<div class="card"><div>{label}</div><div class="n">{value}</div></div>', unsafe_allow_html=True)

        st.info("Catalog status is public-search evidence only. “NOT DISTRIBUTION” means no obvious match was found in the checked public sources; it is not proof that a song is unowned, copyright-free, or legally available to distribute.")

        if rows:
            df = pd.DataFrame([{
                "title":r["title"],"artist":r["artist"],"channel":r["channel"],
                "views":r["views"],"published":r["published"],"url":r["url"],
                "catalog":checks[i]["status"],"apple":checks[i]["apple"],
                "spotify":checks[i]["spotify"],"youtube_music":checks[i]["youtube_music"]
            } for i,r in enumerate(rows)])
            st.download_button("⬇️ Download CSV", df.to_csv(index=False).encode(), "music_opportunity_v2_1.csv", "text/csv")
            for i, r in enumerate(rows):
                c = checks[i]
                render_result({**r, "artist":r["artist"]}, check=False)
                st.caption(f"Catalog: {c['status']} • Apple: {c['apple']} • Spotify: {c['spotify']} • YouTube Music: {c['youtube_music']}")

elif mode == "🔎 Artist Finder":
    st.markdown("## 🔎 Artist Finder")
    artist = st.text_input("Artist / Singer name", placeholder="Type any artist name")
    n = st.number_input("Top songs to show", 5, 50, 20, 5)
    if st.button("🔎 FIND ARTIST SONGS", use_container_width=True):
        if not artist.strip(): st.warning("Enter an artist name."); st.stop()
        rows = yt_search(f'"{artist}" official song', int(n))
        rows = sorted(rows, key=lambda x:x["views"], reverse=True)
        st.success(f"Found {len(rows)} public YouTube candidates for {artist}.")
        for r in rows:
            render_result({**r, "artist":artist}, check=True)

elif mode == "📺 Channel Scanner":
    st.markdown("## 📺 Channel Scanner")
    channel_url = st.text_input("YouTube channel URL", placeholder="https://www.youtube.com/@ChannelName")
    n = st.number_input("Songs to scan", 5, 30, 10, 5)
    min_views = st.number_input("Minimum views", 0, 100_000_000_000, 0, 10000)
    if st.button("📺 SCAN CHANNEL SONGS", use_container_width=True):
        if not channel_url.strip():
            st.warning("Enter a YouTube channel URL."); st.stop()
        # Search by channel URL/name rather than downloading the whole channel.
        handle = channel_url.rstrip("/").split("/")[-1].replace("@","")
        rows = yt_search(f'@{handle} song', int(n)*2)
        rows = [r for r in rows if r["views"] >= min_views]
        rows = rows[:int(n)]
        st.caption("Scanner checks public song candidates and looks for public catalog clues. It does not claim legal ownership status.")
        for r in rows:
            render_result({**r, "artist":r["channel"]}, check=True)

elif mode == "📝 Lyrics Finder":
    st.markdown("## 📝 Lyrics Finder")
    song = st.text_input("Song name", placeholder="Type song name")
    artist = st.text_input("Singer / Artist name (optional)", placeholder="Optional")
    link = st.text_input("Song link (optional)", placeholder="https://youtube.com/watch?v=...")
    if st.button("📝 FIND LYRICS & SOURCES", use_container_width=True):
        if not song.strip():
            st.warning("Enter song name."); st.stop()
        q = f'"{song}" "{artist}" lyrics' if artist else f'"{song}" lyrics'
        hits = web_search(q, 10)
        st.success(f"Found {len(hits)} public lyric/search sources.")
        for h in hits:
            st.markdown(f"**[{h['title']}]({h['url']})**")
            if h["snippet"]: st.caption(h["snippet"])
        if link:
            st.markdown(f"▶ [Open song link]({link})")
        st.info("This finder returns public lyric/source links rather than reproducing copyrighted lyrics.")

elif mode == "📚 History":
    st.markdown("## 📚 History")
    st.info("V2.1 keeps the app stateless on Streamlit Cloud. Add database-backed history later if you want persistent saved research.")
    st.markdown("""
    **Recommended next upgrade**
    - Save searches/results
    - Favorites / shortlist
    - CSV + JSON export
    - Re-scan saved channels
    - Compare two research runs
    """)

st.markdown("---")
st.caption(f"{APP_TITLE} • Public catalog research only • No API keys required by default")
