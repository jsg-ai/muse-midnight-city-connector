#!/usr/bin/env python3
"""Midnight City Muse connector facade. Stdlib only.

Design rules (see ../PLAN.md, SECURITY posture):
- The caller's Midnight City owner token and the control-session lease are
  used only in memory for the single upstream request that needs them.
  Nothing credential-shaped is stored, logged, or returned except the lease
  the game itself issues (which the caller needs for follow-up calls, the
  same shape as the official helper).
- Server-side tier enforcement: read routes, game-write routes, and
  in-game value routes are separate allowlists. Value routes require an
  explicit per-call confirmation flag.
- Upstream is only https://midnight.city/observer. No redirects followed.
- Audit log records timestamps, routes, tier, outcome status only.
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = "https://midnight.city/observer"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
AUDIT_PATH = os.environ.get("MIDNIGHT_AUDIT", "/var/log/midnight-api/audit.jsonl")
MAX_BODY = 32 * 1024
MAX_RESP = 512 * 1024

READ_KINDS = {"context", "inventory", "needs", "progression"}
ACTION_WRITE = {  # Tier 2: game writes, no in-game value transfer
    "move_to", "move-area", "move_area", "travel-district", "enter-building",
    "exit-building", "work", "perform_job", "gather", "harvest", "craft",
    "equip", "unequip", "use-item", "use_item", "eat", "eat_well", "sleep",
    "speak", "engage", "event-action", "attack",
}
ACTION_VALUE = {  # Tier 3: in-game value moves, confirmation required
    "trade", "send-crystal", "send_crystal", "deliver-contract",
    "deliver_contract", "buy", "sell",
}

_buckets = defaultdict(deque)
_audit_lock = __import__("threading").Lock()


def rate_ok(key, limit=12, window=60.0):
    now = time.time()
    q = _buckets[key]
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def audit(route, tier, status):
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "route": route, "tier": tier, "status": status}
    try:
        with _audit_lock:
            os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
            with open(AUDIT_PATH, "a") as f:
                f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def upstream(method, path, bearer=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(UPSTREAM + path, data=data, method=method)
    req.add_header("User-Agent", UA)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if bearer:
        req.add_header("Authorization", f"Bearer {bearer}")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a):
            raise RuntimeError("redirect refused")

    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=25) as r:
            raw = r.read(MAX_RESP + 1)
            return r.status, raw[:MAX_RESP]
    except urllib.error.HTTPError as e:
        return e.code, e.read(MAX_RESP)


def as_json(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"upstream_raw": raw[:300].decode("utf-8", errors="replace")}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # keep tokens and query strings out of logs
        pass

    def send_json(self, code, obj):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def bearer(self):
        h = self.headers.get("Authorization", "")
        return h[7:].strip() if h.lower().startswith("bearer ") else None

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return None
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return None

    # -- routes ---------------------------------------------------------
    def do_GET(self):
        path, _, qs = self.path.partition("?")
        if path in ("/api/", "/api/status"):
            audit(path, 0, 200)
            return self.send_json(200, {
                "ok": True, "service": "midnight-city-connector",
                "version": "0.1.0",
                "upstream": UPSTREAM,
                "networks": ["preview", "preprod"],
                "mainnet": "blocked",
                "docs": "https://midnight.hyperkind.net/apidocs/",
            })
        if path == "/api/openapi.json":
            here = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "openapi.json")
            try:
                with open(here, "rb") as f:
                    payload = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except OSError:
                self.send_json(500, {"error": "spec_unavailable"})
            return
        if path == "/api/leaderboards":
            board = ""
            for part in qs.split("&"):
                if part.startswith("board="):
                    board = part[6:]
            suffix = ("?board=" + urllib.request.quote(board)) if board else ""
            code, raw = upstream("GET", "/api/leaderboards" + suffix)
            audit(path, 0, code)
            return self.send_json(code, as_json(raw))
        if path == "/api/merchants":
            code, raw = upstream("GET", "/api/skill/merchants")
            audit(path, 0, code)
            return self.send_json(code, as_json(raw))
        m = re.fullmatch(r"/api/agents/([^/]+)/(context|inventory|needs|progression)", path)
        if m:
            lease = self.bearer()
            if not lease:
                return self.send_json(401, {"error": "lease_required",
                                            "hint": "POST /api/session first"})
            code, raw = upstream("GET", f"/api/skill/agents/{m.group(1)}/{m.group(2)}",
                                 bearer=lease)
            audit(path, 1, code)
            return self.send_json(code, as_json(raw))
        return self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        path = self.path.partition("?")[0]
        body = self.read_body()
        if body is None:
            return self.send_json(400, {"error": "bad_or_oversized_json"})
        if path == "/api/claimable":
            token = self.bearer()
            if not token:
                return self.send_json(401, {"error": "owner_token_required"})
            code, raw = upstream("GET", "/api/local-control/claimable", bearer=token)
            audit(path, 1, code)
            return self.send_json(code, as_json(raw))
        if path == "/api/session":
            token = self.bearer()
            agent = str(body.get("agentId", ""))
            if not token:
                return self.send_json(401, {"error": "owner_token_required"})
            if not agent:
                return self.send_json(400, {"error": "agentId_required"})
            code, raw = upstream("POST", "/api/local-control/session", bearer=token,
                                 body={"agentId": agent,
                                       "clientInstanceId": "hyperkind-connector",
                                       "modelId": "muse"})
            audit(path, 1, code)
            return self.send_json(code, as_json(raw))
        if path == "/api/session/release":
            lease = self.bearer()
            if not lease:
                return self.send_json(401, {"error": "lease_required"})
            code, raw = upstream("POST", "/api/local-control/session/release",
                                 bearer=lease, body=body or {})
            audit(path, 1, code)
            return self.send_json(code, as_json(raw) if raw.strip() else {"ok": True})
        if path == "/api/actions":
            lease = self.bearer()
            if not lease:
                return self.send_json(401, {"error": "lease_required"})
            kind = str(body.get("kind", ""))
            if kind in ACTION_VALUE:
                tier = 3
                if body.get("confirm") is not True:
                    audit(path, tier, 428)
                    return self.send_json(428, {
                        "error": "confirmation_required",
                        "detail": "Tier 3 (in-game value) actions require "
                                  "\"confirm\": true in the request body, set "
                                  "only after the user approves the exact "
                                  "merchant/recipient, item, and quantity."})
            elif kind in ACTION_WRITE:
                tier = 2
            else:
                audit(path, 2, 403)
                return self.send_json(403, {"error": "action_not_allowlisted",
                                            "kind": kind})
            ip = self.client_address[0]
            if not rate_ok(f"actions:{ip}"):
                audit(path, tier, 429)
                return self.send_json(429, {"error": "rate_limited",
                                            "limit": "12 actions/minute"})
            code, raw = upstream("POST", "/api/actions", bearer=lease, body=body)
            audit(path, tier, code)
            return self.send_json(code, as_json(raw))
        return self.send_json(404, {"error": "not_found"})


if __name__ == "__main__":
    port = int(os.environ.get("MIDNIGHT_API_PORT", "8799"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
