"""แดชบอร์ด HTML ไฟล์เดียว เทียบการมองเห็นร้านค้าข้าม AI engine
  python -m aiso.dashboard          -> reports/dashboard.html (เปิดในเบราว์เซอร์ได้เลย ไม่ต้องต่อเน็ต)

Reads the same raw JSONL as report.py, so it can be re-run any time without new queries.
Mock data is excluded unless --include-mock, so simulated numbers never reach a real chart.
"""
import argparse
import datetime as dt
import json
import os
from collections import Counter, defaultdict
from urllib.parse import urlparse

from .entities import discover_names, load_config
from .extract import extract
from .report import load_records
from .stats import mean_pairwise_jaccard, wilson

ENGINE_LABELS = {
    "perplexity_web": "Perplexity (web, automated)",
    "gemini": "Gemini API + Google Search",
    "gemini_nosearch": "Gemini API, no search (baseline)",
    "mock": "Mock engine (simulated)",
}


def engine_label(p):
    if p in ENGINE_LABELS:
        return ENGINE_LABELS[p]
    if p.endswith("_app"):
        return f"{p[:-4].capitalize()} app (manual)"
    return p


def cite_domain(c):
    t = (c.get("title") or "").strip().lower()
    d = t if ("." in t and " " not in t) else urlparse(c.get("url", "")).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def build(all_records, entities, queries):
    engines = sorted({r["provider"] for r in all_records})
    # Compare engines only on queries every engine answered, so the rates are like for like.
    common = set.intersection(*({r["query_id"] for r in all_records if r["provider"] == e} for e in engines))
    records = [r for r in all_records if r["query_id"] in common]
    by_eng, by_eng_all = defaultdict(list), defaultdict(list)
    for r in records:
        by_eng[r["provider"]].append(r)
    for r in all_records:
        by_eng_all[r["provider"]].append(r)

    # mention rate + Wilson CI per (retailer, engine)
    rates = []
    for e in entities:
        for eng in engines:
            rs = by_eng[eng]
            k = sum(1 for r in rs if r["_x"][e.name]["mentioned"])
            p, lo, hi = wilson(k, len(rs))
            rates.append({"retailer": e.name, "role": e.role, "engine": eng, "k": k, "n": len(rs),
                          "p": p, "lo": lo, "hi": hi,
                          "rec": sum(1 for r in rs if r["_x"][e.name]["recommended"]),
                          "cited": sum(1 for r in rs if r["_x"][e.name]["cited"])})
    target = entities[0].name
    seen = {x["retailer"] for x in rates if x["k"] > 0}
    keep = [e.name for e in entities if e.name == target or e.name in seen]
    best = {n: max(x["p"] for x in rates if x["retailer"] == n) for n in keep}
    order = [target] + sorted((n for n in keep if n != target), key=lambda n: -best[n])
    rates = [x for x in rates if x["retailer"] in order]

    # target per query per engine
    per_query = []
    for qi, q in enumerate(queries):
        cells = {}
        for eng in engines:
            rs = [r for r in by_eng_all[eng] if r["query_id"] == qi]
            if rs:
                cells[eng] = {"k": sum(1 for r in rs if r["_x"][target]["mentioned"]), "n": len(rs)}
        if cells:
            per_query.append({"query": q, "cells": cells})

    # stability: mean pairwise Jaccard of names per (session, query), averaged
    stability = {}
    for eng in engines:
        groups = defaultdict(list)
        for r in by_eng[eng]:
            groups[(r["session"], r["query_id"])].append(r["_ment"] | r["_disc"])
        vals = [v for v in (mean_pairwise_jaccard(g) for g in groups.values()) if v is not None]
        stability[eng] = sum(vals) / len(vals) if vals else None

    cites = {}
    for eng in engines:
        cnt = Counter()
        for r in by_eng[eng]:
            cnt.update({cite_domain(c) for c in r.get("citations") or [] if cite_domain(c)})
        cites[eng] = [{"domain": d, "answers": n} for d, n in cnt.most_common(8)]

    # names the engines bring up that are not in config yet
    known = set()
    for e in entities:
        known |= e.keys()
    disc, disp = Counter(), {}
    for r in records:
        for k, v in discover_names(r.get("answer", "")).items():
            if not any(kk in k or k in kk for kk in known):
                disc[k] += 1
                disp.setdefault(k, v)
    unknown = [{"name": disp[k], "answers": n} for k, n in disc.most_common(12) if n >= 2]

    return {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "target": target,
        "common_queries": len(common),
        "engines": [{"id": e, "label": engine_label(e), "answers": len(by_eng[e]),
                     "answers_all": len(by_eng_all[e]),
                     "queries": len({r["query_id"] for r in by_eng[e]}),
                     "sessions": sorted({r["session"] for r in by_eng[e]})} for e in engines],
        "order": order, "rates": rates, "per_query": per_query,
        "stability": stability, "cites": cites, "unknown": unknown,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--data", default="data/raw/*.jsonl")
    ap.add_argument("--out", default="reports/dashboard.html")
    ap.add_argument("--include-mock", action="store_true")
    args = ap.parse_args()

    _, entities, queries = load_config(args.config)
    recs = [r for r in load_records(args.data) if not r.get("error")]
    if not args.include_mock:
        recs = [r for r in recs if r["provider"] != "mock"]
    if not recs:
        raise SystemExit("ยังไม่มีข้อมูล — รัน python -m aiso.collect ก่อน")
    for r in recs:
        r["_x"] = extract(r, entities)
        r["_ment"] = {n for n, fl in r["_x"].items() if fl["mentioned"]}
        r["_disc"] = set(discover_names(r.get("answer", "")).keys())

    if len({r["provider"] for r in recs}) > 1 and not set.intersection(
            *({r["query_id"] for r in recs if r["provider"] == p} for p in {r["provider"] for r in recs})):
        raise SystemExit("engines ไม่มี query ที่ตอบร่วมกันเลย — เทียบกันไม่ได้")
    data = build(recs, entities, queries)
    tpl_path = os.path.join(os.path.dirname(__file__), "dashboard_template.html")
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()
    html = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"เขียน {args.out}  ({len(recs)} คำตอบ, {len(data['engines'])} engines)")


if __name__ == "__main__":
    main()
