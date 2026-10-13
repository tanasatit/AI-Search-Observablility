"""สร้างรายงานที่ตอบคำถาม 3 วันโดยตรง
  python -m aiso.report            -> reports/report_<date>.md

Day 1: ผลนิ่งพอวัดไหม + ต้องยิงกี่รอบ + adaptive ประหยัดได้เท่าไหร่โดยไม่เสียความแม่น
Day 2: API ตรงกับแอปจริงแค่ไหน
Day 3: query ไหนแพ้ และ AI อ้างอิงหน้าไหน (เอาไปเปิดอ่านเทียบ)
"""
import argparse
import datetime as dt
import glob
import json
import os
from collections import Counter, defaultdict

from .entities import discover_names, load_config
from .extract import extract
from .stats import mean_pairwise_jaccard, required_n, variance_decomposition, wilson

STABLE_OK = 0.6


def load_records(pattern):
    recs = []
    for p in sorted(glob.glob(pattern)):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    r["_file"] = os.path.basename(p)
                    recs.append(r)
    return recs


def pct(x):
    return "-" if x is None else f"{100 * x:.0f}%"


def ci(k, n):
    p, lo, hi = wilson(k, n)
    return f"{100 * p:.0f}% [{100 * lo:.0f}–{100 * hi:.0f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--data", default="data/raw/*.jsonl")
    ap.add_argument("--labels", default="data/labels.jsonl")
    ap.add_argument("--out", default="reports")
    args = ap.parse_args()

    cfg, entities, queries = load_config(args.config)
    target = entities[0]
    all_recs = load_records(args.data)
    if not all_recs:
        raise SystemExit("ยังไม่มีข้อมูลใน data/raw — รัน python -m aiso.collect ก่อน")
    ok = [r for r in all_recs if not r.get("error")]
    for r in ok:
        r["_x"] = extract(r, entities)
        r["_disc"] = set(discover_names(r.get("answer", "")).keys())
        r["_ment"] = {n for n, fl in r["_x"].items() if fl["mentioned"]}

    api = [r for r in ok if not r["provider"].endswith("_app")]
    app = [r for r in ok if r["provider"].endswith("_app")]
    L = []
    w = L.append

    w(f"# AI Search Observability — รายงาน {dt.date.today().isoformat()}\n")
    w(f"ธุรกิจเป้าหมาย: **{target.name}** | คู่แข่งที่ติดตาม: {len(entities) - 1} | queries: {len(queries)}\n")

    # ---------- 0. data summary
    w("## 0. ข้อมูลที่มี\n")
    w("| provider | mode | session | สำเร็จ | error |\n|---|---|---|---|---|")
    summ = defaultdict(lambda: [0, 0])
    for r in all_recs:
        summ[(r["provider"], r.get("mode", "-"), r["session"])][1 if r.get("error") else 0] += 1
    for (p, m, s), (a, b) in sorted(summ.items()):
        w(f"| {p} | {m} | {s} | {a} | {b} |")
    w("")

    # ---------- 1. stability
    w("## 1. Day 1 — ผลนิ่งพอจะวัดไหม\n")
    w("ความเหมือนของคำตอบเมื่อถามซ้ำ (mean pairwise Jaccard ของชุดชื่อร้าน) "
      f"เกณฑ์ผ่าน ≥ {pct(STABLE_OK)}\n")
    w("| provider | query | รอบ | ร้านที่ติดตาม | ชื่อที่พบทั้งหมด |\n|---|---|---|---|---|")
    groups = defaultdict(list)
    for r in api:
        groups[(r["provider"], r["session"], r["query_id"])].append(r)
    tracked_scores, disc_scores = [], []
    for (p, s, qi), rs in sorted(groups.items()):
        jt = mean_pairwise_jaccard([r["_ment"] for r in rs])
        jd = mean_pairwise_jaccard([r["_disc"] for r in rs])
        if jt is not None:
            tracked_scores.append(jt)
        if jd is not None:
            disc_scores.append(jd)
        w(f"| {p} ({s}) | {rs[0]['query'][:40]} | {len(rs)} | {pct(jt)} | {pct(jd)} |")
    if tracked_scores:
        avg = sum(tracked_scores) / len(tracked_scores)
        avg_d = sum(disc_scores) / len(disc_scores) if disc_scores else None
        verdict = "✅ ผ่าน — สัญญาณนิ่งพอวัด" if avg >= STABLE_OK else \
            "⚠️ ไม่ผ่าน — ผลแกว่งมาก ต้องยิงหลายรอบขึ้นหรือทบทวนวิธีวัด"
        w(f"\n**เฉลี่ย: ร้านที่ติดตาม {pct(avg)} | ชื่อทั้งหมด {pct(avg_d)} → {verdict}**\n")

    # required N
    w("### ต้องยิงกี่รอบต่อ query ถึงจะเชื่อได้ (95% CI)\n")
    w("| ร้าน | mention rate ที่พบ | ±20% | ±15% | ±10% |\n|---|---|---|---|---|")
    for e in entities:
        k = sum(1 for r in api if r["_x"][e.name]["mentioned"])
        n = len(api)
        p = k / n if n else 0
        w(f"| {e.name} | {pct(p)} | {required_n(p, .2)} | {required_n(p, .15)} | {required_n(p, .1)} |")
    w("\n(จำนวนรอบ *ต่อ query* คำนวณจาก mention rate รวมทุก query เป็นค่าประมาณ ถ้าเป็น 0%/100% ใช้กรณีแย่สุด p=0.5)\n")

    # adaptive vs fixed — compare only within the same provider + session
    pairs = sorted({(r["provider"], r["session"]) for r in api if r.get("mode") == "adaptive"}
                   & {(r["provider"], r["session"]) for r in api if r.get("mode") == "fixed"})
    if pairs:
        w("### Adaptive vs Fixed — ประหยัดได้จริงไหม และแม่นเท่าเดิมไหม\n")
        w("(เทียบเฉพาะวันเดียวกัน provider เดียวกัน ใช้ fixed เป็นค่าอ้างอิง)\n")
        for prov, sess in pairs:
            fixed = [r for r in api if r["provider"] == prov and r["session"] == sess and r.get("mode") == "fixed"]
            adapt = [r for r in api if r["provider"] == prov and r["session"] == sess and r.get("mode") == "adaptive"]
            qs = {r["query_id"] for r in fixed} & {r["query_id"] for r in adapt}
            rpq_f = sum(1 for r in fixed if r["query_id"] in qs) / len(qs)
            rpq_a = sum(1 for r in adapt if r["query_id"] in qs) / len(qs)
            diffs, tdiffs = [], []
            for qi in qs:
                rf = [r for r in fixed if r["query_id"] == qi]
                ra = [r for r in adapt if r["query_id"] == qi]
                for e in entities:
                    d = abs(sum(r["_x"][e.name]["mentioned"] for r in rf) / len(rf)
                            - sum(r["_x"][e.name]["mentioned"] for r in ra) / len(ra))
                    diffs.append(d)
                    if e.role == "target":
                        tdiffs.append(d)
            w(f"**{prov} ({sess})** — fixed {rpq_f:.1f} รอบ/query | adaptive {rpq_a:.1f} รอบ/query "
              f"→ **ประหยัด {100 * (1 - rpq_a / rpq_f):.0f}%**")
            w(f"- mention rate ของ {target.name} ต่างจาก fixed: เฉลี่ย {pct(sum(tdiffs) / len(tdiffs))}, "
              f"มากสุด {pct(max(tdiffs))}")
            w(f"- ทุกร้านรวมกัน: เฉลี่ย {pct(sum(diffs) / len(diffs))}, มากสุด {pct(max(diffs))}")
        w("\nส่วนหนึ่งของความต่างมาจากการสุ่มปกติ ไม่ได้แปลว่า adaptive ผิดเสมอไป "
          "ลองเทียบกับ fixed สองรอบในวันเดียวกัน จะได้รู้ว่า 'ต่างตามธรรมชาติ' เท่าไหร่ ← นี่คือ finding ของโปรเจกต์\n")

    # variance decomposition — fixed-mode only, per query, then averaged
    fixed_all = [r for r in api if r.get("mode") == "fixed"]
    if len({r["session"] for r in fixed_all}) >= 2:
        w("### Variance มาจากไหน (fixed mode, ต้องมีข้อมูล ≥ 2 วัน)\n")
        w("| ร้าน | ภายในวัน | ข้ามวัน | สัดส่วนจากข้ามวัน |\n|---|---|---|---|")
        for e in entities:
            vds = []
            for qi in {r["query_id"] for r in fixed_all}:
                by = defaultdict(list)
                for r in fixed_all:
                    if r["query_id"] == qi:
                        by[r["session"]].append(1 if r["_x"][e.name]["mentioned"] else 0)
                vd = variance_decomposition(by)
                if vd:
                    vds.append(vd)
            if vds:
                wi = sum(v["within"] for v in vds) / len(vds)
                be = sum(v["between"] for v in vds) / len(vds)
                share = be / (wi + be) if wi + be > 0 else 0
                w(f"| {e.name} | {wi:.3f} | {be:.3f} | {pct(share)} |")
        w("\nถ้าสัดส่วนข้ามวันสูง = คำตอบเปลี่ยนไปตามวัน ต้องเก็บหลายวัน ยิงซ้ำในวันเดียวไม่พอ\n")

    # ---------- 2. API vs app
    w("## 2. Day 2 — API ตรงกับแอปจริงแค่ไหน\n")
    if not app:
        w("_ยังไม่มีข้อมูลจากแอป — รัน `python -m aiso.manual`_\n")
    else:
        w("เทียบชุดร้านในแอป กับ 'คำตอบทั่วไป' ของ API (ร้านที่โผล่ ≥ 50% ของรอบ)\n")
        w("| query | API | แอป | ตรงกัน |\n|---|---|---|---|")
        scores = []
        for a in app:
            base = a["provider"][:-4]
            rs = [r for r in api if r["provider"] == base and r["query_id"] == a["query_id"]]
            if not rs:
                continue
            cnt = Counter(n for r in rs for n in (r["_ment"] | r["_disc"]))
            typical = {n for n, c in cnt.items() if c / len(rs) >= 0.5}
            app_set = a["_ment"] | a["_disc"]
            j = len(typical & app_set) / len(typical | app_set) if (typical | app_set) else 1.0
            scores.append(j)
            w(f"| {a['query'][:40]} | {len(typical)} ร้าน | {len(app_set)} ร้าน | {pct(j)} |")
        if scores:
            avg = sum(scores) / len(scores)
            v = "✅ API สะท้อนของจริงได้ดี" if avg >= .6 else (
                "⚠️ ตรงบางส่วน ต้องระบุข้อจำกัดในรายงาน" if avg >= .3 else
                "❌ ตรงน้อยมาก — ตัวเลขจาก API อาจไม่สะท้อนสิ่งที่ลูกค้าเห็น (และนี่คือ finding ที่น่าสนใจ)")
            w(f"\n**เฉลี่ย {pct(avg)} → {v}**\n")

    # ---------- 3. visibility
    w("## 3. AI Visibility (จาก API, 95% CI)\n")
    w("| ร้าน | Mention | Recommendation | Citation | Share of voice |\n|---|---|---|---|---|")
    n = len(api)
    total_m = sum(len(r["_ment"]) for r in api) or 1
    for e in entities:
        km = sum(r["_x"][e.name]["mentioned"] for r in api)
        kr = sum(r["_x"][e.name]["recommended"] for r in api)
        kc = sum(r["_x"][e.name]["cited"] for r in api)
        star = " ⭐" if e.role == "target" else ""
        w(f"| {e.name}{star} | {ci(km, n)} | {ci(kr, n)} | {ci(kc, n)} | {pct(km / total_m)} |")
    w("")

    disc = Counter()
    known = {k for e in entities for k in e.keys()}
    for r in api:
        for d in r["_disc"]:
            if not any(k in d or d in k for k in known):
                disc[d] += 1
    if disc:
        w("### ชื่อที่ AI พูดถึงแต่ยังไม่อยู่ใน config (อาจเป็นคู่แข่งที่คุณไม่รู้)\n")
        disp = {}
        for r in api:
            disp.update(discover_names(r.get("answer", "")))
        for d, c in disc.most_common(15):
            w(f"- {disp.get(d, d)} — {c} ครั้ง")
        w("\n(เพิ่มตัวที่ใช่ลงใน competitors ใน config.json แล้วรันรายงานใหม่ ไม่ต้องยิงใหม่)\n")

    # ---------- 4. why not me worksheet
    w(f"## 4. Day 3 — 'Why Not Me?' worksheet\n")
    w(f"query ที่คู่แข่งติด (≥50%) แต่ {target.name} ติดน้อย (<50%) พร้อมหน้าที่ AI อ้างอิง "
      "ให้เปิดอ่านแล้วจดว่าหน้าพวกนี้มีข้อมูลอะไรที่เว็บเราไม่มี\n")
    found = False
    for qi, q in enumerate(queries):
        rs = [r for r in api if r["query_id"] == qi]
        if not rs:
            continue
        rate = lambda name: sum(r["_x"][name]["mentioned"] for r in rs) / len(rs)
        if rate(target.name) >= .5:
            continue
        winners = [(e.name, rate(e.name)) for e in entities[1:] if rate(e.name) >= .5]
        if not winners:
            continue
        found = True
        w(f"### ❌ {q}")
        w(f"- {target.name}: {pct(rate(target.name))} | ชนะโดย: "
          + ", ".join(f"{nm} ({pct(p)})" for nm, p in winners))
        cites = Counter(c.get("title") or c.get("url") for r in rs for c in r.get("citations", []))
        w("- หน้าที่ AI อ้างอิงบ่อย:")
        for t, c in cites.most_common(6):
            w(f"  - {t} ({c} ครั้ง)")
        w("- [ ] หน้าพวกนี้มีอะไรที่เว็บเราไม่มี: ________\n")
    if not found:
        w("_ไม่พบ query ที่แพ้ชัดเจน_\n")

    # ---------- 5. extractor accuracy
    if os.path.exists(args.labels):
        w("## 5. ตัวแกะข้อความแม่นแค่ไหน (เทียบกับที่คุณ label มือ)\n")
        byid = {r["record_id"]: r for r in ok}
        tp = defaultdict(int); fp = defaultdict(int); fn = defaultdict(int); tn = defaultdict(int)
        nlab = 0
        with open(args.labels, encoding="utf-8") as f:
            for line in f:
                lab = json.loads(line)
                r = byid.get(lab["record_id"])
                if not r:
                    continue
                nlab += 1
                for flag in ("mentioned", "recommended"):
                    human = set(lab[flag])
                    for e in entities:
                        pred = r["_x"][e.name][flag]
                        truth = e.name in human
                        if pred and truth: tp[flag] += 1
                        elif pred and not truth: fp[flag] += 1
                        elif truth: fn[flag] += 1
                        else: tn[flag] += 1
        w(f"label แล้ว {nlab} คำตอบ\n")
        w("| flag | precision | recall | accuracy |\n|---|---|---|---|")
        for flag in ("mentioned", "recommended"):
            pr = tp[flag] / (tp[flag] + fp[flag]) if tp[flag] + fp[flag] else None
            rc = tp[flag] / (tp[flag] + fn[flag]) if tp[flag] + fn[flag] else None
            tot = tp[flag] + fp[flag] + fn[flag] + tn[flag]
            ac = (tp[flag] + tn[flag]) / tot if tot else None
            w(f"| {flag} | {pct(pr)} | {pct(rc)} | {pct(ac)} |")
        w("\n(ถ้า recommended ต่ำกว่า ~80% ต้องปรับกฎใน extract.py ก่อนเชื่อตัวเลขในข้อ 3)\n")

    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, f"report_{dt.date.today().isoformat()}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L))
    print(f"\nบันทึกรายงานที่ {out}")


if __name__ == "__main__":
    main()
