"""วัดความแม่นของตัวแกะข้อความ (extract.py) กับชุด gold ที่ label มือไว้แล้ว — ไม่ใช้ network / API key
  python -m aiso.benchmark                  # ทั้งชุด
  python -m aiso.benchmark --split test     # เฉพาะ test (ไม่เอาไว้จูนกฎ)
  python -m aiso.benchmark --errors         # ลิสต์เคสที่ตอบผิด

Gold = tests/gold/cases.jsonl (1 บรรทัด = 1 คำตอบ AI + citations + label ของแต่ละร้าน) ดู tests/gold/README.md
"""
import argparse
import json
import os
from collections import defaultdict

from .entities import discover_names, load_config, norm
from .extract import extract

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GOLD = os.path.join(ROOT, "tests", "gold", "cases.jsonl")
DEFAULT_CONFIG = os.path.join(ROOT, "config.example.json")
METRICS = ("mentioned", "cited", "recommended")


def load_gold(path=DEFAULT_GOLD, split="all"):
    cases = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                c = json.loads(line)
                if split == "all" or c.get("split") == split:
                    cases.append(c)
    return cases


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return p, r, f1


def evaluate(cases, entities, extract_fn=extract):
    """-> {"counts": {metric: {scope: {tp,fp,fn,tn}}}, "errors": [...], "unknown": (found, total), "n_cases": n}
    scope = "all" (ทุกร้าน) หรือ "target" (เฉพาะร้านเรา)"""
    counts = {m: defaultdict(lambda: defaultdict(int)) for m in METRICS}
    errors = []
    unk_found = unk_total = 0
    for case in cases:
        pred = extract_fn({"answer": case["answer"], "citations": case.get("citations", [])}, entities)
        for e in entities:
            for m in METRICS:
                p, g = pred[e.name][m], e.name in case["gold"][m]
                kind = ("tp" if g else "fp") if p else ("fn" if g else "tn")
                counts[m]["all"][kind] += 1
                if e.role == "target":
                    counts[m]["target"][kind] += 1
                if kind in ("fp", "fn"):
                    errors.append({"id": case["id"], "category": case.get("category"), "entity": e.name,
                                   "metric": m, "kind": kind, "answer": case["answer"]})
        if case.get("unknown_names"):
            found = discover_names(case["answer"])
            for name in case["unknown_names"]:
                unk_total += 1
                unk_found += norm(name) in found
    return {"counts": counts, "errors": errors, "unknown": (unk_found, unk_total), "n_cases": len(cases)}


def table(result, scope="all"):
    rows = []
    for m in METRICS:
        c = result["counts"][m][scope]
        p, r, f1 = prf(c["tp"], c["fp"], c["fn"])
        rows.append((m, p, r, f1, c["tp"], c["fp"], c["fn"]))
    return rows


def fmt(x):
    return "  n/a" if x is None else f"{x * 100:5.1f}%"


def print_report(result, show_errors=False, out=print):
    out(f"cases: {result['n_cases']}")
    for scope, label in (("all", "ทุกร้าน (target + competitors)"), ("target", "เฉพาะร้านเรา (target)")):
        out(f"\n[{label}]")
        out(f"{'metric':<12}{'precision':>10}{'recall':>9}{'F1':>8}   TP   FP   FN")
        for m, p, r, f1, tp, fp, fn in table(result, scope):
            out(f"{m:<12}{fmt(p):>10}{fmt(r):>9}{fmt(f1):>8} {tp:4d} {fp:4d} {fn:4d}")
    found, total = result["unknown"]
    if total:
        out(f"\nunknown-name discovery (discover_names): {found}/{total} ชื่อที่ไม่อยู่ใน config ถูกเจอ")
    errs = result["errors"]
    out(f"\nmisclassified: {len(errs)} (entity × metric)")
    if show_errors:
        for x in errs:
            out(f"  {x['id']} [{x['category']}] {x['metric']:<11} {x['kind'].upper()} {x['entity']!r}: "
                f"{x['answer'][:110]!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=DEFAULT_GOLD)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--split", default="all", choices=["all", "dev", "test", "holdout"])
    ap.add_argument("--errors", action="store_true", help="ลิสต์เคสที่ตอบผิด")
    args = ap.parse_args()
    _, entities, _ = load_config(args.config)
    print_report(evaluate(load_gold(args.gold, args.split), entities), args.errors)


if __name__ == "__main__":
    main()
