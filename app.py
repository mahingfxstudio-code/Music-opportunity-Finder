import base64
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus

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

st.markdown("""
<style>
.stApp{background:#0b0d12;color:#f5f7fb}
section[data-testid="stSidebar"]{background:#171923}
.block-container{max-width:1180px;padding-top:1.2rem}
.v1hero{background:linear-gradient(110deg,#0d1422,#211d48);border:1px solid #293653;border-radius:0 0 28px 28px;padding:25px 30px;margin-bottom:24px}
.v1hero h1{margin:0;font-size:38px;font-weight:800}.v1hero .v{color:#8c69ff}.sub{color:#b9c1d4;margin-top:12px}
.bigbtn button{width:100%;height:52px;background:#ff4d52!important;color:#fff!important;border:0!important;border-radius:9px!important;font-weight:800!important}
.card{background:#101620;border:1px solid #2c3850;border-radius:13px;padding:17px;min-height:105px}.card .n{font-size:32px;font-weight:800;margin-top:4px}
.smallmuted{color:#8f99ad;font-size:13px}.resultbox{background:#0f141c;border:1px solid #303b51;border-radius:12px;padding:15px;margin:9px 0}
.badge{display:inline-block;padding:4px 9px;border-radius:12px;font-size:12px;font-weight:800}
.dist{background:#193d2b;color:#6ff0a3}.notdist{background:#4b2427;color:#ff9ba0}.unverified{background:#403719;color:#ffd86b}
.linkrow a{margin-right:10px}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="v1hero"><h1>🎵 Music Opportunity Finder <span class="v">{VERSION}</span></h1>
<div class="sub">Viral • Old • High-View • Artist • Channel • Lyrics • Public Catalog Research</div></div>
""", unsafe_allow_html=True)

