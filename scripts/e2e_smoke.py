"""End-to-end smoke test against a running backend (uses the real LLM; about 5 calls).

    backend/.venv/bin/python scripts/e2e_smoke.py [--api http://127.0.0.1:8000] [--sample eval/samples/rx_typed_english.png] [--keep]

Registers a throwaway account and patient, uploads a sample, waits for the pipeline, confirms the review,
then checks the record, FHIR bundles, a Hindi summary, the chat, the mock ABHA flow and that a second
account cannot see any of it. The accounts are deleted at the end unless --keep is given.
"""

import argparse
import mimetypes
import secrets
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def register(c: httpx.Client, name: str, email: str, password: str) -> httpx.Response:
    """Sign up with the email code (needs a local server without an email provider, which returns the code)."""
    sent = c.post("/api/auth/register/start", json={"name": name, "login": email, "password": password})
    if sent.status_code != 200 or "dev_code" not in sent.json():
        sys.exit(f"sign-up needs a local server without GOOGLE_SCRIPT_URL: {sent.text}")
    return c.post("/api/auth/register/verify", json={"email": email, "code": sent.json()["dev_code"]})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--sample", type=Path, default=ROOT / "eval/samples/rx_typed_english.png")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    c = httpx.Client(base_url=args.api, timeout=180)
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
        if not ok:
            failures.append(label)

    health = c.get("/api/health").json()
    print(f"backend ok · provider {health['llm_provider']} · models {health['models']}")
    password = secrets.token_urlsafe(12)
    login = f"e2e-{secrets.token_hex(4)}@example.com"
    print("accounts")
    check("protected API needs sign-in", c.get("/api/patients").status_code == 401)
    reg = register(c, "E2E Smoke Test", login, password)
    check("register signs in", reg.status_code == 200 and c.get("/api/auth/me").status_code == 200, login)
    if reg.status_code != 200:
        return 1
    other = httpx.Client(base_url=args.api, timeout=60)
    register(other, "Other", "x" + login, password).raise_for_status()
    pid = c.post("/api/patients", json={"name": "E2E Smoke Test", "gender": "male", "birth_date": "1980-01-01"}).json()["id"]
    try:
        print("upload + pipeline")
        mime = mimetypes.guess_type(args.sample.name)[0]
        up = c.post(f"/api/patients/{pid}/documents", files={"files": (args.sample.name, args.sample.read_bytes(), mime)})
        check("upload accepted", up.status_code == 200, str(up.status_code))
        did = up.json()[0]["id"] if isinstance(up.json(), list) else up.json()["documents"][0]["id"]
        t0 = time.time()
        while True:
            doc = c.get(f"/api/documents/{did}").json()
            if doc["status"] in ("review", "failed") or time.time() - t0 > 300:
                break
            time.sleep(2)
        stages = " → ".join(f"{s['stage']} {s['ms'] / 1000:.1f}s" for s in doc.get("pipeline_log") or [])
        check("pipeline reached review", doc["status"] == "review", f"{time.time() - t0:.0f}s · {stages} {doc.get('error') or ''}")
        if doc["status"] != "review":
            return 1
        rv = doc["review"]
        st = rv["stats"]
        check("items extracted", st["items_total"] > 0,
              f"{len(rv['medications'])} medicines, {len(rv['observations'])} observations, {len(rv['conditions'])} conditions, {st['needs_review']} flagged")

        print("confirm")
        conf = c.post(f"/api/documents/{did}/confirm", json=rv)
        check("confirm saved records", conf.status_code == 200 and sum(conf.json()["saved"].values()) > 0, str(conf.json().get("saved")))
        meds = c.get(f"/api/patients/{pid}/medications").json()
        statuses = [m["status"] for m in (meds if isinstance(meds, list) else meds.get("active", []) + meds.get("past", []))]
        check("medicines in the record", len(statuses) > 0, f"{statuses.count('active')} active, {statuses.count('completed')} completed by duration")
        tl = c.get(f"/api/patients/{pid}/timeline").json()
        check("timeline has the document", len(tl) > 0 if isinstance(tl, list) else bool(tl))

        print("FHIR")
        r = c.get(f"/api/documents/{did}/fhir").json()
        b = r["bundle"]
        types = sorted({e["resource"]["resourceType"] for e in b.get("entry", [])})
        check("document bundle validates", b.get("type") == "document" and "Composition" in types and not r["validation_errors"], ", ".join(types))
        pb = c.get(f"/api/patients/{pid}/fhir").json()
        pb = pb.get("bundle", pb)
        check("patient export bundle", pb.get("resourceType") == "Bundle" and len(pb.get("entry", [])) > 0, f"{len(pb.get('entry', []))} entries")

        print("summary + chat")
        s = c.get(f"/api/documents/{did}/summary", params={"lang": "hi"})
        sj = s.json() if s.status_code == 200 else {}
        check("Hindi document summary", s.status_code == 200 and bool(sj.get("headline") or sj.get("overview")),
              f"{s.status_code} · safety {sj.get('safety')}" if s.status_code == 200 else s.text[:160])
        ch = c.post(f"/api/patients/{pid}/chat", json={"message": "What medicines am I taking and when?", "lang": "en"})
        cj = ch.json() if ch.status_code == 200 else {}
        check("chat answers with citations", ch.status_code == 200 and len(cj.get("citations", [])) > 0,
              f"{len(cj.get('citations', []))} citations" if ch.status_code == 200 else ch.text[:160])
        em = c.post(f"/api/patients/{pid}/chat", json={"message": "I have severe chest pain right now", "lang": "en"})
        check("emergency notice", em.status_code == 200 and bool(em.json().get("emergency_notice")))

        print("mock ABHA")
        init = c.post(f"/api/patients/{pid}/abha/init", json={"abha_address": "e2e.smoke@abdm"}).json()
        ok = c.post(f"/api/patients/{pid}/abha/confirm", json={"txn_id": init["txn_id"], "otp": "123456"})
        check("ABHA link with OTP", ok.status_code == 200)
        imp = c.post(f"/api/patients/{pid}/abha/import", json={})
        check("HIP import", imp.status_code == 200, str({k: v for k, v in imp.json().items() if k != "consent"})[:160])

        print("privacy")
        seen = [other.get(u).status_code for u in (f"/api/patients/{pid}", f"/api/documents/{did}", f"/api/documents/{did}/file")]
        check("other account gets 404", seen == [404, 404, 404] and other.get("/api/patients").json() == [], str(seen))
    finally:
        if not args.keep:
            c.post("/api/auth/delete-account", json={"password": password})
            other.post("/api/auth/delete-account", json={"password": password})
    print(f"\n{'ALL PASSED' if not failures else 'FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
