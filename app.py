import streamlit as st
import pandas as pd
import requests, re, sqlite3, html
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, urlparse
from datetime import datetime, timezone
from difflib import SequenceMatcher

st.set_page_config(page_title="Music Opportunity Finder V1.3", page_icon="🎵", layout="wide", initial_sidebar_state="expanded")
DB = "music_finder_v1_3.db"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/139 Safari/537.36"

# ---------- DB ----------
def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY, title TEXT, artist TEXT, channel TEXT, video_id TEXT,
        views INTEGER, published TEXT, catalog TEXT, checked_at TEXT)""")
    c.commit(); return c

def save_history(rows):
    if not rows: return
    c = db()
    for r in rows:
        c.execute("INSERT INTO history(title,artist,channel,video_id,views,published,catalog,checked_at) VALUES(?,?,?,?,?,?,?,?)",
                  (r.get("title",""),r.get("artist",""),r.get("channel",""),r.get("video_id",""),
                   int(r.get("views",0)),r.get("published",""),r.get("catalog",""),datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()

# ---------- helpers ----------
def normalize(s):
    s = (s or "").lower()
    s = re.sub(r'[\[\(\{].*?[\]\)\}]', ' ', s)
    s = re.sub(r'\b(official|video|audio|lyrics?|mv|hd|4k|full|song|music|visualizer|officially|presenting)\b', ' ', s)
    s = re.sub(r'[^a-z0-9\u0980-\u09ff]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

NOISE = re.compile(r'\b(remix|reaction|react|cover|karaoke|instrumental|slowed|reverb|speed ?up|mashup|jukebox|full movie|natok|drama|trailer|teaser|shorts?)\b', re.I)

def parse_artist(title, channel=""):
    t = re.sub(r'\[[^\]]+\]|\([^)]*\)', ' ', title or "")
    parts = re.split(r'\s+[|–—-]\s+|\s+ft\.?\s+|\s+feat\.?\s+', t, flags=re.I)
    if len(parts) > 1:
        left = parts[0].strip()
        if 1 <= len(left.split()) <= 8 and not NOISE.search(left): return left
    return channel or "Unknown"


def clean_song_title(title):
    """Best-effort cleanup for display/search matching; keeps the original title separately."""
    t = re.sub(r'\[[^\]]*\]|\([^)]*\)', " ", title or "")
    t = re.sub(r'\b(official\s+(music\s+)?video|official\s+audio|lyrics?|hd|4k|full\s+song|music\s+video)\b', " ", t, flags=re.I)
    return re.sub(r'\s+', " ", t).strip(" -–—|")

def exact_relevance(title, artist, channel, query):
    q=normalize(query)
    if not q: return 0
    fields=[normalize(title),normalize(artist),normalize(channel)]
    score=0
    for f in fields:
        if q == f: score=max(score,100)
        elif q in f: score=max(score,75)
    return score

# ---------- YouTube public search, no API key ----------
@st.cache_data(ttl=180, show_spinner=False)
def yt_search(query, limit=20):
    try:
        import yt_dlp
        opts={"quiet":True,"no_warnings":True,"skip_download":True,"extract_flat":True,
              "ignoreerrors":True,"socket_timeout":4,"retries":1,
              "playlistend":min(max(int(limit),5),40),
              "extractor_args":{"youtube":{"player_client":["web"]}}}
        with yt_dlp.YoutubeDL(opts) as y:
            info=y.extract_info(f"ytsearch{int(limit)}:{query}", download=False)
        out=[]
        for e in (info or {}).get("entries",[]) or []:
            if not e or not e.get("id"): continue
            vid=e.get("id")
            out.append({"video_id":vid,"title":e.get("title") or "",
                        "channel":e.get("channel") or e.get("uploader") or "",
                        "views":int(e.get("view_count") or 0),
                        "published":e.get("upload_date") or "",
                        "artist":parse_artist(e.get("title") or "",e.get("channel") or e.get("uploader") or ""),
                        "url":f"https://www.youtube.com/watch?v={vid}",
                        "channel_url":e.get("channel_url") or e.get("uploader_url") or ""})
        return out
    except Exception:
        return []

@st.cache_data(ttl=180, show_spinner=False)
def multi_search(keyword, limit, artist=""):
    base=(keyword.strip()+" "+artist.strip()).strip()
    qs=[f'"{base}"', f'{base} official song', f'{base} music video']
    per=max(5,min(24,int(limit//2)+3))
    merged=[]; seen=set()
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs=[ex.submit(yt_search,q,per) for q in qs]
        for f in as_completed(futs):
            for r in f.result():
                k=r["video_id"] or normalize(r["title"]+r["channel"])
                if k not in seen: seen.add(k); merged.append(r)
    return merged[:int(limit)]

# ---------- direct channel scan ----------
@st.cache_data(ttl=180, show_spinner=False)
def channel_videos(channel_ref, limit=50):
    """Pull videos directly from a YouTube channel. This avoids search-engine ambiguity."""
    try:
        import yt_dlp
        ref=channel_ref.strip()
        if not ref.startswith("http"):
            ref="https://www.youtube.com/@"+ref.lstrip("@")
        opts={"quiet":True,"no_warnings":True,"skip_download":True,"extract_flat":True,
              "ignoreerrors":True,"playlistend":min(max(int(limit),10),100),"socket_timeout":6,"retries":0}
        with yt_dlp.YoutubeDL(opts) as y:
            info=y.extract_info(ref+"/videos",download=False)
        out=[]
        for e in (info or {}).get("entries",[]) or []:
            if not e or not e.get("id"): continue
            vid=e["id"]; title=e.get("title") or ""
            out.append({"video_id":vid,"title":title,
                        "channel":e.get("channel") or e.get("uploader") or (ref.split("/")[-1]),
                        "views":int(e.get("view_count") or 0),"published":e.get("upload_date") or "",
                        "artist":parse_artist(title,e.get("channel") or e.get("uploader") or ""),
                        "url":f"https://www.youtube.com/watch?v={vid}",
                        "channel_url":e.get("channel_url") or e.get("uploader_url") or ref})
        return out
    except Exception:
        return []

# ---------- public catalog clues ----------
@st.cache_data(ttl=300, show_spinner=False)
def apple_match(title, artist):
    """Check the public Apple/iTunes catalog without requiring an API key.
    The title is the primary key; artist is a second signal when available.
    Weak/ambiguous search hits are deliberately not counted as distribution.
    """
    clean_title=clean_song_title(title)
    queries=[clean_title, f"{clean_title} {artist}".strip()]
    best=None
    nt=normalize(clean_title)
    na=normalize(artist)
    try:
        for query_text in queries:
            q=quote_plus(query_text)
            r=requests.get(f"https://itunes.apple.com/search?term={q}&media=music&entity=song&limit=15",headers={"User-Agent":UA},timeout=4)
            data=r.json()
            for x in data.get("results",[]):
                tt=normalize(x.get("trackName","")); aa=normalize(x.get("artistName",""))
                if not tt or not nt: continue
                title_sim=SequenceMatcher(None,nt,tt).ratio()
                title_ok=(nt==tt) or (nt in tt) or (tt in nt) or title_sim>=0.90
                artist_sim=SequenceMatcher(None,na,aa).ratio() if na and aa else 0
                artist_ok=(not na) or (na==aa) or (na in aa) or (aa in na) or artist_sim>=0.82
                # Exact/near-exact title + artist is strong. If the supplied artist is
                # actually a channel/uploader, title-only still gets a medium score and
                # is NOT enough to classify as distributed unless title is exact.
                score=title_sim*3 + (artist_sim*2 if na else 0)
                if title_ok and artist_ok:
                    if na and not (na==aa or na in aa or aa in na or artist_sim>=0.82):
                        continue
                    candidate=(score,x,title_sim,artist_sim)
                    if best is None or candidate[0]>best[0]: best=candidate
        if best:
            _,x,ts,ascore=best
            strong_title=ts>=0.92
            strong_artist=(not na) or ascore>=0.82
            if strong_title and strong_artist:
                return True,f"{x.get('artistName','')} — {x.get('trackName','')}",x.get('trackViewUrl','')
    except Exception:
        pass
    q=quote_plus(f"{clean_title} {artist}".strip())
    return False,"No strong Apple/iTunes match",f"https://music.apple.com/us/search?term={q}"

@st.cache_data(ttl=300, show_spinner=False)
def web_release_clues(title, artist):
    """Fast public web check. Looks for public release/catalog pages; never treats absence as clearance."""
    q=quote_plus(f'"{title}" "{artist}"')
    urls=[
        f"https://www.google.com/search?q={q}+Spotify",
        f"https://www.google.com/search?q={q}+Apple+Music",
        f"https://www.google.com/search?q={q}+music+distribution",
    ]
    # Lightweight request to Google is intentionally best-effort; the links are always returned.
    text=""
    try:
        rr=requests.get(urls[0],headers={"User-Agent":UA},timeout=3)
        text=rr.text.lower()
    except Exception: pass
    hits=[]
    for term in ["open.spotify.com","music.apple.com","spotify.com","music.youtube.com"]:
        if term in text: hits.append(term)
    return hits, urls

def check_one(r):
    row=dict(r); title=row.get("title",""); artist=row.get("artist","")
    # Apple/iTunes is a real public catalog response; only a strong title+artist match
    # is allowed to move a song into the Distributed catalog. Search-page URLs are
    # always exposed separately, but are never treated as proof of a match.
    am,ad,au=apple_match(title,artist)
    q=quote_plus((clean_song_title(title)+" "+artist).strip())
    row.update({
        "apple_status":"MATCH FOUND" if am else "NO MATCH",
        "apple_detail":ad, "apple_url":au,
        "spotify_status":"SEARCH ONLY",
        "spotify_url":f"https://open.spotify.com/search/{q}",
        "ytm_status":"SEARCH ONLY",
        "ytm_url":f"https://music.youtube.com/search?q={q}",
        "lyrics_url":f"https://www.google.com/search?q={q}+lyrics",
        "google_url":f"https://www.google.com/search?q={q}+music+distribution",
        "web_clues":"Search links only — not verified",
    })
    distributed=bool(am)
    row["catalog"]="DISTRIBUTED / MATCH FOUND" if distributed else "NOT DISTRIBUTION"
    row["evidence"]=("Strong Apple/iTunes public-catalog match found for this title/artist pair. Verify the exact recording and rights."
                      if distributed else "No strong Apple/iTunes public-catalog match was found. Spotify/YouTube Music links are search-only and are not counted as distribution evidence.")
    return row

def research_rows(rows,workers=8):
    out=[]
    with ThreadPoolExecutor(max_workers=int(workers)) as ex:
        fs=[ex.submit(check_one,r) for r in rows]
        for f in as_completed(fs):
            try: out.append(f.result())
            except Exception: pass
    return out

def filter_rows(rows,min_views,max_views,year,hide_noise):
    out=[]; seen=set(); cutoff=datetime.now().year-int(year) if int(year) else None
    for r in rows:
        k=r.get("video_id") or normalize(r.get("title","")+r.get("channel",""))
        if k in seen: continue
        seen.add(k)
        if int(r.get("views",0))<int(min_views): continue
        if int(max_views) and int(r.get("views",0))>int(max_views): continue
        ds=str(r.get("published", ""))
        if cutoff and re.match(r'^\d{8}$',ds) and int(ds[:4])>cutoff: continue
        if hide_noise and NOISE.search(r.get("title","")): continue
        out.append(r)
    return sorted(out,key=lambda x:int(x.get("views",0)),reverse=True)

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
""",unsafe_allow_html=True)
st.markdown('<div class="hero"><h1>🎵 Music Opportunity Finder <b>V1.3</b></h1><p>Viral • Old • High-View • Artist • Channel • Lyrics • Public Catalog Research</p></div>',unsafe_allow_html=True)
st.markdown('<div class="section">🔎 Viral Song Discovery</div>',unsafe_allow_html=True)

