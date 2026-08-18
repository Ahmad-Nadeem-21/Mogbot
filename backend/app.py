"""Flask HTTP wrapper for the MogBot floor manager owned by main.py."""

from __future__ import annotations

from typing import Any, Dict

from flask import Flask, jsonify, request


def _request_json() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _json_response(result):
    payload, status_code = result
    return jsonify(payload), status_code


def create_app(floor_manager) -> Flask:
    app = Flask(__name__)

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        return response

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(floor_manager.health())

    @app.route("/sessions", methods=["POST", "OPTIONS"])
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
    def submit_answer(session_id: str):
        if request.method == "OPTIONS":
            return ("", 204)
        return _json_response(floor_manager.submit_answer(session_id, _request_json()))

    return app


if __name__ == "__main__":
    print("Run `python main.py` from the repository root to start MogBot.")
