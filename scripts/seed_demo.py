"""Create a demo account and patient through the API (backend must be running).

    backend/.venv/bin/python scripts/seed_demo.py                       # account + patient + ABHA link + 4 mock-HIP records (no LLM calls)
    backend/.venv/bin/python scripts/seed_demo.py --confirm lab_diabetes_lipid_pdf,rx_handwritten_diabetes \
                                                  --review rx_handwritten_photo   # also upload samples (uses the LLM)

Documents passed to --confirm are uploaded and confirmed as extracted; --review ones are left waiting
on the review screen for a live demo. The script signs in to --login (creating the account if needed);
sign in to the web app with the same login and password to see the data.
"""

import argparse
import mimetypes
import sys
import time
from pathlib import Path

import httpx

SAMPLES = Path(__file__).resolve().parents[1] / "eval" / "samples"


def upload(c: httpx.Client, pid: str, sample: str) -> str:
    path = next(p for p in SAMPLES.glob(f"{sample}.*") if p.suffix != ".json")
    r = c.post(f"/api/patients/{pid}/documents", files={"files": (path.name, path.read_bytes(), mimetypes.guess_type(path.name)[0])})
    r.raise_for_status()
    return r.json()[0]["id"]


def wait(c: httpx.Client, did: str) -> dict:
    for _ in range(200):
        d = c.get(f"/api/documents/{did}").json()
        if d["status"] in ("review", "failed"):
            return d
        time.sleep(2)
    raise TimeoutError(did)


def register(c: httpx.Client, name: str, login: str, password: str) -> httpx.Response:
    """Sign up with the email code. Local servers without an email provider return the code; otherwise ask for it."""
    email = login if "@" in login else input(f"email for {login}: ").strip()
    first, _, last = name.partition(" ")
    sent = c.post("/api/auth/register/start", json={"first_name": first, "last_name": last or first, "email": email,
                                                    "password": password})
    if sent.status_code != 200:
        return sent
    code = sent.json().get("dev_code") or input(f"code emailed to {email}: ").strip()
    return c.post("/api/auth/register/verify", json={"email": email, "code": code})


def sign_in(c: httpx.Client, login: str, password: str, name: str) -> None:
    r = c.post("/api/auth/login", json={"login": login, "password": password})
    if r.status_code == 401:
        r = register(c, name, login, password)
    if r.status_code != 200:
        sys.exit(f"could not sign in as {login}: {r.text}")
    print(f"signed in as {login}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--login", default="demo@healthcopilot.in")
    ap.add_argument("--password", default="demo12345")
    ap.add_argument("--name", default="Ramesh Kumar")
    ap.add_argument("--abha", default="ramesh.kumar@abdm")
    ap.add_argument("--confirm", default="", help="comma-separated sample ids to upload and confirm")
    ap.add_argument("--review", default="", help="comma-separated sample ids to upload and leave in review")
    args = ap.parse_args()
    c = httpx.Client(base_url=args.api, timeout=180)
    sign_in(c, args.login, args.password, args.name)

    p = c.post("/api/patients", json={"name": args.name, "gender": "male", "birth_date": "1968-04-12",
                                      "phone": "9876543210", "preferred_language": "en"}).json()
    pid = p["id"]
    print(f"patient {args.name}: {pid}")
    txn = c.post(f"/api/patients/{pid}/abha/init", json={"abha_address": args.abha}).json()
    c.post(f"/api/patients/{pid}/abha/confirm", json={"txn_id": txn["txn_id"], "otp": txn.get("demo_otp_hint", "123456")}).raise_for_status()
    imp = c.post(f"/api/patients/{pid}/abha/import", json={}).json()
    print(f"ABHA {args.abha} linked · imported {len(imp['imported'])} records from the mock HIP")

    for sample in filter(None, args.confirm.split(",")):
        d = wait(c, upload(c, pid, sample))
        if d["status"] != "review":
            print(f"  {sample}: failed: {d.get('error')}")
            continue
        saved = c.post(f"/api/documents/{d['id']}/confirm", json=d["review"]).json()["saved"]
        print(f"  {sample}: confirmed {saved}")
    for sample in filter(None, args.review.split(",")):
        d = wait(c, upload(c, pid, sample))
        print(f"  {sample}: {d['status']} (open /documents/{d['id']}/review)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
