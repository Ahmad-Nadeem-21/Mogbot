"""Production WSGI entrypoint. Run with a real server, not `python main.py`:

    gunicorn wsgi:app

`python main.py` (Flask's dev server) stays for local development only.
"""

from __future__ import annotations

from backend.app import create_app
from main import MogBotFloorManager

app = create_app(MogBotFloorManager())
