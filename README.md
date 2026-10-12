# Health Copilot: AI-powered personal health copilot

Health Copilot turns photos and PDFs of prescriptions, lab reports and discharge summaries into a verified, unified
health record. It explains abnormal values in plain language, in English, Hindi, Telugu, Tamil or Kannada, and
exports everything as ABDM-ready FHIR R4 with a mock ABHA link.

*Built for the Altrix Labs hackathon, "AI-Powered Personal Health Copilot".*

![Dashboard](docs/screenshots/dashboard.png)

| | |
|---|---|
| ![Review](docs/screenshots/review.png) | ![Hindi summary](docs/screenshots/docview_hi.png) |
| Side-by-side review with confidence and verifier changes | Plain-language summary in Hindi |
| ![Trends](docs/screenshots/trends.png) | ![ABHA](docs/screenshots/abha.png) |
| Trends with reference ranges | Mock ABHA link and import, FHIR export |

## What it does

- **Ingest:** drag and drop, or use the phone camera. PDF, JPG, PNG and WEBP are accepted, multi-page documents
  included. Printed, handwritten, bilingual and regional-script documents all work.
- **Extract:** medicines with strength, dose, a morning/afternoon/night schedule, meal timing and duration; test
  values with units and reference ranges; diagnoses with ICD-10 codes; vitals; dates; doctor and facility.
- **Verify:**
  - A second model re-reads the page, guided by the validators' suspicious fields.
  - Code checks units, ranges, flags, drug names, dosage grammar, dates and plausibility.
  - A person confirms every document on a side-by-side review screen before anything is saved.
- **Explain:** plain-language summaries that cover what each abnormal result may mean, questions to ask the doctor,
  the medicine schedule and a glossary. They pass safety checks: no dosing advice, no diagnosis, and every number
  must come from the record. They are translated with all numbers preserved.
- **Unified profile:** dashboard, timeline, trends with shaded reference ranges, active and past medicines, and
  critical-value banners.
- **Ask my records:** chat grounded only in the patient's own records, with citations and emergency detection.
- **ABDM readiness:**
  - Every document becomes an NRCeS-profile FHIR R4 bundle, and the whole record exports as one bundle.
  - Mock ABHA flow: link with OTP, consent artefact, and import from a mock Health Information Provider.

**Measured accuracy** ([`eval/report.md`](eval/report.md)): on 10 synthetic documents with 96 items, the pipeline
with verification got 100% of 477 checked fields right; the single pass got 99.8%. The test set covers printed,
handwritten, phone-photo, PDF, Hindi, Telugu, Tamil and Kannada documents. This is a regression suite, not a
clinical validation; see the report for caveats.

Docs: [architecture](docs/architecture.md) · [slides](docs/slides.md) ([PDF](docs/slides.pdf)) · [3-minute demo script](docs/demo_script.md)

## Quick start (local development)