with st.sidebar:
    st.header("🎯 Research Center")
    mode=st.radio("Research mode",["🔥 Song Discovery","🎤 Artist Finder","📺 Channel Scanner","📝 Lyrics Finder","📚 History"])
    keyword=st.text_input("🔎 Search", "Bangla old viral song")
    artist_filter=st.text_input("🎤 Singer / Artist (optional)", "")
    st.caption("Type any keyword, song, singer, channel, year or number.")
    results=st.number_input("Results",5,100,30,5)
    min_views=st.number_input("Minimum views",0,2_000_000_000,100000,10000)
    max_views=st.number_input("Maximum views (0 = unlimited)",0,2_000_000_000,0,10000)
    year=st.number_input("Year / Old-song cutoff (0 = Any Year)",0,2100,0,1)
    hide_noise=st.checkbox("🚫 Hide remix/cover/reaction/movie noise",True)
    workers=st.slider("⚡ Parallel research",2,12,10)
    st.divider(); st.caption("🔓 No YouTube/Spotify API key required for the default public-search workflow.")
    st.caption("⚠️ Catalog 2 is a public-search classification only; it is never proof that a song is free to distribute.")

def linkline(r):
    st.markdown(f"▶ [YouTube]({r.get('url','')})  •  🎧 [Spotify]({r.get('spotify_url','')})  •  🍎 [Apple Music]({r.get('apple_url','')})  •  🎼 [YouTube Music]({r.get('ytm_url','')})  •  📝 [Lyrics Search]({r.get('lyrics_url','')})")
    if r.get("channel_url"): st.markdown(f"📺 [Channel]({r['channel_url']})")

