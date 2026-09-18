import streamlit as st
import pandas as pd
import requests, re, sqlite3, html, time
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus
from datetime import datetime, timezone

try:
    import yt_dlp
except Exception:
    yt_dlp = None

VERSION = "V1.1"
DB = "music_finder_v1_1.db"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36"

st.set_page_config(page_title=f"Music Opportunity Finder {VERSION}", page_icon="🎵",
                   layout="wide", initial_sidebar_state="expanded")

# ---------- DB ----------
def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY, title TEXT, artist TEXT, channel TEXT, video_id TEXT,
        views INTEGER, published TEXT, catalog TEXT, checked_at TEXT)""")
    c.commit()
    return c

def save_history(rows):
    if not rows:
        return
    c = db()
    for r in rows:
        c.execute("""INSERT INTO history
        (title,artist,channel,video_id,views,published,catalog,checked_at)
        VALUES(?,?,?,?,?,?,?,?)""",
        (r.get("title",""), r.get("artist",""), r.get("channel",""),
         r.get("video_id",""), int(r.get("views",0)), r.get("published",""),
         r.get("catalog",""), datetime.now(timezone.utc).isoformat()))
    c.commit()
    c.close()

# ---------- helpers ----------
def normalize(s):
    s = (s or "").lower()
    s = re.sub(r'[\[\(\{].*?[\]\)\}]', ' ', s)
    s = re.sub(r'\b(official|video|audio|lyrics?|mv|hd|4k|full|song|music|visualizer|officially|presenting)\b', ' ', s)
    s = re.sub(r'[^a-z0-9\u0980-\u09ff]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def tokens(s):
    return set(x for x in normalize(s).split() if len(x) > 1)

def similarity(a, b):
    aa, bb = tokens(a), tokens(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, len(aa | bb))

NOISE = re.compile(
    r'\b(remix|reaction|react|cover|karaoke|instrumental|slowed|reverb|speed ?up|'
    r'mashup|jukebox|full movie|natok|drama|trailer|teaser|shorts?)\b', re.I)

def parse_artist(title, channel=""):
    t = re.sub(r'\[[^\]]+\]|\([^)]*\)', ' ', title or "")
    parts = re.split(r'\s+[|–—-]\s+|\s+ft\.?\s+|\s+feat\.?\s+', t, flags=re.I)
    if len(parts) > 1:
        left = parts[0].strip()
        if 1 <= len(left.split()) <= 8 and not NOISE.search(left):
            return left
    return channel or "Unknown"

def safe_get(url, **kwargs):
    headers = kwargs.pop("headers", {"User-Agent": UA})
    timeout = kwargs.pop("timeout", 7)
    for attempt in range(2):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, **kwargs)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(0.35 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except Exception:
            if attempt == 0:
                time.sleep(0.25)
    return None

# ---------- YouTube public search ----------
@st.cache_data(ttl=180, show_spinner=False)
def yt_search(query, limit=20):
    if not yt_dlp:
        return []
    try:
        opts = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": True, "ignoreerrors": True,
            "socket_timeout": 7, "retries": 1,
            "playlistend": min(max(int(limit), 5), 50),
            "extractor_args": {"youtube": {"player_client": ["web"]}},
        }
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(f"ytsearch{int(limit)}:{query}", download=False)
        out = []
        for e in (info or {}).get("entries", []) or []:
            if not e or not e.get("id"):
                continue
            vid = e["id"]
            channel = e.get("channel") or e.get("uploader") or ""
            title = e.get("title") or ""
            out.append({
                "video_id": vid, "title": title, "channel": channel,
                "views": int(e.get("view_count") or 0),
                "published": e.get("upload_date") or "",
                "artist": parse_artist(title, channel),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "channel_url": e.get("channel_url") or e.get("uploader_url") or "",
            })
        return out
    except Exception:
        return []

@st.cache_data(ttl=180, show_spinner=False)
def multi_search(keyword, limit):
    qs = [keyword, f"{keyword} official song", f"{keyword} music video"]
    per = max(5, min(30, int(limit // 2) + 4))
    merged, seen = [], set()
    with ThreadPoolExecutor(max_workers=3) as ex:
        fs = [ex.submit(yt_search, q, per) for q in qs]
        for f in as_completed(fs):
            try:
                rows = f.result()
            except Exception:
                rows = []
            for r in rows:
                k = r["video_id"] or normalize(r["title"] + r["channel"])
                if k not in seen:
                    seen.add(k)
                    merged.append(r)
    return merged[:int(limit)]

# ---------- direct channel scan ----------
@st.cache_data(ttl=180, show_spinner=False)
def channel_videos(channel_ref, limit=50):
    if not yt_dlp:
        return []
    ref = channel_ref.strip()
    if not ref:
        return []
    try:
        if ref.startswith("@"):
            ref = "https://www.youtube.com/" + ref
        elif not ref.startswith("http"):
            ref = "https://www.youtube.com/@" + ref.lstrip("@")
        # Avoid adding /videos twice.
        url = ref.rstrip("/")
        if not re.search(r'/videos$', url):
            url += "/videos"
        opts = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "extract_flat": True, "ignoreerrors": True,
            "playlistend": min(max(int(limit), 10), 100),
            "socket_timeout": 8, "retries": 1,
            "extractor_args": {"youtube": {"player_client": ["web"]}},
        }
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=False)
        out = []
        for e in (info or {}).get("entries", []) or []:
            if not e or not e.get("id"):
                continue
            title = e.get("title") or ""
            channel = e.get("channel") or e.get("uploader") or ref.split("/")[-1]
            out.append({
                "video_id": e["id"], "title": title, "channel": channel,
                "views": int(e.get("view_count") or 0),
                "published": e.get("upload_date") or "",
                "artist": parse_artist(title, channel),
                "url": f"https://www.youtube.com/watch?v={e['id']}",
                "channel_url": e.get("channel_url") or e.get("uploader_url") or ref,
            })
        return out
    except Exception:
        return []

# ---------- catalog checks ----------
@st.cache_data(ttl=900, show_spinner=False)
def apple_match(title, artist):
    q = quote_plus(f"{title} {artist}".strip())
    url = f"https://itunes.apple.com/search?term={q}&media=music&entity=song&limit=15&country=US"
    r = safe_get(url)
    fallback = f"https://music.apple.com/us/search?term={q}"
    if not r:
        return {"state":"UNVERIFIED", "detail":"CHECK FAILED", "url":fallback}
    try:
        data = r.json()
    except Exception:
        return {"state":"UNVERIFIED", "detail":"INVALID RESPONSE", "url":fallback}
    nt, na = normalize(title), normalize(artist)
    best = None
    best_score = 0
    for x in data.get("results", []):
        tt, aa = normalize(x.get("trackName","")), normalize(x.get("artistName",""))
        if not tt:
            continue
        ts = similarity(nt, tt)
        ars = similarity(na, aa) if na else 0
        score = ts * 0.65 + ars * 0.35
        # Exact artist + strong title is required for a positive result.
        if (nt == tt or ts >= 0.72) and (not na or na == aa or ars >= 0.65):
            if score > best_score:
                best_score, best = score, x
    if best and best_score >= 0.68:
        return {"state":"MATCH", "detail":f"{best.get('artistName','')} — {best.get('trackName','')}",
                "url":best.get("trackViewUrl") or fallback}
    return {"state":"NO_MATCH", "detail":"NO OBVIOUS MATCH", "url":fallback}

@st.cache_data(ttl=600, show_spinner=False)
def ddg_catalog_search(title, artist, domain):
    q = quote_plus(f'"{title}" "{artist}"')
    url = f"https://html.duckduckgo.com/html/?q={q}+site%3A{domain}"
    r = safe_get(url, timeout=6)
    if not r:
        return {"state":"UNVERIFIED","url":f"https://www.google.com/search?q={q}+site%3A{domain}"}
    try:
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return {"state":"UNVERIFIED","url":f"https://www.google.com/search?q={q}+site%3A{domain}"}
    nt, na = normalize(title), normalize(artist)
    best = None
    for a in soup.select("a.result__a")[:10]:
        txt = a.get_text(" ", strip=True)
        href = a.get("href","")
        blob = normalize(txt)
        if nt and nt in blob and (not na or na in blob):
            best = href
            break
    if best:
        return {"state":"MATCH","url":best}
    # Search completed successfully but yielded no obvious exact result.
    return {"state":"NO_MATCH","url":f"https://www.google.com/search?q={q}+site%3A{domain}"}

def check_one(r):
    row = dict(r)
    title, artist = row.get("title",""), row.get("artist","")
    apple = apple_match(title, artist)
    spotify = ddg_catalog_search(title, artist, "open.spotify.com")
    ytm = ddg_catalog_search(title, artist, "music.youtube.com")

    checks = [apple, spotify, ytm]
    matches = [x for x in checks if x["state"] == "MATCH"]
    failed = [x for x in checks if x["state"] == "UNVERIFIED"]
    # Positive = actual evidence from a catalog/search result.
    # Negative = only when all 3 completed and none matched.
    if matches:
        catalog = "DISTRIBUTED / MATCH FOUND"
    elif not failed:
        catalog = "NOT DISTRIBUTION"
    else:
        catalog = "CHECK UNVERIFIED"

    row.update({
        "catalog": catalog,
        "apple_status": "MATCH FOUND" if apple["state"]=="MATCH" else (
            "CHECK UNVERIFIED" if apple["state"]=="UNVERIFIED" else "NO OBVIOUS MATCH"),
        "spotify_status": "MATCH FOUND" if spotify["state"]=="MATCH" else (
            "CHECK UNVERIFIED" if spotify["state"]=="UNVERIFIED" else "NO OBVIOUS MATCH"),
        "ytm_status": "MATCH FOUND" if ytm["state"]=="MATCH" else (
            "CHECK UNVERIFIED" if ytm["state"]=="UNVERIFIED" else "NO OBVIOUS MATCH"),
        "apple_url": apple["url"],
        "spotify_url": f"https://open.spotify.com/search/{quote_plus(title+' '+artist)}",
        "ytm_url": f"https://music.youtube.com/search?q={quote_plus(title+' '+artist)}",
        "lyrics_url": f"https://www.google.com/search?q={quote_plus(title+' '+artist+' lyrics')}",
        "google_url": f"https://www.google.com/search?q={quote_plus(title+' '+artist)}",
        "evidence": "Exact/strong public catalog evidence found." if matches else (
            "All three public catalog checks completed with no obvious exact match."
            if not failed else
            "One or more public checks could not be completed; status is not treated as a negative."
        )
    })
    return row

def research_rows(rows, workers=8):
    out = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=int(workers)) as ex:
        fs = {ex.submit(check_one, r): i for i, r in enumerate(rows)}
        for f in as_completed(fs):
            i = fs[f]
            try:
                out[i] = f.result()
            except Exception:
                out[i] = dict(rows[i], catalog="CHECK UNVERIFIED",
                              apple_status="CHECK UNVERIFIED",
                              spotify_status="CHECK UNVERIFIED",
                              ytm_status="CHECK UNVERIFIED")
    return [x for x in out if x]

def filter_rows(rows, min_views, max_views, year, hide_noise):
    out, seen = [], set()
    cutoff = datetime.now().year - int(year) if int(year) else None
    for r in rows:
        k = r.get("video_id") or normalize(r.get("title","") + r.get("channel",""))
        if k in seen: continue
        seen.add(k)
        views = int(r.get("views",0))
        if views < int(min_views): continue
        if int(max_views) and views > int(max_views): continue
        ds = str(r.get("published",""))
        if cutoff and re.match(r'^\d{8}$', ds) and int(ds[:4]) > cutoff:
            continue
        if hide_noise and NOISE.search(r.get("title","")):
            continue
        out.append(r)
    return sorted(out, key=lambda x:int(x.get("views",0)), reverse=True)

# ---------- UI ----------
st.markdown("""
<style>
:root{--bg:#090c14;--panel:#101521;--panel2:#151a27;--line:#283148;--muted:#9aa6bd;--accent:#7c5cff;--hot:#ff4d55}
.block-container{padding-top:1.15rem;padding-bottom:3rem;max-width:1500px}
[data-testid="stSidebar"]{background:#171923;border-right:1px solid #282d3a}
[data-testid="stSidebar"] .block-container{padding:1.25rem 1rem}
.hero{padding:26px 30px;border:1px solid #293550;border-radius:24px;background:radial-gradient(circle at 86% 12%,#25204b 0,#111625 42%,#0a0d15 82%);box-shadow:0 14px 40px rgba(0,0,0,.22);margin-bottom:22px}
.hero h1{font-size:39px;line-height:1.1;margin:0;font-weight:850;letter-spacing:-.7px}.hero b{color:#8b70ff}.hero p{margin:8px 0 0;color:#aab4c9;font-size:15px}
.section{font-size:26px;font-weight:820;margin:4px 0 14px;letter-spacing:-.3px}
.search-card{padding:18px 20px;border:1px solid #283249;border-radius:20px;background:linear-gradient(180deg,#111622,#0d111b);margin-bottom:14px}
.songbox{border:1px solid #293249;border-radius:16px;padding:14px 16px;background:#111621;margin:8px 0}
.songtitle{font-size:18px;font-weight:800}.artist{color:#aeb8ca;margin-top:4px}.links{margin-top:8px;color:#b9c1d1}
.metric-wrap{padding:14px 16px;border:1px solid #293249;border-radius:16px;background:#111621}
.small-note{color:#8792aa;font-size:13px}
div.stButton>button[kind="primary"]{border-radius:12px;font-weight:750;min-height:44px}
[data-testid="stMetric"]{background:#111621;border:1px solid #293249;padding:10px 14px;border-radius:14px}
.stDataFrame{border:1px solid #293249;border-radius:14px;overflow:hidden}
</style>
""", unsafe_allow_html=True)

st.markdown(f'<div class="hero"><h1>🎵 Music Opportunity Finder <b>{VERSION}</b></h1><p>Viral • Old • High-View • Artist • Channel • Lyrics • Public Catalog Research</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("🎯 Research Center")
    mode = st.radio("Research mode", ["🔥 Song Discovery","🎤 Artist Finder","📺 Channel Scanner","📝 Lyrics Finder","📚 History"])
    keyword = st.text_input("🔎 Search", "Bangla old viral song")
    st.caption("Type any keyword, singer, channel, year or number.")
    results = st.number_input("Results",5,100,30,5)
    min_views = st.number_input("Minimum views",0,2_000_000_000,100000,10000)
    max_views = st.number_input("Maximum views (0 = unlimited)",0,2_000_000_000,0,10000)
    year = st.number_input("Year / Old-song cutoff (0 = Any Year)",0,100,0,1)
    hide_noise = st.checkbox("🚫 Hide remix/cover/reaction/movie noise",True)
    workers = st.slider("⚡ Parallel research",2,12,8)
    st.divider()
    st.caption("🔓 Default workflow uses public search. No YouTube/Spotify API key is required.")
    st.caption("⚠️ NOT DISTRIBUTION only means all three public checks completed without an obvious exact match.")

def linkline(r):
    st.markdown(
        f'▶ [YouTube]({r.get("url","")}) • 🎧 [Spotify Search]({r.get("spotify_url","")}) • '
        f'🍎 [Apple Music]({r.get("apple_url","")}) • 🎼 [YouTube Music]({r.get("ytm_url","")}) • '
        f'📝 [Lyrics Search]({r.get("lyrics_url","")}) • 🔎 [Google]({r.get("google_url","")})'
    )
    if r.get("channel_url"):
        st.markdown(f'📺 [Channel]({r["channel_url"]})')

def render_catalog(df, name):
    st.subheader(name)
    if df.empty:
        st.info("No results in this catalog.")
        return
    cols = ["title","artist","channel","views","published","apple_status","spotify_status","ytm_status"]
    st.dataframe(df[[c for c in cols if c in df.columns]], use_container_width=True, hide_index=True)
    for _, r in df.iterrows():
        with st.expander(f'🎵 {r["title"]} • {int(r.get("views",0)):,} views'):
            st.write(f'**Artist:** {r.get("artist","")}  |  **Channel:** {r.get("channel","")}')
            st.write(f'**Catalog:** {r.get("catalog","")}')
            st.write(f'**Apple:** {r.get("apple_status","")}  |  **Spotify:** {r.get("spotify_status","")}  |  **YouTube Music:** {r.get("ytm_status","")}')
            st.caption(r.get("evidence",""))
            linkline(r)

def show_two(checked):
    df = pd.DataFrame(checked)
    if df.empty:
        st.warning("No candidates.")
        return
    c1 = df[df.catalog=="DISTRIBUTED / MATCH FOUND"]
    c2 = df[df.catalog=="NOT DISTRIBUTION"]
    c3 = df[df.catalog=="CHECK UNVERIFIED"]
    a,b,c,d = st.columns(4)
    a.metric("🎵 Songs",len(df)); b.metric("📁 Distributed",len(c1)); c.metric("📁 Not Distribution",len(c2)); d.metric("⚠️ Unverified",len(c3))
    st.warning("NOT DISTRIBUTION is a public-search finding only. It is not proof of copyright ownership, clearance, or legal availability.")
    render_catalog(c1,"📁 CATALOG 1 — DISTRIBUTED / MATCH FOUND")
    render_catalog(c2,"📁 CATALOG 2 — NOT DISTRIBUTION")
    if not c3.empty:
        render_catalog(c3,"⚠️ CHECK UNVERIFIED")
    st.divider()
    x,y = st.columns(2)
    x.download_button("⬇️ Download CSV", df.to_csv(index=False).encode("utf-8-sig"), "music_finder_v1_1.csv", "text/csv")
    y.download_button("⬇️ Download JSON", df.to_json(orient="records",force_ascii=False,indent=2).encode("utf-8"), "music_finder_v1_1.json", "application/json")
    save_history(checked)

# ---------- modes ----------
if mode == "📚 History":
    c = db()
    h = pd.read_sql_query("SELECT * FROM history ORDER BY id DESC LIMIT 500", c)
    c.close()
    st.markdown('<div class="section">📚 Research History</div>', unsafe_allow_html=True)
    st.dataframe(h, use_container_width=True, hide_index=True)
    st.stop()

if mode == "📝 Lyrics Finder":
    st.markdown('<div class="section">📝 Lyrics Finder</div>', unsafe_allow_html=True)
    song = st.text_input("🎵 Song name", keyword if keyword else "")
    artist = st.text_input("🎤 Singer / Artist name (optional)", "")
    song_link = st.text_input("🔗 Song link (optional)", "")
    if st.button("📝 Find Lyrics", type="primary", use_container_width=True):
        if not song.strip():
            st.warning("Song name is required.")
        else:
            q = quote_plus((song+" "+artist).strip())
            st.markdown(f'<div class="songbox"><div class="songtitle">🎵 {html.escape(song)}</div><div class="artist">🎤 {html.escape(artist) if artist else "Artist not provided"}</div></div>', unsafe_allow_html=True)
            if song_link.strip():
                st.markdown(f"🔗 **Song:** [{song_link}]({song_link})")
            st.markdown("### Public lyric sources")
            st.markdown(f"📝 [Google Lyrics Search](https://www.google.com/search?q={q}+lyrics) • [YouTube Lyrics Search](https://www.youtube.com/results?search_query={q}+lyrics)")
            st.markdown(f"🎤 [Musixmatch](https://www.musixmatch.com/search/{q}) • [Genius](https://genius.com/search?q={q})")
            st.caption("The finder links to public lyric sources instead of reproducing copyrighted lyrics.")
    st.stop()

if mode == "🎤 Artist Finder":
    st.markdown('<div class="section">🎤 Artist Finder — Top Songs</div>', unsafe_allow_html=True)
    artist_name = st.text_input("Artist / Singer name", keyword)
    if st.button("🔥 Find Artist Songs FAST", type="primary", use_container_width=True):
        with st.spinner("⚡ Searching the artist in parallel…"):
            rows = multi_search(f'"{artist_name}" song', int(results))
        target = normalize(artist_name)
        rows = [r for r in rows if target and (target in normalize(r.get("title","")) or target in normalize(r.get("artist","")) or target in normalize(r.get("channel","")))]
        rows = filter_rows(rows,int(min_views),int(max_views),int(year),hide_noise)
        if not rows:
            st.warning("No strong artist matches. Try the exact singer name, channel name, or lower Minimum views.")
        else:
            checked = research_rows(rows,int(workers))
            show_two(checked)
    st.stop()

if mode == "📺 Channel Scanner":
    st.markdown('<div class="section">📺 Channel Scanner</div>', unsafe_allow_html=True)
    channel_ref = st.text_input("YouTube channel URL / @handle / channel name", keyword)
    st.caption("Pulls videos directly from the channel first, then checks public catalog evidence.")
    if st.button("📡 Scan Channel FAST", type="primary", use_container_width=True):
        with st.spinner("⚡ Reading channel videos…"):
            rows = channel_videos(channel_ref,int(results))
        rows = filter_rows(rows,int(min_views),int(max_views),int(year),hide_noise)
        if not rows:
            st.error("Could not read the channel. Use the exact YouTube @handle or full channel URL.")
        else:
            checked = research_rows(rows,int(workers))
            show_two(checked)
            st.markdown('<div class="section">📺 Channel Song List</div>', unsafe_allow_html=True)
            for r in checked:
                st.markdown(f'<div class="songbox"><div class="songtitle">🎵 {html.escape(r["title"])}</div><div class="artist">🎤 {html.escape(r.get("artist","Unknown"))} • {int(r.get("views",0)):,} views</div><div class="links">{r.get("catalog","")}</div></div>', unsafe_allow_html=True)
                linkline(r)
    st.stop()

# ---------- Song discovery ----------
st.markdown('<div class="section">🔎 Viral Song Discovery</div>', unsafe_allow_html=True)
if st.button("🚀 FAST FIND & RESEARCH SONGS", type="primary", use_container_width=True):
    with st.spinner("⚡ Fast multi-search…"):
        rows = multi_search(keyword,int(results))
    rows = filter_rows(rows,int(min_views),int(max_views),int(year),hide_noise)
    if not rows:
        st.warning("No candidates. Try Any Year / 0 and lower Minimum views.")
        st.stop()
    with st.spinner("⚡ Parallel public catalog checks…"):
        checked = research_rows(rows,int(workers))
    show_two(checked)
else:
    st.info("Type any keyword, song, singer, channel, year or number and press FAST FIND & RESEARCH SONGS.")
