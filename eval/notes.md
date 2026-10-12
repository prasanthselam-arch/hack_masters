## Findings

**Accuracy.** With verification, every one of the 96 ground-truth items was found and every checked field was correct.
That covers drug, strength, schedule, duration, meal timing, value, unit, LOINC code, flag, ICD-10 code, document type and date.
The single pass alone missed one item: the "SpO2 97% on room air" line, which appears only in the discharge
summary's narrative text and not in the lab table. The verification pass found it and correctly flagged it for
review as an addition. This is the case the second read is designed for.

**Handwriting, photos and regional scripts.** This run had no errors on the handwritten, photographed, Hindi, Telugu,
Tamil or Kannada documents. The handwriting is rendered with handwriting fonts plus jitter, slant, blur, perspective and
JPEG noise, but it is still cleaner than a real doctor's pad. Expect lower accuracy on real handwriting, which is why every
document passes through the review screen before it reaches the health record.

**Bugs the evaluation found (now fixed).**

- *Spurious "found only by the verification pass" flags.* Matching between the two passes compared exact names, and the two
  models word names differently, for example "Haematocrit" and "Hematocrit (PCV)", or "Uprise-D3" and "Uprise D3 60K".
  In the run above, 18 of the 19 review flags were caused by this. The false-alarm row in the headline table shows the
  results from before the fix. Items are now matched on LOINC code, generic drug name and ICD-10 category before
  fuzzy names, and the case is covered by `test_verifier_rewording_is_not_treated_as_new_item`. With the fix, the only
  remaining flag would be the genuine SpO2 addition, so the false-alarm rate drops from about 20% to about 1%.
- *Ground-truth mistakes.* Body weight has no reference range, so "no flag" is the correct output. The SpO2 narrative value
  is on the page, so it belongs in the ground truth.
- *Non-reproducible samples.* The handwriting jitter was seeded with Python's per-process `hash()`. It now uses a stable
  CRC32, so `make_samples.py` produces byte-identical images on every run.

Earlier manual testing found two more bugs, which are now unit-tested in `backend/tests`:

- Combination brands were collapsed to the single-drug brand (Glycomet GP was matched as Glycomet).
- An older prescription imported after a newer one left both active.

**Safety-net coverage.** The "wrong items flagged" row is blank because there were no wrong items to flag. The
deterministic checks that would catch them are unit-tested separately in `backend/tests/test_validate.py`. They cover
implausible values, a mismatch between the printed and parsed numbers, a mismatch between the report's flag and the
reference range, unusual strengths, and day-first date parsing.

**Quota.** The Gemini free tier allows 20 requests per model per day. A full run needs about 30 requests, so the
fallback chain switches models during the run and a second full run in the same day is not possible. A run started
after the matching fix was cut short by quota (`eval/runs/20261012-080705`). To finish it after the quota resets, run
`python eval/run_eval.py --resume eval/runs/20261012-080705`. Rescoring
(`--rescore`) rebuilds the review payloads from the saved raw model output, so changes to the deterministic code can be
measured without spending quota.
