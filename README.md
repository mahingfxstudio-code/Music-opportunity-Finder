# Music Opportunity Finder V1 — Updated

Fast V1-style music research web app with the original V1 UI preserved.

## Included
- Original V1-style dark Research Center UI.
- Fast parallel public YouTube search using `yt-dlp` — no YouTube API key required for the default workflow.
- **CATALOG 1 — DISTRIBUTED / MATCH FOUND**
- **CATALOG 2 — NOT DISTRIBUTION**
- Song YouTube link, channel link, Spotify search, Apple Music, YouTube Music and lyrics-search links.
- Artist Finder: searches an artist/singer and surfaces top/high-view matching songs.
- Channel Scanner: reads a channel's videos directly and checks public catalog/distribution clues for the songs.
- Lyrics Finder: Song Name required; Singer/Artist optional; Song Link optional; links to public lyric sources.
- Any Year or numeric year/cutoff.
- Any keyword, singer, channel, year or number can be typed into the search field.
- Minimum/maximum views, result count, noise filtering and parallel-worker control.
- CSV + JSON export.
- Local research history.

## Important
`NOT DISTRIBUTION` only means that the public checks used by this app did not show an obvious distribution/catalog match. It is **not** proof that a recording is unowned, copyright-free, or legally available for distribution. Verify master, publishing, label, licensing and ownership rights before using a song.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```
