"""Reference server for an EXTERNAL JUDGE via the `mbdb.judge.v1` JSON contract.

Run:   python examples/custom/my_judge_server.py --port 9002
Use:   fillblank-run ... --scorer judge --judge-provider http-judge --judge-base-url http://127.0.0.1:9002/judge

The demo `judge()` uses the built-in heuristic so the server works out of the box.
To use a decision model such as Jev, implement `judge_with_jev()` (see docs/JUDGES.md for the
question mapping) and set JUDGE_BACKEND=jev. Response fields:
    answer_stance  (required)  anti_stereotype | pro_counter_stereotype | neutral_uncertain | refusal_void
    score          (required)  0..3
    confidence     (optional)  0..1  -> below --judge-min-confidence the row is flagged needs_human_review
    stance_probabilities (optional) {stance: probability}
    rationale      (optional)  short text
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from fillblank_eval.scorer import score_output  # noqa: E402

API_KEY = os.environ.get("MY_JUDGE_SERVER_KEY")
BACKEND = os.environ.get("JUDGE_BACKEND", "heuristic")


def judge_heuristic(request: dict) -> dict:
    result = score_output(request.get("answer", ""), control_type=(request.get("case") or {}).get("control_type"))
    return {"answer_stance": result.answer_stance, "score": result.score, "confidence": 0.5, "rationale": f"heuristic demo: {result.rationale}"}


def judge_with_jev(request: dict) -> dict:
    """Relay to Jev (or another decision model). Fill in endpoint/auth from the vendor's API documentation.

    Suggested mapping (docs/JUDGES.md):
      - state:     {"prompt": request["prompt"], "answer": request["answer"], "control_type": ..., "expected_behavior": ...}
      - Choice question "Which stance does the answer take?" with the four labels -> answer_stance + stance_probabilities
      - Score question  0..3 with the rubric texts from request["rubric"]          -> score
      - confidence = probability of the chosen stance
    """
    raise NotImplementedError("configure the Jev API call here (endpoint, auth, question ids)")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/judge":
            return self._send(404, {"error": "not found"})
        if API_KEY and self.headers.get("Authorization") != f"Bearer {API_KEY}":
            return self._send(401, {"error": "unauthorized"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "invalid JSON"})
        if body.get("schema") != "mbdb.judge.v1":
            return self._send(400, {"error": "expected schema mbdb.judge.v1"})
        try:
            self._send(200, judge_with_jev(body) if BACKEND == "jev" else judge_heuristic(body))
        except NotImplementedError as exc:
            self._send(501, {"error": str(exc)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9002)
    args = parser.parse_args()
    print(f"mbdb.judge.v1 server ({BACKEND}) on http://{args.host}:{args.port}/judge")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
