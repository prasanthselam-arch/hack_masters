"""Field-level evaluation of the extraction pipeline against eval/samples ground truth.

    python eval/run_eval.py                        # run the pipeline on every sample (calls the LLM)
    python eval/run_eval.py --only rx_             # subset by id prefix
    python eval/run_eval.py --rescore eval/runs/X  # recompute metrics from saved predictions

Each run writes eval/runs/<stamp>/{pred/*.json, results.json, report.md} and refreshes eval/report.md.
Both the single-pass extraction and the verified (second-model) extraction are scored, so the
value of the verification pass is measured rather than assumed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from rapidfuzz import fuzz  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.knowledge import _clean_drug, norm_unit  # noqa: E402
from app.pipeline.validate import parse_number  # noqa: E402

SAMPLES = ROOT / "samples"
RUNS = ROOT / "runs"
VARIANTS = ("single", "verified")
TAG_GROUPS = ["printed", "handwritten", "photo", "pdf", "bilingual"]


# --------------------------------------------------------------------------- running


def run(only: str | None, pause: float, out: Path | None = None) -> Path:
    """Run the pipeline on every sample; with `out`, only re-run samples that are missing or failed there."""
    from app.pipeline.runner import run_on_file

    out = out or RUNS / datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / "pred").mkdir(parents=True, exist_ok=True)
    for gt_path in sorted(SAMPLES.glob("*.json")):
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        if only and not gt["id"].startswith(only):
            continue
        prev = out / "pred" / f"{gt['id']}.json"
        if prev.exists() and not json.loads(prev.read_text(encoding="utf-8")).get("error"):
            continue
        print(f"→ {gt['id']:34s}", end="", flush=True)
        t0 = time.perf_counter()
        rec: dict[str, Any] = {"id": gt["id"]}
        try:
            r = run_on_file(SAMPLES / gt["file"], gt["mime"], gt.get("sex"), verify=True, work_dir=out / "work" / gt["id"])
            rec["classification"] = r["classification"].model_dump(mode="json")
            rec["first"] = r["first"].model_dump(mode="json")
            rec["verification"] = r["verification"].model_dump(mode="json") if "verification" in r else None
            rec["single"] = r["single"].model_dump(mode="json")
            rec["verified"] = r["verified"].model_dump(mode="json") if "verified" in r else None
            rec["verify_error"] = r.get("verify_error")
            rec["timings"] = r["timings"]
            rec["models"] = r["models"]
            status = "ok" if rec["verified"] else f"single only ({(rec['verify_error'] or '')[:60]})"
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"{type(e).__name__}: {e}"[:500]
            status = "FAILED " + rec["error"][:80]
        rec["wall_ms"] = int((time.perf_counter() - t0) * 1000)
        (out / "pred" / f"{gt['id']}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f" {rec['wall_ms'] / 1000:6.1f}s  {status}")
        time.sleep(pause)
    return out


# --------------------------------------------------------------------------- matching


def _greedy(gts: list[dict], preds: list[dict], sim) -> list[tuple[int, int]]:
    pairs = sorted(((sim(g, p), i, j) for i, g in enumerate(gts) for j, p in enumerate(preds)), reverse=True)
    used_g, used_p, out = set(), set(), []
    for s, i, j in pairs:
        if s < 80:
            break
        if i in used_g or j in used_p:
            continue
        used_g.add(i)
        used_p.add(j)
        out.append((i, j))
    return out


def _sim_med(g: dict, p: dict) -> float:
    if g.get("generic") and p.get("generic") and g["generic"].lower() == p["generic"].lower():
        return 100
    a, b = _clean_drug(g["name"]), _clean_drug(p.get("name") or p.get("name_raw") or "")
    return max(fuzz.ratio(a, b), fuzz.ratio(a, re.sub(r"\s+\d+$", "", b)))


def _sim_obs(g: dict, p: dict) -> float:
    if g.get("loinc") and p.get("loinc") == g["loinc"]:
        return 100
    return fuzz.token_set_ratio(g["name"].lower(), (p.get("name") or "").lower()) * 0.95


def _sim_cond(g: dict, p: dict) -> float:
    if p.get("icd10") and p["icd10"][:3] == g["icd10"][:3]:
        return 100
    return fuzz.token_set_ratio(g["name"].lower(), (p.get("name") or "").lower()) * 0.95


# --------------------------------------------------------------------------- field checks


def _strength(s: str | None) -> str:
    s = (s or "").lower().replace("µg", "mcg").replace(" ", "")
    s = re.sub(r"(\d+(?:\.\d+)?)k", lambda m: str(int(float(m.group(1)) * 1000)), s)
    return s


def _close(a: float | None, b: float) -> bool:
    return a is not None and abs(a - b) <= max(1e-6, 0.001 * abs(b))


def _base_flag(f: str | None) -> str | None:
    return {"HH": "H", "LL": "L"}.get(f or "", f)


def med_checks(g: dict, p: dict) -> dict[str, tuple[bool, Any, Any]]:
    out = {"generic": (bool(p.get("generic")) and p["generic"].lower() == g["generic"].lower(), g["generic"], p.get("generic"))}
    if g.get("strength"):
        out["strength"] = (_strength(p.get("strength")) == _strength(g["strength"]), g["strength"], p.get("strength"))
    if g.get("morning") is not None:
        exp = (g["morning"], g["afternoon"], g["night"])
        got = (p.get("morning"), p.get("afternoon"), p.get("night"))
        out["schedule"] = (all(x is not None and float(x) == float(y) for x, y in zip(got, exp)), "-".join(_n(x) for x in exp), "-".join(_n(x) for x in got))
    if g.get("duration_days") is not None:
        out["duration_days"] = (p.get("duration_days") == g["duration_days"], g["duration_days"], p.get("duration_days"))
    if g.get("meal_relation"):
        out["meal_relation"] = (p.get("meal_relation") == g["meal_relation"], g["meal_relation"], p.get("meal_relation"))
    return out


def obs_checks(g: dict, p: dict) -> dict[str, tuple[bool, Any, Any]]:
    printed = parse_number(p.get("value_original"))[0] if p.get("value_original") else None
    value_ok = _close(printed, g["value"]) or (printed is None and _close(p.get("value_num"), g["value"]))
    unit_ok = norm_unit(g["unit"]) in {norm_unit(p.get("unit_original")), norm_unit(p.get("unit"))}
    return {
        "value": (value_ok, g["value"], p.get("value_original") or p.get("value_num")),
        "unit": (unit_ok, g["unit"], p.get("unit_original") or p.get("unit")),
        "loinc": (p.get("loinc") == g["loinc"], g["loinc"], p.get("loinc")),
        "flag": (_base_flag(p.get("interpretation")) == g["interpretation"], g["interpretation"], p.get("interpretation")),
    }


def cond_checks(g: dict, p: dict) -> dict[str, tuple[bool, Any, Any]]:
    return {"icd10": ((p.get("icd10") or "")[:3] == g["icd10"][:3], g["icd10"], p.get("icd10"))}


def _n(x: Any) -> str:
    if x is None:
        return "?"
    return str(int(x)) if float(x).is_integer() else str(x)


# --------------------------------------------------------------------------- scoring


KINDS = {
    "medications": ("medications", "medications", _sim_med, med_checks, "name"),
    "observations": ("observations", "observations", _sim_obs, obs_checks, "name"),
    "conditions": ("conditions", "conditions", _sim_cond, cond_checks, "name"),
}


def rebuild(rec: dict[str, Any], sex: str | None) -> None:
    """Re-derive both review payloads from the saved raw model output with the current deterministic code."""
    from app.pipeline.validate import build_review
    from app.schemas.extraction import Classification, DocumentExtraction, VerificationResult

    if not rec.get("first"):
        return
    cls = Classification.model_validate(rec["classification"])
    first = DocumentExtraction.model_validate(rec["first"])
    rec["single"] = build_review(first, cls, sex).model_dump(mode="json")
    if rec.get("verification"):
        vr = VerificationResult.model_validate(rec["verification"])
        rec["verified"] = build_review(vr.corrected, cls, sex, first, vr).model_dump(mode="json")


def score(run_dir: Path) -> dict[str, Any]:
    gts = {g["id"]: g for g in (json.loads(p.read_text(encoding="utf-8")) for p in sorted(SAMPLES.glob("*.json")))}
    preds = {r["id"]: r for r in (json.loads(p.read_text(encoding="utf-8")) for p in sorted((run_dir / "pred").glob("*.json")))}
    for doc_id, rec in preds.items():
        rebuild(rec, gts.get(doc_id, {}).get("sex"))
    used: dict[str, Counter] = defaultdict(Counter)
    for rec in preds.values():
        for stage, model in (rec.get("models") or {}).items():
            used[stage][model] += 1
    results: dict[str, Any] = {
        "run": run_dir.name,
        "documents": len(preds),
        "configured_models": {r: get_settings().models_for(r) for r in ("extract", "verify")},
        "models_used": {k: dict(v) for k, v in used.items()},
    }
    for variant in VARIANTS:
        ent = {k: {"tp": 0, "fp": 0, "fn": 0} for k in KINDS}
        fields: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        tags: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        review = {"wrong_items": 0, "wrong_flagged": 0, "correct_items": 0, "correct_flagged": 0, "missed_items": 0, "extra_items": 0, "extra_flagged": 0}
        errors: list[dict[str, Any]] = []
        per_doc: dict[str, Any] = {}
        fallback = 0
        for doc_id, gt in gts.items():
            rec = preds.get(doc_id)
            if rec is None:
                continue
            payload = rec.get(variant) or rec.get("single") if not rec.get("error") else None
            if variant == "verified" and rec.get("single") and not rec.get("verified"):
                fallback += 1
            d_ok = d_total = 0

            def check(name: str, ok: bool, exp: Any, got: Any, item: str = "") -> None:
                nonlocal d_ok, d_total
                fields[name][0] += ok
                fields[name][1] += 1
                d_ok += ok
                d_total += 1
                for t in gt["tags"]:
                    if t in TAG_GROUPS:
                        tags[t][0] += ok
                        tags[t][1] += 1
                if not ok:
                    errors.append({"doc": doc_id, "field": name, "item": item, "expected": exp, "got": got})

            if payload is None:
                for k in KINDS:
                    ent[k]["fn"] += len(gt[k])
                    for g in gt[k]:
                        check(f"{k[:-1]}.found", False, g["name"], None, g["name"])
                review["missed_items"] += sum(len(gt[k]) for k in KINDS)
                per_doc[doc_id] = {"error": rec.get("error")}
                continue

            check("document.type", payload["document"]["doc_type"] == gt["doc_type"], gt["doc_type"], payload["document"]["doc_type"])
            check("document.date", payload["document"]["document_date"] == gt["document_date"], gt["document_date"], payload["document"]["document_date"])
            for k, (gkey, pkey, sim, checks, label) in KINDS.items():
                g_items, p_items = gt[gkey], payload[pkey]
                pairs = _greedy(g_items, p_items, sim)
                ent[k]["tp"] += len(pairs)
                ent[k]["fn"] += len(g_items) - len(pairs)
                ent[k]["fp"] += len(p_items) - len(pairs)
                matched_g = {i for i, _ in pairs}
                matched_p = {j for _, j in pairs}
                for i, g in enumerate(g_items):
                    if i not in matched_g:
                        check(f"{k[:-1]}.found", False, g[label], None, g[label])
                        review["missed_items"] += 1
                for j, p in enumerate(p_items):
                    if j not in matched_p:
                        review["extra_items"] += 1
                        review["extra_flagged"] += bool(p.get("needs_review"))
                        errors.append({"doc": doc_id, "field": f"{k[:-1]}.extra", "item": p.get(label), "expected": None, "got": p.get(label)})
                for i, j in pairs:
                    g, p = g_items[i], p_items[j]
                    check(f"{k[:-1]}.found", True, g[label], p.get(label), g[label])
                    res = checks(g, p)
                    for fname, (ok, exp, got) in res.items():
                        check(f"{k[:-1]}.{fname}", ok, exp, got, g[label])
                    item_ok = all(ok for ok, _, _ in res.values())
                    flagged = bool(p.get("needs_review"))
                    if item_ok:
                        review["correct_items"] += 1
                        review["correct_flagged"] += flagged
                    else:
                        review["wrong_items"] += 1
                        review["wrong_flagged"] += flagged
            per_doc[doc_id] = {"field_accuracy": round(d_ok / d_total, 4) if d_total else None, "checked": d_total,
                               "stats": payload.get("stats"), "timings": rec.get("timings")}

        def prf(e: dict[str, int]) -> dict[str, float]:
            p = e["tp"] / (e["tp"] + e["fp"]) if e["tp"] + e["fp"] else 1.0
            r = e["tp"] / (e["tp"] + e["fn"]) if e["tp"] + e["fn"] else 1.0
            return {**e, "precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}

        value_fields = {k: v for k, v in fields.items() if not k.endswith(".found")}
        ok = sum(v[0] for v in value_fields.values())
        total = sum(v[1] for v in value_fields.values())
        all_ok = sum(v[0] for v in fields.values())
        all_total = sum(v[1] for v in fields.values())
        results[variant] = {
            "verification_fallbacks": fallback if variant == "verified" else 0,
            "entities": {k: prf(v) for k, v in ent.items()},
            "fields": {k: {"correct": v[0], "total": v[1], "accuracy": round(v[0] / v[1], 4)} for k, v in sorted(fields.items())},
            "field_accuracy_matched": round(ok / total, 4) if total else None,
            "field_accuracy_end_to_end": round(all_ok / all_total, 4) if all_total else None,
            "by_tag": {t: {"correct": v[0], "total": v[1], "accuracy": round(v[0] / v[1], 4)} for t, v in tags.items()},
            "review": {**review,
                       "error_flag_recall": round(review["wrong_flagged"] / review["wrong_items"], 4) if review["wrong_items"] else None,
                       "false_alarm_rate": round(review["correct_flagged"] / review["correct_items"], 4) if review["correct_items"] else None},
            "errors": errors,
            "per_doc": per_doc,
        }
    timings = [p.get("timings") or {} for p in preds.values()]
    results["latency_s"] = {k: round(sum(t.get(k, 0) for t in timings) / max(1, sum(1 for t in timings if k in t)) / 1000, 2)
                            for k in ("classify", "extract", "verify")}
    return results


# --------------------------------------------------------------------------- report


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def report(res: dict[str, Any]) -> str:
    s, v = res["single"], res["verified"]
    gts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SAMPLES.glob("*.json"))]
    n_items = sum(len(g["medications"]) + len(g["observations"]) + len(g["conditions"]) for g in gts)
    def used(stage: str) -> str:
        counts = res["models_used"].get(stage) or {}
        parts = [f"`{m}` ×{n}" for m, n in sorted(counts.items(), key=lambda x: -x[1])]
        if (missing := res["documents"] - sum(counts.values())) > 0:
            parts.append(f"not recorded ×{missing}")
        return ", ".join(parts)

    L = [
        "# Extraction accuracy report",
        "",
        f"Run `{res['run']}` · {res['documents']} documents · {n_items} ground-truth items",
        "",
        f"Models that served each stage (the free tier rate-limits, so the fallback chain is often used): "
        f"extract {used('extract')}; verify {used('verify')}.",
        "",
        "Generated by `eval/run_eval.py` on the synthetic set from `eval/make_samples.py` (printed, handwritten, phone-photo, "
        "multi-page PDF, Hindi / Telugu / Tamil / Kannada). Every number below is computed against hand-written ground truth; "
        "nothing is self-reported by the model.",
        "",
        "## Headline",
        "",
        "| Metric | Single pass | With verification |",
        "|---|---|---|",
        f"| Field accuracy, end to end (missed items count as errors) | {_pct(s['field_accuracy_end_to_end'])} | {_pct(v['field_accuracy_end_to_end'])} |",
        f"| Field accuracy on matched items | {_pct(s['field_accuracy_matched'])} | {_pct(v['field_accuracy_matched'])} |",
    ]
    for k in KINDS:
        L.append(f"| {k.capitalize()} F1 (P / R) | {_pct(s['entities'][k]['f1'])} ({_pct(s['entities'][k]['precision'])} / {_pct(s['entities'][k]['recall'])}) | "
                 f"{_pct(v['entities'][k]['f1'])} ({_pct(v['entities'][k]['precision'])} / {_pct(v['entities'][k]['recall'])}) |")
    L.append(f"| Wrong items flagged for human review | {_pct(s['review']['error_flag_recall'])} | {_pct(v['review']['error_flag_recall'])} |")
    L.append(f"| Correct items flagged (false alarms) | {_pct(s['review']['false_alarm_rate'])} | {_pct(v['review']['false_alarm_rate'])} |")
    if v.get("verification_fallbacks"):
        L.append(f"\nVerification was unavailable for {v['verification_fallbacks']} document(s); the verified column uses the single-pass result for those.")
    L += ["", "## Field accuracy", "", "| Field | Single pass | With verification | n |", "|---|---|---|---|"]
    for f in v["fields"]:
        L.append(f"| `{f}` | {_pct(s['fields'].get(f, {}).get('accuracy'))} | {_pct(v['fields'][f]['accuracy'])} | {v['fields'][f]['total']} |")
    L += ["", "## By document condition (field accuracy, with verification)", "", "| Condition | Accuracy | Fields checked |", "|---|---|---|"]
    for t in TAG_GROUPS:
        if t in v["by_tag"]:
            L.append(f"| {t} | {_pct(v['by_tag'][t]['accuracy'])} | {v['by_tag'][t]['total']} |")
    L += ["", "## Per document (with verification)", "", "| Document | Field accuracy | Items flagged for review |", "|---|---|---|"]
    for d, info in v["per_doc"].items():
        if "error" in info:
            L.append(f"| {d} | failed: {info['error'][:80]} | — |")
        else:
            st = info.get("stats") or {}
            L.append(f"| {d} | {_pct(info['field_accuracy'])} | {st.get('needs_review', 0)} / {st.get('items_total', 0)} |")
    lat = res["latency_s"]
    L += ["", "## Latency (mean seconds per document)", "", f"classify {lat['classify']} s · extract {lat['extract']} s · verify {lat['verify']} s", ""]
    errs = v["errors"]
    L += ["## Remaining errors (with verification)", ""]
    if not errs:
        L.append("None.")
    else:
        L += ["| Document | Field | Item | Expected | Got |", "|---|---|---|---|---|"]
        for e in errs[:60]:
            L.append(f"| {e['doc']} | `{e['field']}` | {e['item'] or ''} | {e['expected']} | {e['got']} |")
    notes = ROOT / "notes.md"
    if notes.exists():
        L += ["", notes.read_text(encoding="utf-8").strip()]
    L += ["", "## How to read this", "",
          "- *End to end* counts a ground-truth item the pipeline missed as a wrong field, so it reflects what a user would see before review.",
          "- *Wrong items flagged* is the share of incorrect items the review screen highlights for a human; this is the safety net that the "
          "deterministic validators and confidence calibration provide.",
          "- Values are compared to what is printed on the document (so a unit conversion is not counted as an error); flags are compared after "
          "conversion, so they also test the unit normalisation and reference-range logic.",
          "- The synthetic set is small and was written by the same team that built the pipeline. Treat it as a regression suite, not a clinical "
          "validation. Real-world accuracy on poor photos of handwriting will be lower; that is why every document goes through human review.",
          ""]
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="only run samples whose id starts with this prefix")
    ap.add_argument("--rescore", type=Path, help="recompute metrics for an existing run directory")
    ap.add_argument("--resume", type=Path, help="re-run only the missing or failed samples of an existing run directory")
    ap.add_argument("--pause", type=float, default=4.0, help="seconds to wait between documents (free-tier rate limits)")
    args = ap.parse_args()

    run_dir = args.rescore or run(args.only, args.pause, args.resume)
    res = score(run_dir)
    (run_dir / "results.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md = report(res)
    (run_dir / "report.md").write_text(md, encoding="utf-8")
    if not args.only:
        (ROOT / "report.md").write_text(md, encoding="utf-8")
    v, s = res["verified"], res["single"]
    print(f"\nfield accuracy end-to-end: single {_pct(s['field_accuracy_end_to_end'])}  verified {_pct(v['field_accuracy_end_to_end'])}")
    print(f"wrong items flagged for review: {_pct(v['review']['error_flag_recall'])}  ·  report: {run_dir / 'report.md'}")


if __name__ == "__main__":
    main()
