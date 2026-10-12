"""Admin commands.

    .venv/bin/python -m app.manage accounts                     # list accounts and their profiles
    .venv/bin/python -m app.manage assign-orphans <login>       # give profiles created before sign-in existed to an account
"""

import sys

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models.tables import Account, Patient
from app.services.auth import normalize_login


def main(argv: list[str]) -> int:
    init_db()
    with Session(engine) as db:
        if argv[:1] == ["accounts"]:
            for a in db.exec(select(Account).order_by(Account.created_at)).all():
                names = [p.name for p in db.exec(select(Patient).where(Patient.owner_id == a.id)).all()]
                print(f"{a.login:32s} {a.name:24s} profiles: {', '.join(names) or '-'}")
            orphans = db.exec(select(Patient).where(Patient.owner_id.is_(None))).all()  # type: ignore[union-attr]
            if orphans:
                print(f"\nprofiles without an account: {', '.join(p.name for p in orphans)}")
            return 0
        if argv[:1] == ["assign-orphans"] and len(argv) == 2:
            acc = db.exec(select(Account).where(Account.login == normalize_login(argv[1]))).first()
            if not acc:
                print(f"no account {argv[1]}; register it in the app first")
                return 1
            orphans = db.exec(select(Patient).where(Patient.owner_id.is_(None))).all()  # type: ignore[union-attr]
            for p in orphans:
                p.owner_id = acc.id
                db.add(p)
            db.commit()
            print(f"assigned {len(orphans)} profile(s) to {acc.login}: {', '.join(p.name for p in orphans) or '-'}")
            return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
