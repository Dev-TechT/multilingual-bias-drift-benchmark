"""Reference server for connecting YOUR OWN AI via the `mbdb.generate.v1` JSON contract.

Run:   python examples/custom/my_ai_server.py --port 9001
Use:   fillblank-run --provider http-json --base-url http://127.0.0.1:9001/generate --model my-ai-v1
       (web app: provider "Your own AI (HTTP JSON contract)")

Replace `generate()` with a call to your model (internal API, local model, agent, RAG pipeline, ...).
Only the Python standard library is used, so this runs anywhere.
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_KEY = os.environ.get("MY_AI_SERVER_KEY")  # optional: require "Authorization: Bearer <key>"


def generate(prompt: str, system_prompt: str, max_tokens: int, temperature: float | None) -> dict:
    """Call your model here and return {"text": "..."}.

    Optional fields: {"refused": true} if your model refused, {"content_filtered": true} if a safety filter blocked it.
    """
    return {"text": "The scenario does not provide enough information to determine that."}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep prompts out of logs
        pass

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/generate":
            return self._send(404, {"error": "not found"})
        if API_KEY and self.headers.get("Authorization") != f"Bearer {API_KEY}":
            return self._send(401, {"error": "unauthorized"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "invalid JSON"})
        if body.get("schema") != "mbdb.generate.v1" or not isinstance(body.get("prompt"), str):
            return self._send(400, {"error": "expected schema mbdb.generate.v1 with a prompt"})
        self._send(200, generate(body["prompt"], body.get("system_prompt", ""), int(body.get("max_tokens") or 256), body.get("temperature")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9001)
    args = parser.parse_args()
    print(f"mbdb.generate.v1 server on http://{args.host}:{args.port}/generate")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
