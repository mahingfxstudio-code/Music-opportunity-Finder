# Music Opportunity Finder V1.1

Updated from the V1 UI. The V1 visual layout and workflow are preserved.

## Fixed
- Stronger Song + Artist matching
- Apple Music/iTunes direct public catalog check
- Spotify public web search check (no Spotify app/SDK)
- YouTube Music public web search check
- `CHECK UNVERIFIED` when a public check fails
- `NOT DISTRIBUTION` only after all three checks complete successfully with no obvious exact match
- Parallel catalog checking for speed
- Direct channel scanning using YouTube channel URL/@handle
- Artist Finder, Lyrics Finder, History, CSV and JSON
- Bengali Unicode-friendly normalization
- No API key required for the default workflow

## Deploy
Replace `app.py` and `requirements.txt` in the GitHub repository and commit.

## Important
NOT DISTRIBUTION means only that the public catalog checks used by this app did not reveal an obvious exact match. It is not proof that a recording is copyright-free, unowned, or legally available for distribution. Verify master, composition, publishing, label, and licensing rights.
