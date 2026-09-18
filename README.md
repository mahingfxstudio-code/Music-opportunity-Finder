# Music Opportunity Finder V2.1

V1-style UI preserved with a safer and faster catalog-check workflow.

### Important fixes
- Song + Singer/Artist matching is prioritized for better search accuracy.
- Apple Music/iTunes public catalog check works without an API key.
- Spotify is optional; if credentials are missing it is **UNVERIFIED**, never falsely marked as NOT DISTRIBUTION.
- YouTube Music public evidence is conservative.
- **NOT DISTRIBUTION** appears only after at least two independent public catalog checks complete with no match.
- Failed/unavailable checks become **CHECK UNVERIFIED**, not a false negative.
- Catalog checks run in parallel to reduce waiting time.
- Counts now separate Distributed / Not Distribution / Unverified correctly.
- V1-style dark/purple UI is retained.

### Deploy
Replace `app.py` and `requirements.txt` in your GitHub repository and commit the changes. Streamlit Community Cloud monitors the connected repository and normally reflects committed code changes automatically.
