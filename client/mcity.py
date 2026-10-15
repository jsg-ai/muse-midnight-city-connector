#!/usr/bin/env python3
"""Midnight City control CLI. Authenticated requests use the vault-stored
custom.midnight-city credential via authd surrogates; the raw key is never
visible here. Only talks to midnight.city."""

import json
import os
import sys
import urllib.request

# dynamic_credentials ships with the custom-connector-setup skill; its
# install path moved across deployments (2026-10-14: /opt/hatch/skills/
# skill-creator/bin vanished in a recycle and every driver died on
# import). Resolve the first candidate that actually holds the module.
for _cand in ("/opt/hatch/skills/skill-creator/bin",
              "/opt/muse/skills/custom-connector-setup/bin",
              "/opt/hatch/workflow-skills/custom-connector-setup/bin"):
    if os.path.exists(os.path.join(_cand, "dynamic_credentials.py")):
        sys.path.insert(0, _cand)
        break
from dynamic_credentials import (
    add_surrogate_to_request,
    read_json_response,
    DynamicCredentialError,
)

CREDENTIAL = "custom.midnight-city"
OBSERVER = "https://midnight.city/observer"
ALLOWED_HOSTS = ("midnight.city",)


def api_get(path):
    req = urllib.request.Request(OBSERVER + path, method="GET")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    add_surrogate_to_request(
        req, CREDENTIAL, allowed_hosts=ALLOWED_HOSTS
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return read_json_response(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"HTTP {e.code}: {body}")


def cmd_claimable():
    data = api_get("/api/local-control/claimable")
    ids = data.get("agentIds", []) if isinstance(data, dict) else []
    print(json.dumps({"agentIds": ids}, indent=2))


def cmd_leaderboards(board=""):
    path = "/api/leaderboards"
    if board:
        path += "?board=" + board
    # Leaderboards are public; no credential needed, but harmless to reuse api_get.
    # Use an unauthenticated fetch instead to avoid spending the credential.
    with urllib.request.urlopen(OBSERVER + path, timeout=20) as resp:
        data = read_json_response(resp)
    print(json.dumps(data, indent=2)[:2000])


def cmd_context(agent_id):
    data = api_get(f"/api/skill/agents/{agent_id}/context")
    print(json.dumps(data, indent=2)[:4000])


def api_post(path, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OBSERVER + path, data=body, method="POST")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    req.add_header("Content-Type", "application/json")
    add_surrogate_to_request(req, CREDENTIAL, allowed_hosts=ALLOWED_HOSTS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return read_json_response(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"HTTP {e.code}: {body}")


def lease_get(path, lease_token):
    req = urllib.request.Request(OBSERVER + path, method="GET")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    req.add_header("Authorization", f"Bearer {lease_token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return read_json_response(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"HTTP {e.code}: {body}")


def lease_post(path, lease_token, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OBSERVER + path, data=body, method="POST")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {lease_token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return read_json_response(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"HTTP {e.code}: {body}")


def cmd_shakedown(agent_id):
    import socket
    print("connecting...", flush=True)
    sess = api_post("/api/local-control/session", {
        "agentId": agent_id,
        "clientInstanceId": f"mcity-muse:{agent_id}:{socket.gethostname()}",
        "modelId": "muse-spark",
    })
    token = sess.get("token")
    if not token:
        raise SystemExit(f"no lease token in session response: {str(sess)[:300]}")
    print(f"connected: session {sess.get('sessionId')}", flush=True)
    try:
        out = {}
        for name in ("context", "inventory", "needs"):
            out[name] = lease_get(f"/api/skill/agents/{agent_id}/{name}", token)
        # compact summary
        ctx = out["context"] if isinstance(out["context"], dict) else {}
        inv = out["inventory"] if isinstance(out["inventory"], dict) else {}
        print(json.dumps({
            "agent": {k: ctx.get(k) for k in ("agentId", "name", "location", "area", "status") if k in ctx},
            "context_keys": sorted(ctx.keys())[:20],
            "inventory_keys": sorted(inv.keys())[:20],
            "needs": out["needs"],
        }, indent=2)[:3000])
    finally:
        try:
            lease_post("/api/local-control/session/release", token, {})
            print("disconnected (lease released)", flush=True)
        except SystemExit:
            print("warning: lease release failed", flush=True)


def public_get(path):
    req = urllib.request.Request(OBSERVER + path, method="GET")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return read_json_response(resp)


def tolerant_lease_post(path, lease_token, payload):
    """Like lease_post, but tolerates empty/non-JSON bodies (release acks)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(OBSERVER + path, data=body, method="POST")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {lease_token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            try:
                return json.loads(raw.decode("utf-8")) if raw.strip() else {"ok": True}
            except json.JSONDecodeError:
                return {"ok": True, "raw": raw[:200].decode("utf-8", errors="replace")}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        return {"http_error": e.code, "body": body}


EDIBLE = ("meat", "fish", "to_go_food", "matcha_smoothie")


def cmd_feed(agent_id):
    import socket, time
    print("connecting...", flush=True)
    sess = api_post("/api/local-control/session", {
        "agentId": agent_id,
        "clientInstanceId": f"mcity-muse:{agent_id}:{socket.gethostname()}",
        "modelId": "muse-spark",
    })
    token, session_id = sess.get("token"), sess.get("sessionId")
    if not token:
        raise SystemExit(f"no lease token: {str(sess)[:300]}")
    print("connected", flush=True)
    try:
        def get_inv():
            inv = lease_get(f"/api/skill/agents/{agent_id}/inventory", token)
            return inv.get("inventory", {}) if isinstance(inv, dict) else {}

        items = get_inv()
        crystal = items.get("crystal", 0)
        print(f"start: crystal={crystal} items={json.dumps(items)[:300]}", flush=True)

        # 1. earn crystal by working (hacker profession => automatic job)
        if crystal <= 0:
            print("working (perform_job)...", flush=True)
            wr = lease_post("/api/actions", token,
                            {"kind": "perform_job", "agentId": agent_id})
            print("work submitted:", json.dumps(wr)[:200], flush=True)
            for i in range(9):
                time.sleep(10)
                items = get_inv()
                crystal = items.get("crystal", 0)
                print(f"work poll {i+1}: crystal={crystal}", flush=True)
                if crystal > 0:
                    break

        # 2. buy cheapest edible food with crystal
        items = get_inv()
        crystal = items.get("crystal", 0)
        have_food = sum(items.get(f, 0) for f in EDIBLE)
        if have_food <= 0 and crystal > 0:
            merchants = public_get("/api/skill/merchants")
            mlist = merchants.get("merchants", merchants) if isinstance(merchants, dict) else merchants
            best = None
            for m in (mlist or []):
                offer = m.get("offer", {})
                if (offer.get("acceptsItemId") == "crystal" and offer.get("paysItemId") in EDIBLE
                        and offer.get("acceptsQuantity", 0) > 0 and offer.get("paysQuantity", 0) > 0
                        and crystal >= offer["acceptsQuantity"]):
                    rate = offer["acceptsQuantity"] / offer["paysQuantity"]
                    if best is None or rate < best[0]:
                        best = (rate, m.get("name"), offer)
            if best is None:
                print("OUTCOME: no affordable edible offer", flush=True)
                return
            _, mname, offer = best
            print(f"trading {offer['acceptsQuantity']} crystal at {mname} for {offer['paysItemId']}...", flush=True)
            tr = lease_post("/api/actions", token, {
                "kind": "trade", "merchantName": mname,
                "itemId": "crystal", "quantity": offer["acceptsQuantity"],
                "agentId": agent_id,
            })
            print("trade submitted:", json.dumps(tr)[:300], flush=True)
            time.sleep(10)
            items = get_inv()
            have_food = sum(items.get(f, 0) for f in EDIBLE)
            print(f"food_on_hand now={have_food} crystal={items.get('crystal')}", flush=True)

        # 3. eat
        items = get_inv()
        have_food = sum(items.get(f, 0) for f in EDIBLE)
        if have_food > 0:
            print("eating...", flush=True)
            er = lease_post("/api/actions", token, {"kind": "eat", "agentId": agent_id})
            print("eat submitted:", json.dumps(er)[:300], flush=True)
            for i in range(8):
                time.sleep(4)
                needs = lease_get(f"/api/skill/agents/{agent_id}/needs", token)
                hunger = needs.get("hunger") or {}
                val, state = hunger.get("value"), hunger.get("state")
                print(f"hunger check {i+1}: value={val} state={state}", flush=True)
                if isinstance(val, (int, float)) and val < 100:
                    print("OUTCOME: fed", flush=True)
                    break
            else:
                print("OUTCOME: still hungry after eating", flush=True)
        else:
            print("OUTCOME: no food to eat", flush=True)
    finally:
        r = tolerant_lease_post("/api/local-control/session/release", token,
                                {"sessionId": session_id})
        print(f"disconnected (release: {json.dumps(r)[:120]})", flush=True)


def cmd_supper(agent_id):
    """Wait for work to pay out, then buy food and eat. Bounded ~12 min."""
    import socket, time
    print("connecting...", flush=True)
    sess = api_post("/api/local-control/session", {
        "agentId": agent_id,
        "clientInstanceId": f"mcity-muse:{agent_id}:{socket.gethostname()}",
        "modelId": "muse-spark",
    })
    token, session_id = sess.get("token"), sess.get("sessionId")
    if not token:
        raise SystemExit(f"no lease token: {str(sess)[:300]}")
    print("connected", flush=True)
    try:
        def get_inv():
            inv = lease_get(f"/api/skill/agents/{agent_id}/inventory", token)
            return inv.get("inventory", {}) if isinstance(inv, dict) else {}

        # 1. wait for payday (up to ~10 min)
        crystal, have_food, items = 0, 0, {}
        for i in range(14):
            items = get_inv()
            crystal = items.get("crystal", 0)
            have_food = sum(items.get(f, 0) for f in EDIBLE)
            print(f"payday poll {i+1}: crystal={crystal} food={have_food}", flush=True)
            if crystal > 0 or have_food > 0:
                break
            time.sleep(45)
        else:
            print("OUTCOME: job has not paid yet", flush=True)
            return

        # 2. buy cheapest edible food
        if have_food <= 0 and crystal > 0:
            merchants = public_get("/api/skill/merchants")
            mlist = merchants.get("merchants", merchants) if isinstance(merchants, dict) else merchants
            best = None
            for m in (mlist or []):
                offer = m.get("offer", {})
                if (offer.get("acceptsItemId") == "crystal" and offer.get("paysItemId") in EDIBLE
                        and offer.get("acceptsQuantity", 0) > 0 and offer.get("paysQuantity", 0) > 0
                        and crystal >= offer["acceptsQuantity"]):
                    rate = offer["acceptsQuantity"] / offer["paysQuantity"]
                    if best is None or rate < best[0]:
                        best = (rate, m.get("name"), offer)
            if best is None:
                print("OUTCOME: no affordable edible offer", flush=True)
                return
            _, mname, offer = best
            print(f"trading {offer['acceptsQuantity']} crystal at {mname} for {offer['paysItemId']}...", flush=True)
            tr = lease_post("/api/actions", token, {
                "kind": "trade", "merchantName": mname,
                "itemId": "crystal", "quantity": offer["acceptsQuantity"],
                "agentId": agent_id,
            })
            print("trade submitted:", json.dumps(tr)[:300], flush=True)
            time.sleep(10)

        # 3. eat
        items = get_inv()
        have_food = sum(items.get(f, 0) for f in EDIBLE)
        if have_food > 0:
            print("eating...", flush=True)
            er = lease_post("/api/actions", token, {"kind": "eat", "agentId": agent_id})
            print("eat submitted:", json.dumps(er)[:300], flush=True)
            for i in range(8):
                time.sleep(4)
                needs = lease_get(f"/api/skill/agents/{agent_id}/needs", token)
                hunger = needs.get("hunger") or {}
                val, state = hunger.get("value"), hunger.get("state")
                print(f"hunger check {i+1}: value={val} state={state}", flush=True)
                if isinstance(val, (int, float)) and val < 100:
                    print("OUTCOME: fed", flush=True)
                    break
            else:
                print("OUTCOME: still hungry after eating", flush=True)
        else:
            print("OUTCOME: no food to eat", flush=True)
    finally:
        r = tolerant_lease_post("/api/local-control/session/release", token,
                                {"sessionId": session_id})
        print(f"disconnected (release: {json.dumps(r)[:120]})", flush=True)


COMMANDS = {
    "claimable": cmd_claimable,
    "leaderboards": cmd_leaderboards,
    "context": cmd_context,
    "shakedown": cmd_shakedown,
    "feed": cmd_feed,
    "supper": cmd_supper,
};


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print("usage: mcity.py <claimable|leaderboards [board]|context <agentId>", file=sys.stderr)
        return 2
    try:
        if argv[1] == "supper":
            cmd_supper(argv[2])
        elif argv[1] == "feed":
            cmd_feed(argv[2])
        elif argv[1] == "shakedown":
            cmd_shakedown(argv[2])
        elif argv[1] == "context":
            cmd_context(argv[2])
        elif argv[1] == "leaderboards":
            cmd_leaderboards(argv[2] if len(argv) > 2 else "")
        else:
            COMMANDS[argv[1]]()
    except DynamicCredentialError as e:
        print(f"credential error: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
