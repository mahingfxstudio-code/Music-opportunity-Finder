# 🎵 Music Opportunity Finder V1.3 — FAST FIXED

V1-style UI preserved, with safer public-catalog classification and faster search behavior.

## What was fixed
- **V1 UI kept** — Research Center sidebar + dark purple/red design.
- **Song search accepts any keyword** plus optional **Singer / Artist**.
- Search uses **song + singer/artist together** when supplied, improving relevance.
- **Artist Finder** keeps exact-name relevance filtering before catalog checks.
- **Channel Scanner** reads the supplied YouTube channel directly and shows its songs with YouTube/channel links.
- **Lyrics Finder** uses Song Name + optional Singer/Artist + optional Song Link and provides public lyric-search links.
- **Catalog 1 — DISTRIBUTED / MATCH FOUND** only when a strong Apple/iTunes public catalog match is found.
- **Catalog 2 — NOT DISTRIBUTION** when no strong Apple/iTunes match is found.
- Spotify and YouTube Music are shown as **SEARCH ONLY** links, so a search page is not falsely treated as proof of distribution.
- Apple title matching now uses normalized titles + similarity and artist matching to reduce false results.
- Faster YouTube search limits and retry handling.
- Any Year / custom year, min/max views, result count, noise filter and parallel workers remain.
- CSV + JSON export and local history remain.
- **No YouTube/Spotify API key is required for the default workflow.**

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud
Upload/replace `app.py`, `requirements.txt`, and `README.md` in the GitHub repo. Streamlit Cloud will redeploy from `app.py`.

## Important
**NOT DISTRIBUTION does not mean copyright-free, unowned, or legally available for distribution.** It only means that this app did not find a strong Apple/iTunes public-catalog match. Always verify the exact recording, master, composition, publishing, label and licensing rights before using a song.
