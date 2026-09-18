# Music Opportunity Finder V2

V1 UI preserved, with improved Song Discovery matching.

## V2 improvements
- Exact **Song Name + Singer/Artist Name** search mode.
- Multiple targeted YouTube queries for the pair.
- Candidate relevance scoring prioritizes title + artist/channel agreement.
- Distributed / NOT DISTRIBUTION two-catalog workflow retained.
- Artist Finder, Channel Scanner, Lyrics Finder and History retained.
- Public-search workflow does not require YouTube/Spotify API keys by default.

## Run
```bash
pip install -r requirements.txt
streamlit run app.py
```

Catalog status is public-search evidence only and is not legal rights clearance.