def render_catalog(df,name):
    st.subheader(name)
    if df.empty: st.info("No results in this catalog yet."); return
    cols=["title","artist","channel","views","published","apple_status","spotify_status","ytm_status"]
    st.dataframe(df[[c for c in cols if c in df.columns]],use_container_width=True,hide_index=True)
    for _,r in df.iterrows():
        with st.expander(f"🎵 {r['title']} • {int(r.get('views',0)):,} views"):
            st.write(f"**Artist:** {r.get('artist','')}  |  **Channel:** {r.get('channel','')}")
            st.write(f"**Catalog:** {r.get('catalog','')}  |  **Apple:** {r.get('apple_status','')}  |  **Spotify:** {r.get('spotify_status','')}  |  **YouTube Music:** {r.get('ytm_status','')}")
            st.caption(r.get('evidence',''))
            linkline(r)

def show_two(checked):
    df=pd.DataFrame(checked)
    if df.empty: st.warning("No candidates."); return
    c1=df[df.catalog=="DISTRIBUTED / MATCH FOUND"]; c2=df[df.catalog=="NOT DISTRIBUTION"]
    a,b,c,d=st.columns(4); a.metric("🎵 Songs",len(df)); b.metric("📁 Distributed",len(c1)); c.metric("📁 NOT DISTRIBUTION",len(c2)); d.metric("🔥 1M+",int((df.views>=1_000_000).sum()))
    st.warning("NOT DISTRIBUTION means no strong Apple/iTunes catalog match was found. Spotify and YouTube Music are shown as search links only. Verify ownership, master, publishing, label and licensing rights before distribution.")
    render_catalog(c1,"📁 CATALOG 1 — DISTRIBUTED / MATCH FOUND")
    render_catalog(c2,"📁 CATALOG 2 — NOT DISTRIBUTION")
    st.divider(); x,y=st.columns(2)
    x.download_button("⬇️ Download CSV",df.to_csv(index=False).encode("utf-8-sig"),"music_finder_v1_3.csv","text/csv")
    y.download_button("⬇️ Download JSON",df.to_json(orient="records",force_ascii=False,indent=2).encode("utf-8"),"music_finder_v1_3.json","application/json")
    save_history(checked)

