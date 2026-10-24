# VainahNews — Python deployment starter

Python Flask news website, Russian-language worldwide RSS, search, articles, and password-protected editor.

### Render
- Type: Web Service / Python
- Root directory: leave empty
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn --bind 0.0.0.0:$PORT app:app`
- Plan: Free
- Set Environment variables: `SECRET_KEY` (random, keep fixed), `ADMIN_PASSWORD` (unique password), `COOKIE_SECURE=1`.
- After deploying, open `/admin` and click **Обновить RSS** for the first batch.

### Important limitations of Free Render
The free instance sleeps when inactive. Its local storage is ephemeral: the default SQLite file in `/tmp` will NOT persist across restarts/deploys. Use a persistent external Postgres database before storing important editorial content. This starter does not yet have a Postgres adapter. Do not rely on stored data in this prototype.

The RSS sources are fetched on manual admin action. Continuous 5-minute refresh is NOT enabled in this Render starter: use a separate scheduler/database before claiming that functionality. Some RSS feeds or images may be blocked or inaccessible.

RSS descriptions are typically short; the site links to full originals. Do not duplicate copyrighted texts/images without permission.

### Local run
`pip install -r requirements.txt`, set `SECRET_KEY` and `ADMIN_PASSWORD`, then `python app.py`. Open http://127.0.0.1:5050