Requirements: Python 3.12, Node 22, and a [Gemini API key](https://aistudio.google.com/apikey). OpenAI also works.

```bash
# backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # then put your key in GEMINI_API_KEY
.venv/bin/uvicorn app.main:app --port 8000 --reload --reload-dir app

# frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
```

Or use the control script, which runs both servers in the background with logs in `.run/`:

`setup` also installs what the system is missing, as far as possible without touching the system:

- **Node 22:** uses an existing Node 20.19+/22.12+ (including nvm or volta installs); otherwise downloads the
  official build from nodejs.org into `.tools/node`.
- **Python 3.11–3.13 with venv:** uses the system Python; otherwise installs [uv](https://docs.astral.sh/uv/) in
  `~/.local/bin` and uses a standalone Python 3.12.
- **lsof, curl, python3-venv:** installed with apt when missing (asks for your sudo password).

It also works with `sudo ./run.sh setup`: only the apt packages are installed as root, and the project files stay
owned by you.

```bash
./run.sh setup                 # first time: system packages, virtualenv, pip and npm install, backend/.env
./run.sh start                 # backend :8000 + frontend :5173
./run.sh status
./run.sh restart [backend|frontend]
./run.sh logs [backend|frontend]
./run.sh stop
HOST=0.0.0.0 ./run.sh start    # open from a phone on the same Wi-Fi (camera upload)
```

After a `git pull`, just run `./run.sh restart`: start and restart first install any packages added to
`backend/requirements.txt` or `frontend/package-lock.json` since the last install.

### Accounts

Anyone can create an account with their first and last name, an email address and a password. After signing up, the
sign-in can be switched to a mobile number (any of 20 countries, India by default) in the account settings. Each account sees
only its own profiles and documents, and can hold several profiles, for example parents or children. Requests for
another account's records return 404. Sessions use an HttpOnly cookie (30 days), passwords are stored as scrypt
hashes, and repeated wrong passwords are throttled.

Every new account verifies its email with a 6-digit code before it is created (free SMS isn't available, so mobile
numbers aren't verified by text). The email is used to reset a forgotten password and,
if the user keeps them on, for security alerts (new sign-in, password or email changed), medicine-course reminders and
a weekly summary. Codes expire after 10 minutes, allow 5 tries, and at most 5 can be sent to an email per hour.
Accounts created before this see a reminder on the dashboard to add an email. Locally, without an email provider,
the code is shown on screen instead of being emailed.

To load a demo account (`demo@healthcopilot.in`, password `demo12345`) with a patient, an ABHA link and a year of
records (no LLM calls needed):

```bash
backend/.venv/bin/python scripts/seed_demo.py
# optionally also run real documents through the pipeline:
backend/.venv/bin/python scripts/seed_demo.py --confirm lab_diabetes_lipid_pdf,rx_handwritten_diabetes --review rx_handwritten_photo
# use your own account instead:
backend/.venv/bin/python scripts/seed_demo.py --login you@example.com --password '...'
```

The demo ABHA OTP is `123456`.

Profiles created before accounts existed have no owner and are hidden. Give them to an account with:

```bash
cd backend && .venv/bin/python -m app.manage accounts                      # list accounts and profiles
cd backend && .venv/bin/python -m app.manage assign-orphans demo@healthcopilot.in
```

### Docker

```bash
cp backend/.env.example backend/.env   # add your key
docker-compose up --build              # http://localhost:8080 (Postgres + backend + nginx frontend)
```

### Behind a TLS-inspecting corporate proxy

If HTTPS calls fail with certificate errors, for example behind Zscaler:

- **Backend:** point `CA_BUNDLE` in `backend/.env` at a PEM file that contains the system CAs plus the proxy's root CA.
- **npm:** set `NODE_EXTRA_CA_CERTS=/path/to/proxy-root.pem`.

## Deploy to Render (free)

Everything runs on free plans: a Render free web service, plus a **private GitHub repository** that keeps the
accounts, health records and uploaded files. A free Render service has no persistent disk: it forgets everything when
it restarts, redeploys or sleeps after 15 minutes without traffic. So at start-up the app restores its SQLite database
and files from that repository, and pushes a snapshot back about a minute after anything changes and again when it
shuts down. Each day keeps one commit, so the repository also gives you a daily history.

1. **Create the data repository.** On GitHub, create a new **private**, empty repository, for example
   `your-name/health-copilot-data` (no README or licence).
2. **Create a token for it.** In GitHub **Settings → Developer settings → Personal access tokens → Fine-grained
   tokens**, generate a token with **Repository access: Only select repositories** (pick the data repository) and
   **Permissions → Contents: Read and write**. Choose an expiry date and put a reminder in your calendar to renew it.
3. **Create the service.** In Render, choose **New → Blueprint**, connect this GitHub repository and pick the
   `main` branch. Render reads `render.yaml` and asks for:
   - `GEMINI_API_KEY`: your Gemini API key;
   - `DATA_REPO`: the data repository as `owner/name`, for example `your-name/health-copilot-data`;
   - `DATA_REPO_TOKEN`: the token from step 2.
4. **Deploy.** The first build takes a few minutes. The site is then at `https://health-copilot-<id>.onrender.com`,
   and every push to `main` redeploys it once the GitHub Actions checks (`.github/workflows/ci.yml`: backend
   tests, frontend lint and build) pass. A push that fails them is not deployed; the live site keeps running.

**Email (sign-up codes, password reset, alerts).** Emails are sent from your own Gmail by a small Google Apps Script
web app (free, about 100 emails a day). Render's free plan blocks SMTP, so the app reaches the script over HTTPS:

1. In Render, open the service's **Environment** tab and copy the generated `GOOGLE_SCRIPT_SECRET` value.
2. Signed in to the Gmail account that should send the emails, open [script.google.com](https://script.google.com),
   choose **New project**, replace the code with [`scripts/google-apps-script/Code.gs`](scripts/google-apps-script/Code.gs)
   and save.
3. Open **Project Settings** (gear icon) → **Script properties** → **Add script property**: name `SECRET`, value
   from step 1. Save.
4. **Deploy → New deployment**, pick type **Web app**, set **Execute as: Me** and **Who has access: Anyone**, then
   **Deploy**. Allow access when Google asks (it's your own script: **Advanced → Go to … (unsafe)** is expected).
   Copy the **Web app URL** (it ends in `/exec`).
5. Back in Render's **Environment** tab, add `GOOGLE_SCRIPT_URL` with that URL and save.

Until this is done, the live site can't send codes, so sign-up and password reset show "Email isn't set up on this
server yet". If you edit the script later, use **Deploy → Manage deployments → Edit → New version** so the URL stays
the same.

**Daily reminders and weekly summaries.** A sleeping free service runs no timers, so the scheduled GitHub Action
`.github/workflows/notify.yml` wakes it every day at 9 AM IST and runs the job. To turn it on, copy the
`CRON_SECRET` value Render generated (service **Environment** tab) and, in this GitHub repository's **Settings →
Secrets and variables → Actions**, add it as the secret `CRON_SECRET` and add the variable `APP_URL` with the site's
address (for example `https://health-copilot-kl7g.onrender.com`). Run it once by hand from the **Actions** tab to
check. GitHub pauses scheduled workflows after 60 days without commits; re-enable it from the Actions tab if that happens.

Good to know:

- The token is passed to git through environment variables only. It is never written to a URL, a file or the logs.
- If the data repository can't be read at start-up (wrong name, expired token), the app still starts but stops
  syncing, so an empty instance can never overwrite your data. The Render logs say so; fix the variable and redeploy.
- The first visit after the service has slept takes about a minute while Render starts it again.
- A change made in the last minute before a crash (not a normal stop) can be lost. Normal stops, redeploys and sleep
  always push a final snapshot.
- Keep the data repository private: it contains everyone's health records.
- GitHub warns about repositories over 1 GB and rejects files over 100 MB, which is far beyond a demo's needs.

## Configuration (`backend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | — | Required for extraction, summaries and chat |
| `GEMINI_EXTRACT_MODELS`, `GEMINI_VERIFY_MODELS`, `GEMINI_FAST_MODELS` | see `.env.example` | Comma-separated fallback chains per role. The first available model wins; quota or overload errors move to the next. Verification starts on a different model from extraction. |
| `ENABLE_VERIFICATION` | `true` | Turns the second-model read on or off |
| `DATABASE_URL` | SQLite in `backend/data` | e.g. `postgresql+psycopg://…` |
| `CA_BUNDLE` | — | Custom CA bundle for TLS-inspecting proxies |
| `SESSION_DAYS` | `30` | How long a sign-in lasts |
| `COOKIE_SECURE` | `false` | Set `true` when served over HTTPS |
| `STATIC_DIR` | — | Folder with the built frontend; the API then serves the website too (set in the `Dockerfile`) |
| `DATA_REPO` / `DATA_REPO_TOKEN` | — | Private GitHub repository (`owner/name`) and fine-grained token that keep the data; see [Deploy to Render](#deploy-to-render-free) |
| `DATA_REPO_BRANCH` | `main` | Branch for the data snapshots |
| `DATA_SYNC_SECONDS` | `60` | How often to check for changes to push |
| `GOOGLE_SCRIPT_URL` / `GOOGLE_SCRIPT_SECRET` | — | Google Apps Script web app that sends the emails, and its shared secret. Without a URL, local http:// servers show codes on screen; HTTPS servers refuse to send |
| `MAIL_FROM_NAME` | `Health Copilot` | Sender name on emails |
| `APP_URL` | Render's address, else `http://localhost:5173` | Used for links in emails |
| `CRON_SECRET` | — | Lets the daily GitHub Action run reminders and weekly summaries |

The **Gemini free tier allows only about 20 requests per model per day**. One document uses 3 requests (classify,
extract, verify), and each summary or chat answer uses one or two more. For demos and evaluation runs, use a key with
billing enabled.

## Tests and evaluation

```bash
cd backend && .venv/bin/python -m pytest -q        # 93 unit tests: validators, knowledge base, FHIR, ABHA, safety, records, data sync, email codes
backend/.venv/bin/python eval/make_samples.py      # regenerate the 10 synthetic documents + ground truth (deterministic)
backend/.venv/bin/python eval/run_eval.py         # run the pipeline on all samples and write eval/report.md (about 30 LLM calls)
backend/.venv/bin/python eval/run_eval.py --rescore eval/runs/<run>   # re-score saved outputs without LLM calls
backend/.venv/bin/python scripts/e2e_smoke.py      # end-to-end API check against a running backend (about 6 LLM calls)
```

## Project layout

```
backend/app/
  pipeline/    preprocess (PDF render, text layer, deskew, CLAHE) · extract (classify/extract/verify) · validate · runner · llm
  knowledge/   lab_ranges.json (60 LOINC tests) · drugs_india.csv (213 brands) · dosage_terms.json · icd10.json · mock HIP records
  fhir/        mapper (NRCeS profiles) · bundle (document bundles, patient export, FHIR import)
  services/    records (confirm + medicine reconciliation) · summary · chat · facts · safety · abha_mock
  api/         patients · documents · insights (summary, chat, ABHA)
  models/      SQLModel tables shaped like FHIR resources
frontend/src/  pages (Dashboard, Upload, Review, DocumentView, Timeline, Trends, Medications, Chat, Abha) · components · i18n (en, hi, te, ta, kn)
eval/          make_samples.py · samples/ (documents + ground truth) · run_eval.py · report.md · notes.md
scripts/       seed_demo.py · e2e_smoke.py
docs/          architecture.md (+ PNG diagrams) · slides.md / slides.pdf · demo_script.md · screenshots/
```

## Safety notes

- **This is a prototype, not a medical device.** It does not diagnose and never suggests changing medicines. Every
  screen shows a disclaimer. Critical values show a "contact a doctor or seek urgent care" banner, and emergency
  symptoms in chat show the 112 notice.
- **Code decides what is abnormal.** High, Low and Critical flags, unit conversions, codes and schedules are computed
  deterministically. The AI explains them and writes prose only.
- **Nothing is saved without human confirmation.** Low-confidence, disputed and verifier-added items are highlighted
  for review.
- **Privacy:**
  - Records stay in the local database.
  - Page images go to the configured LLM provider for extraction.
  - Summaries and chat receive fact sheets with gender, age and clinical facts only: no name, phone number or ABHA
    identifier.
  - Each account sees only its own records. *Delete account* (API: `POST /api/auth/delete-account`) removes the
    account, its profiles, records and uploaded files.
  - For production you would also need encryption at rest, HTTPS (`COOKIE_SECURE=true`), and a provider agreement
    that meets the DPDP Act.

## Security

- API keys belong only in `backend/.env`, which is gitignored. Never commit them.
- **Rotate any key that has been shared in chat or screenshots,** and set a usage limit on the provider dashboard.

## Credits and licences

- The synthetic handwriting samples use [Kalam](https://fonts.google.com/specimen/Kalam) and
  [Caveat](https://fonts.google.com/specimen/Caveat) (SIL Open Font License 1.1), which are bundled in `eval/fonts/`.
- Reference ranges and drug data are curated for demonstration. Verify them before any clinical use.
- FHIR profiles follow the [NRCeS ABDM implementation guide](https://nrces.in/ndhm/fhir/r4/).