# ---------- modes ----------
if mode=="📚 History":
    c=db(); h=pd.read_sql_query("SELECT * FROM history ORDER BY id DESC LIMIT 500",c); c.close()
    st.subheader("📚 Research History"); st.dataframe(h,use_container_width=True,hide_index=True); st.stop()

if mode=="📝 Lyrics Finder":
    st.markdown('<div class="section">📝 Lyrics Finder</div>',unsafe_allow_html=True)
    song=st.text_input("🎵 Song name",keyword if keyword else "")
    artist=st.text_input("🎤 Singer / Artist name (optional)","")
    song_link=st.text_input("🔗 Song link (optional)","")
    if st.button("📝 Find Lyrics",type="primary",use_container_width=True):
        if not song.strip(): st.warning("Song name is required.")
        else:
            q=quote_plus((song+" "+artist).strip())
            st.markdown(f'<div class="songbox"><div class="songtitle">🎵 {html.escape(song)}</div><div class="artist">🎤 {html.escape(artist) if artist else "Artist not provided"}</div></div>',unsafe_allow_html=True)
            if song_link.strip(): st.markdown(f"🔗 **Song:** [{song_link}]({song_link})")
            st.markdown("### Public lyric sources")
            st.markdown(f"📝 [Google Lyrics Search](https://www.google.com/search?q={q}+lyrics)  •  [YouTube Lyrics Search](https://www.youtube.com/results?search_query={q}+lyrics)")
            st.markdown(f"🎤 [Musixmatch](https://www.musixmatch.com/search/{q})  •  [Genius](https://genius.com/search?q={q})")
            st.caption("The app links to public lyric sources rather than reproducing copyrighted lyrics.")
    st.stop()

