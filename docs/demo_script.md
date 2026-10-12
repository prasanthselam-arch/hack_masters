# Demo script (3 minutes)

## Before the demo (10 minutes earlier)

- [ ] **Model quota.** The Gemini free tier allows only 20 requests per model per day, and one document uses 3. Use a
      key with billing enabled, or a fresh key, and run `curl localhost:8000/api/health` to confirm.
- [ ] **Start the app.** Backend: `cd backend && .venv/bin/uvicorn app.main:app --port 8000`. Frontend:
      `cd frontend && npm run dev`. Open <http://localhost:5173>.
- [ ] **Seed the demo patient.** This runs about 9 LLM calls, so allow a few minutes:
      `backend/.venv/bin/python scripts/seed_demo.py --confirm lab_diabetes_lipid_pdf,rx_handwritten_diabetes --review rx_handwritten_photo`.
      It signs in to the demo account `demo@healthcopilot.in` (password `demo12345`), creates *Ramesh Kumar*, links ABHA `ramesh.kumar@abdm`, imports 4 records from the mock HIP, confirms two
      samples and leaves the handwritten photo waiting on the review screen.
- [ ] **Pre-warm the summaries.** Click *Explain my health* once in English and once in Hindi. Summaries are cached, so
      the live click is instant.
- [ ] **Have the files to hand.** `eval/samples/rx_bilingual_telugu.png`, for the live upload, and
      `eval/samples/rx_handwritten_photo.jpg`, to show next to the review screen.
- [ ] **Browser.** Sign in as `demo@healthcopilot.in` / `demo12345`. Zoom 110%, sidebar visible, language set to English.

## Script

| Time | Screen | Say / do |
|---|---|---|
| 0:00–0:15 | Dashboard | "Indian patients carry their health history on paper: handwritten prescriptions, lab printouts, discharge summaries, often in two languages. Health Copilot turns that paper into a verified health record, explains it, and makes it ready for ABDM. Anyone can sign up with an email or mobile number; each account sees only its own family's records." |
| 0:15–0:35 | Upload | Drop `rx_bilingual_telugu.png`. "Phone photos and PDFs both work. The live pipeline deskews and enhances the page, classifies it, extracts with Gemini vision into a strict schema, checks every value in code, then has a *different* model re-read the page." Leave it processing (about 30–40 s). |
| 0:35–1:15 | Review (handwritten photo) | Open the waiting document. "The original sits next to every extracted field. Each item shows its confidence and whether both AI reads agree." Point at the deskewed page, the *What the verification read changed* card, the dosage pills (morning, afternoon, night) and the weekly Uprise-D3 60K dose. Fix or accept one flagged item with *Looks right*, then *Confirm & save*. "Nothing reaches the record until a person confirms it." |
| 1:15–1:40 | Dashboard → Trends | "Every document builds one profile: abnormal results, today's medicines, conditions. The flags are computed by code from the report's own range, never by the AI." Open Trends → HbA1c: "the shaded band is the reference range across a year of records." |
| 1:40–2:05 | Dashboard summary in Hindi | Switch the language to हिन्दी and click *Explain my health*. "A plain-language summary in Hindi. The AI writes only the prose. Every number, flag and medicine schedule is attached from the database, and a safety filter blocks dosing advice and diagnoses." |
| 2:05–2:25 | Ask Copilot (Telugu) | Switch to తెలుగు and tap the suggested question *How has my HbA1c changed over time?*. "Answers come only from your own records, with citations." Type *chest pain* to show the emergency notice. |
| 2:25–2:45 | ABHA & Records | "ABDM-ready: link an ABHA with OTP, grant consent, and pull FHIR records from a hospital. Imported records go through the same validators. Every document exports as an NRCeS-profile FHIR R4 bundle." Click *Download FHIR bundle*. |
| 2:45–3:00 | Slide: *Measured, not claimed* | "We measured accuracy rather than claiming it: 100% of 477 checked fields on our 10-document test set with verification, including handwritten, photographed and four regional scripts. The evaluation also caught real bugs, which we fixed. AI reads and explains, code checks, you confirm." |

## If something goes wrong

- **The upload stays processing or fails with a quota error.** Say "the free-tier quota ran out" and use the pre-seeded
  documents. The flow is identical. *Re-read document* on the document view retries it.
- **The summary is slow.** It is cached after the first call. If you didn't pre-warm it, keep talking over the spinner,
  which takes about 20 seconds.
- **Backup video.** Record a run-through of this script with the same data beforehand.
