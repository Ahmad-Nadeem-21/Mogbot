"""Production WSGI entrypoint for MogBot.

`backend.app.create_app()` is a factory - it needs a MogBotFloorManager
instance, so it can't be gunicorn's target directly. This module builds
that instance once at import time and exposes the resulting Flask app as
`app`, the way gunicorn expects (`gunicorn backend.wsgi:app`).

See ACTION_PLAN.md Milestone 10 - this replaces the Werkzeug dev server
(`main.py`'s `flask_app.run(...)`) for a real deployment.
"""

from __future__ import annotations

from backend.app import create_app
from main import MogBotFloorManager

app = create_app(MogBotFloorManager())
