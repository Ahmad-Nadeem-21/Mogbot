"""Flask HTTP wrapper for the MogBot floor manager owned by main.py."""

from __future__ import annotations

import os
from typing import Any, Dict

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from core import llm_client

# Each POST /sessions triggers job_search + resume_analyzer + question_generator
# (up to 3 LLM calls); each POST /sessions/<id>/answers triggers evaluator and
# sometimes devils_advocate/helper review (up to 3 more). These defaults are
# deliberately conservative - override via env vars per deployment.
SESSION_RATE_LIMIT = os.environ.get("MOGBOT_SESSION_RATE_LIMIT", "10 per hour")
ANSWER_RATE_LIMIT = os.environ.get("MOGBOT_ANSWER_RATE_LIMIT", "60 per hour")

# Defaults to "*" for local dev. Set to the deployed frontend's exact origin
# (e.g. "https://mogbot.netlify.app") once it's known - see ACTION_PLAN.md
# Milestone 10.
ALLOWED_ORIGIN = os.environ.get("MOGBOT_ALLOWED_ORIGIN", "*")


def _request_json() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _json_response(result):
    payload, status_code = result
    return jsonify(payload), status_code


def create_app(
    floor_manager,
    *,
    session_rate_limit: str = SESSION_RATE_LIMIT,
    answer_rate_limit: str = ANSWER_RATE_LIMIT,
) -> Flask:
    app = Flask(__name__)

    # In-memory storage: fine for a single-process deployment (see
    # ACTION_PLAN.md Milestone 10). A multi-worker/multi-instance deployment
    # needs a shared backend (e.g. Redis) or limits will be per-process, not
    # per-user.
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[],
        headers_enabled=True,
    )

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(floor_manager.health())

    @app.route("/usage", methods=["GET"])
    def usage():
        """Cumulative LLM token usage this process has made, for spend visibility."""
        return jsonify(llm_client.get_usage_summary())

    @app.route("/sessions", methods=["POST", "OPTIONS"])
    @limiter.limit(session_rate_limit, methods=["POST"])
    def start_session():
        if request.method == "OPTIONS":
            return ("", 204)
        return _json_response(floor_manager.start_session(_request_json()))

    @app.route("/sessions/<session_id>", methods=["GET"])
    def get_session(session_id: str):
        return _json_response(floor_manager.get_session(session_id))

    @app.route("/sessions/<session_id>/inputs", methods=["GET"])
    def get_session_inputs(session_id: str):
        return _json_response(floor_manager.get_session_inputs(session_id))

    @app.route("/sessions/<session_id>/answers", methods=["POST", "OPTIONS"])
    @limiter.limit(answer_rate_limit, methods=["POST"])
    def submit_answer(session_id: str):
        if request.method == "OPTIONS":
            return ("", 204)
        return _json_response(floor_manager.submit_answer(session_id, _request_json()))

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

    return app


if __name__ == "__main__":
    print("Run `python main.py` from the repository root to start MogBot.")