if mode=="🎤 Artist Finder":
    st.markdown('<div class="section">🎤 Artist Finder — Top Songs</div>',unsafe_allow_html=True)
    artist_name=st.text_input("Artist / Singer name",keyword)
    if st.button("🔥 Find Artist Songs FAST",type="primary",use_container_width=True):
        with st.spinner("⚡ Searching the artist in parallel…"):
            rows=multi_search(f'"{artist_name}" song',int(results))
        # Strong artist relevance filter before catalog checks
        target=normalize(artist_name)
        rows=[r for r in rows if target and (target in normalize(r.get("title","")) or target in normalize(r.get("artist","")) or target in normalize(r.get("channel","")))]
        rows=filter_rows(rows,int(min_views),int(max_views),int(year),hide_noise)
        if not rows: st.warning("No strong artist matches. Try the exact singer name, channel name, or lower Minimum views.")
        else:
            checked=research_rows(rows,int(workers)); show_two(checked)
    st.stop()

if mode=="📺 Channel Scanner":
    st.markdown('<div class="section">📺 Channel Scanner</div>',unsafe_allow_html=True)
    channel_ref=st.text_input("YouTube channel URL / @handle / channel name",keyword)
    st.caption("This mode pulls videos directly from the channel first, then checks whether each song has public release/catalog clues elsewhere.")
    if st.button("📡 Scan Channel FAST",type="primary",use_container_width=True):
        with st.spinner("⚡ Reading channel videos…"):
            rows=channel_videos(channel_ref,int(results))
        rows=filter_rows(rows,int(min_views),int(max_views),int(year),hide_noise)
        if not rows:
            st.error("Could not read the channel. Use the exact YouTube @handle or full channel URL.")
        else:
            checked=research_rows(rows,int(workers)); show_two(checked)
            st.markdown('<div class="section">📺 Channel Song List</div>',unsafe_allow_html=True)
            for r in checked:
                st.markdown(f'<div class="songbox"><div class="songtitle">🎵 {html.escape(r["title"])}</div><div class="artist">🎤 {html.escape(r.get("artist", "Unknown"))} • {int(r.get("views",0)):,} views • {html.escape(r.get("catalog",""))}</div></div>',unsafe_allow_html=True)
                linkline(r)
    st.stop()

# song discovery
if st.button("🚀 FAST FIND & RESEARCH SONGS",type="primary",use_container_width=True):
    with st.spinner("⚡ Fast multi-search…"):
        rows=multi_search(keyword,int(results),artist_filter)
    rows=filter_rows(rows,int(min_views),int(max_views),int(year),hide_noise)
    if artist_filter.strip():
        target=normalize(artist_filter)
        rows=[r for r in rows if target in normalize(r.get("title","")+" "+r.get("artist","")+" "+r.get("channel",""))]
    if not rows: st.warning("No candidates. Try Any Year / 0 and lower Minimum views."); st.stop()
    with st.spinner("⚡ Parallel public catalog checks…"):
        checked=research_rows(rows,int(workers))
    show_two(checked)
else:
    st.info("Type any keyword, song, singer, channel, year or number and press FAST FIND & RESEARCH SONGS.")