def normalize(s):
    s = (s or "").lower()
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", s)
    s = re.sub(r"[^a-z0-9\u0980-\u09ff]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def fmt_views(n):
    try: n = int(n)
    except Exception: return "—"
    if n >= 1_000_000_000: return f"{n/1e9:.1f}B"
    if n >= 1_000_000: return f"{n/1e6:.1f}M"
    if n >= 1_000: return f"{n/1e3:.1f}K"
    return str(n)

@st.cache_data(ttl=900, show_spinner=False)
def yt_search(query, limit=20):
    if not yt_dlp: return []
    opts = {"quiet":True,"skip_download":True,"extract_flat":True,"noplaylist":False,
            "playlistend":max(1,min(int(limit),50)),"socket_timeout":10,"retries":1,
            "user_agent":UA}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        out = []
        for e in (info or {}).get("entries") or []:
            if not e: continue
            vid = e.get("id") or ""
            out.append({"title":e.get("title") or "","channel":e.get("channel") or e.get("uploader") or "",
                        "channel_id":e.get("channel_id") or "","views":int(e.get("view_count") or 0),
                        "published":e.get("upload_date") or "",
                        "url":e.get("webpage_url") or (f"https://www.youtube.com/watch?v={vid}" if vid else ""),
                        "video_id":vid})
        return out
    except Exception:
        return []

@st.cache_data(ttl=900, show_spinner=False)
def web_search(query, limit=8):
    try:
        r = requests.get("https://html.duckduckgo.com/html/", params={"q":query},
                         headers={"User-Agent":UA}, timeout=8)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rows = []
        for a in soup.select("a.result__a")[:limit]:
            p = a.find_parent(class_="result")
            rows.append({"title":a.get_text(" ",strip=True),"url":a.get("href",""),
                         "snippet":(p.select_one(".result__snippet").get_text(" ",strip=True)
                                    if p and p.select_one(".result__snippet") else "")})
        return rows
    except Exception:
        return []

@st.cache_data(ttl=1800, show_spinner=False)
def apple_search(title, artist):
    try:
        r = requests.get("https://itunes.apple.com/search",
            params={"term":f"{title} {artist}".strip(),"media":"music","entity":"song","limit":15,"country":"US"},
            headers={"User-Agent":UA}, timeout=8)
        r.raise_for_status()
        wt, wa = normalize(title), normalize(artist)
        best, item = 0, None
        for x in r.json().get("results", []):
            tt, aa = normalize(x.get("trackName","")), normalize(x.get("artistName",""))
            score = 0
            if wt and (wt == tt or wt in tt or tt in wt): score += 65
            if wa and (wa == aa or wa in aa or aa in wa): score += 35
            if score > best: best, item = score, x
        if best >= 90:
            return {"state":"MATCH","detail":"MATCH FOUND","url":item.get("trackViewUrl","")}
        return {"state":"NO_MATCH","detail":"NO MATCH","url":""}
    except Exception:
        return {"state":"ERROR","detail":"CHECK FAILED","url":""}

@st.cache_data(ttl=1800, show_spinner=False)
def spotify_search(title, artist):
    cid = st.secrets.get("SPOTIFY_CLIENT_ID","")
    secret = st.secrets.get("SPOTIFY_CLIENT_SECRET","")
    if not cid or not secret:
        return {"state":"UNVERIFIED","detail":"NOT CHECKED (optional API not configured)","url":""}
    try:
        tok = requests.post("https://accounts.spotify.com/api/token",
            headers={"Authorization":"Basic "+base64.b64encode(f"{cid}:{secret}".encode()).decode(),
                     "Content-Type":"application/x-www-form-urlencoded"},
            data={"grant_type":"client_credentials"}, timeout=8)
        tok.raise_for_status()
        access = tok.json()["access_token"]
        r = requests.get("https://api.spotify.com/v1/search",
            headers={"Authorization":f"Bearer {access}"},
            params={"q":f'track:"{title}" artist:"{artist}"',"type":"track","limit":10,"market":"US"},
            timeout=8)
        r.raise_for_status()
        wt, wa = normalize(title), normalize(artist)
        for x in r.json().get("tracks",{}).get("items",[]):
            tt = normalize(x.get("name",""))
            names = [normalize(a.get("name","")) for a in x.get("artists",[])]
            if (wt == tt or wt in tt or tt in wt) and any(wa == a or wa in a or a in wa for a in names):
                return {"state":"MATCH","detail":"MATCH FOUND","url":x.get("external_urls",{}).get("spotify","")}
        return {"state":"NO_MATCH","detail":"NO MATCH","url":""}
    except Exception:
        return {"state":"ERROR","detail":"CHECK FAILED","url":""}

@st.cache_data(ttl=1800, show_spinner=False)
def youtube_music_search(title, artist):
    hits = web_search(f'site:music.youtube.com "{title}" "{artist}"', 8)
    wt, wa = normalize(title), normalize(artist)
    for h in hits:
        text = normalize(h.get("title","")+" "+h.get("snippet",""))
        if wt and wt in text and (not wa or wa in text):
            return {"state":"MATCH","detail":"MATCH FOUND","url":h.get("url","")}
    if hits:
        return {"state":"NO_MATCH","detail":"NO MATCH","url":""}
    return {"state":"UNVERIFIED","detail":"CHECK UNVERIFIED","url":""}

def distribution_check(title, artist):
    if not title.strip() or not artist.strip():
        return {"status":"CHECK UNVERIFIED","apple":"NEEDS SONG + ARTIST",
                "spotify":"NEEDS SONG + ARTIST","youtube_music":"NEEDS SONG + ARTIST",
                "apple_url":"","spotify_url":"","youtube_music_url":""}
    checks = [apple_search(title,artist), spotify_search(title,artist), youtube_music_search(title,artist)]
    if any(x["state"] == "MATCH" for x in checks):
        status = "DISTRIBUTED / MATCH FOUND"
    else:
        verified = [x for x in checks if x["state"] == "NO_MATCH"]
        failed = [x for x in checks if x["state"] == "ERROR"]
        status = "NOT DISTRIBUTION" if len(verified) >= 2 and not failed else "CHECK UNVERIFIED"
    return {"status":status,"apple":checks[0]["detail"],"spotify":checks[1]["detail"],
            "youtube_music":checks[2]["detail"],"apple_url":checks[0].get("url",""),
            "spotify_url":checks[1].get("url",""),"youtube_music_url":checks[2].get("url","")}

def render_result(row, c=None):
    title = row.get("title",""); artist = row.get("artist") or row.get("channel") or ""
    c = c or distribution_check(title,artist)
    cls = "dist" if c["status"].startswith("DISTRIBUTED") else ("notdist" if c["status"]=="NOT DISTRIBUTION" else "unverified")
    links = []
    if row.get("url"): links.append(f'<a href="{row["url"]}" target="_blank">▶ YouTube</a>')
    for label,key in [("🎧 Apple Music","apple_url"),("🟢 Spotify","spotify_url"),("🎵 YouTube Music","youtube_music_url")]:
        if c.get(key): links.append(f'<a href="{c[key]}" target="_blank">{label}</a>')
    links.append(f'<a href="https://www.google.com/search?q={quote_plus(title+" "+artist+" lyrics")}" target="_blank">📝 Lyrics Search</a>')
    st.markdown(f"""
<div class="resultbox"><div><b>🎵 {title}</b> <span class="badge {cls}">{c["status"]}</span></div>
<div class="smallmuted">Artist: {artist} • Views: {fmt_views(row.get("views",0))}</div>
<div style="margin-top:7px">Catalog: <b>{c["status"]}</b> &nbsp;|&nbsp; Apple: <b>{c["apple"]}</b> &nbsp;|&nbsp; Spotify: <b>{c["spotify"]}</b> &nbsp;|&nbsp; YouTube Music: <b>{c["youtube_music"]}</b></div>
<div class="linkrow" style="margin-top:9px">{" ".join(links)}</div></div>""", unsafe_allow_html=True)

st.sidebar.markdown("## 🎯 Research Center")
mode = st.sidebar.radio("Research mode",["🔥 Song Discovery","🔎 Artist Finder","📺 Channel Scanner","📝 Lyrics Finder","📚 History"],index=0)
st.sidebar.markdown("---")

if mode == "🔥 Song Discovery":
    song = st.sidebar.text_input("Song name (optional)",placeholder="e.g. Kahani Suno")
    artist = st.sidebar.text_input("Singer / Artist (optional)",placeholder="e.g. Kaifi Khalil")
    keyword = st.sidebar.text_input("Keyword / genre / language",placeholder="Any keyword")
    results_n = st.sidebar.number_input("Results",5,50,30,5)
    min_views = st.sidebar.number_input("Minimum views",0,100_000_000_000,100000,10000)
    max_views = st.sidebar.number_input("Maximum views (0 = unlimited)",0,100_000_000_000,0,10000)
    year = st.sidebar.number_input("Year / Old-song cutoff (0 = Any Year)",0,2100,0,1)
    noise = st.sidebar.checkbox("🚫 Hide remix/cover/reaction/movie noise",True)
    workers = st.sidebar.slider("⚡ Parallel research",1,8,6)
    st.sidebar.caption("Public catalog checks. Spotify is optional; unavailable checks never become NOT DISTRIBUTION.")

    st.markdown("## 🔎 Viral Song Discovery")
    st.caption("Use Song + Singer/Artist for the most accurate catalog matching.")
    st.markdown('<div class="bigbtn">',unsafe_allow_html=True)
    go = st.button("🚀 FAST FIND & RESEARCH SONGS",use_container_width=True)
    st.markdown("</div>",unsafe_allow_html=True)

    if go:
        search_text = f"{song} {artist}".strip() if song or artist else keyword
        if not search_text: st.warning("Enter a song + artist, or a keyword."); st.stop()
        if song and artist: queries=[f'"{song}" "{artist}"',f'{song} {artist} official',f'{song} {artist} song']
        elif song: queries=[song,f'{song} official song']
        else: queries=[keyword,f'{keyword} official song',f'{keyword} music']
        raw=[]
        for q in queries[:3]: raw.extend(yt_search(q,int(results_n)))
        seen=set(); rows=[]
        for x in raw:
            k=x["video_id"] or x["url"]
            if k in seen: continue
            seen.add(k)
            if x["views"] < min_views or (max_views and x["views"] > max_views): continue
            if noise and any(k in x["title"].lower() for k in ["reaction","cover","remix","trailer"]): continue
            if song and artist:
                t,a,s,ar=normalize(x["title"]),normalize(x["channel"]),normalize(song),normalize(artist)
                x["score"]=(60 if s and s in t else 0)+(35 if ar and (ar in t or ar in a) else 0)
            else: x["score"]=0
            x["artist"]=x["channel"]; rows.append(x)
        rows.sort(key=lambda z:(z["score"],z["views"]),reverse=True); rows=rows[:int(results_n)]

        checks=[None]*len(rows)
        progress=st.progress(0)
        def check_one(i,r):
            try: return i,distribution_check(r["title"],r["artist"])
            except Exception: return i,{"status":"CHECK UNVERIFIED","apple":"CHECK FAILED","spotify":"CHECK FAILED","youtube_music":"CHECK FAILED"}
        with ThreadPoolExecutor(max_workers=int(workers)) as ex:
            futures=[ex.submit(check_one,i,r) for i,r in enumerate(rows)]
            done=0
            for f in as_completed(futures):
                i,c=f.result(); checks[i]=c; done+=1; progress.progress(done/max(1,len(rows)))
        progress.empty()

        dist=sum(c["status"].startswith("DISTRIBUTED") for c in checks)
        notdist=sum(c["status"]=="NOT DISTRIBUTION" for c in checks)
        unv=len(rows)-dist-notdist
        cols=st.columns(4)
        for col,label,value in zip(cols,["🎵 Songs","📁 Distributed","📁 Not Distribution","⚠️ Unverified"],[len(rows),dist,notdist,unv]):
            col.markdown(f'<div class="card"><div>{label}</div><div class="n">{value}</div></div>',unsafe_allow_html=True)

        st.info("NOT DISTRIBUTION is shown only when at least two independent public catalog checks complete with no match. A missing/failed check is never treated as a negative.")
        if rows:
            df=pd.DataFrame([{"title":r["title"],"artist":r["artist"],"channel":r["channel"],"views":r["views"],
                              "published":r["published"],"url":r["url"],"catalog":checks[i]["status"],
                              "apple":checks[i]["apple"],"spotify":checks[i]["spotify"],"youtube_music":checks[i]["youtube_music"]}
                             for i,r in enumerate(rows)])
            st.download_button("⬇️ Download CSV",df.to_csv(index=False).encode(),"music_opportunity_v2_1.csv","text/csv")
            for i,r in enumerate(rows): render_result(r,checks[i])

elif mode == "🔎 Artist Finder":
    st.markdown("## 🔎 Artist Finder")
    artist=st.text_input("Artist / Singer name",placeholder="Type any artist name")
    n=st.number_input("Top songs to show",5,50,20,5)
    if st.button("🔎 FIND ARTIST SONGS",use_container_width=True):
        if not artist.strip(): st.warning("Enter an artist name."); st.stop()
        rows=yt_search(f'"{artist}" official song',int(n)*2)
        rows=[r for r in rows if normalize(artist) in normalize(r["channel"]+" "+r["title"])]
        rows=sorted(rows,key=lambda x:x["views"],reverse=True)[:int(n)]
        st.success(f"Found {len(rows)} matching public YouTube candidates for {artist}.")
        for r in rows: render_result({**r,"artist":artist})

elif mode == "📺 Channel Scanner":
    st.markdown("## 📺 Channel Scanner")
    channel_url=st.text_input("YouTube channel URL",placeholder="https://www.youtube.com/@ChannelName")
    n=st.number_input("Songs to scan",5,30,10,5)
    min_views=st.number_input("Minimum views",0,100_000_000_000,0,10000)
    if st.button("📺 SCAN CHANNEL SONGS",use_container_width=True):
        if not channel_url.strip(): st.warning("Enter a YouTube channel URL."); st.stop()
        handle=channel_url.rstrip("/").split("/")[-1]
        rows=yt_search(f'site:youtube.com "{handle}" song',int(n)*2) or yt_search(f'{handle} song',int(n)*2)
        rows=[r for r in rows if r["views"]>=min_views and normalize(handle.replace("@","")) in normalize(r["channel"]+" "+r["title"])]
        rows=rows[:int(n)]
        st.caption("Channel Scanner lists public song candidates and checks their public catalog evidence.")
        for r in rows: render_result(r)

elif mode == "📝 Lyrics Finder":
    st.markdown("## 📝 Lyrics Finder")
    song=st.text_input("Song name",placeholder="Type song name")
    artist=st.text_input("Singer / Artist name (optional)",placeholder="Optional")
    link=st.text_input("Song link (optional)",placeholder="https://youtube.com/watch?v=...")
    if st.button("📝 FIND LYRICS & SOURCES",use_container_width=True):
        if not song.strip(): st.warning("Enter song name."); st.stop()
        q=f'"{song}" "{artist}" lyrics' if artist else f'"{song}" lyrics'
        hits=web_search(q,10)
        st.success(f"Found {len(hits)} public lyric/search sources.")
        for h in hits:
            st.markdown(f'**[{h["title"]}]({h["url"]})**')
            if h["snippet"]: st.caption(h["snippet"])
        if link: st.markdown(f'▶ [Open song link]({link})')
        st.info("This finder returns public lyric/source links rather than reproducing copyrighted lyrics.")

else:
    st.markdown("## 📚 History")
    st.info("History is session-based in this version. Persistent history can be added later.")

st.markdown("---")
st.caption(f"{APP_TITLE} • Public catalog research only • No API keys required by default")
