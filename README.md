# Music Opportunity Finder V2.1

V1-style UI preserved, with a faster public-search workflow and stronger Song + Artist matching.

## V2.1.1 catalog-check fix
- Apple Music/iTunes uses the public Search API directly (no key).
- Spotify is never guessed: it is checked only if optional `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` are configured.
- YouTube Music public search is checked conservatively.
- `CHECK UNVERIFIED` replaces false negative results when a check fails or is unavailable.
- `NOT DISTRIBUTION` is only returned after all enabled checks complete successfully with no match.

## Main changes
- V1-inspired dark UI
- Exact Song Name + Singer/Artist inputs
- Multiple targeted YouTube searches
- Public YouTube search via yt-dlp; no YouTube API key required by default
- Two catalog buckets: `DISTRIBUTED / MATCH FOUND` and `NOT DISTRIBUTION`
- Public evidence checks for Apple Music, Spotify and YouTube Music
- Artist Finder
- Channel Scanner
- Lyrics Finder with song + artist + optional link
- CSV export
- Flexible Any-style filters
- No database required

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Important
Catalog status is only public-web evidence. A `NOT DISTRIBUTION` result does not prove a recording is unowned, copyright-free, or legally available for distribution. Always verify master, publishing, label, licensing and ownership rights.
