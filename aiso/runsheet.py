"""พิมพ์/สร้าง checklist สำหรับเก็บข้อมูลด้วยมือ (queries × engines × repeats)

  python -m aiso.runsheet                       # Markdown ออกหน้าจอ
  python -m aiso.runsheet --repeats 3 --out reports/runsheet   # -> reports/runsheet.md + reports/runsheet.csv
  python -m aiso.runsheet --engines perplexity,chatgpt --format csv

Uses config.json; falls back to config.example.json if config.json is missing.
Protocol: docs/run-sheet.md
"""
import argparse
import csv
import io
import os
import sys

from .entities import load_config
from .manual import PROVIDERS, parse_query_subset

ENGINE_LABELS = {
    "gemini": "Gemini (web)",
    "chatgpt": "ChatGPT (web)",
    "perplexity": "Perplexity (web)",
    "aimode": "Google AI Mode",
}
CSV_FIELDS = ["engine", "repeat", "q_no", "query", "date", "collector", "done",
              "sources_copied", "blocked", "note"]


def resolve_config(path):
    if os.path.exists(path):
        return path
    fallback = os.path.join(os.path.dirname(path) or ".", "config.example.json")
    if path == "config.json" and os.path.exists(fallback):
        print(f"ไม่พบ {path} ใช้ {fallback} แทน", file=sys.stderr)
        return fallback
    raise SystemExit(f"ไม่พบ config: {path}")


def parse_engines(spec):
    if not spec or spec.strip().lower() == "all":
        return list(PROVIDERS)
    out = []
    for e in spec.split(","):
        e = e.strip().lower()
        if not e:
            continue
        if e not in PROVIDERS:
            raise ValueError(f"engine ไม่รู้จัก: {e} (เลือกจาก {', '.join(PROVIDERS)})")
        if e not in out:
            out.append(e)
    return out


def build_rows(queries, engines, repeats, picked=None):
    """One row per engine × repeat × query. q_no is 1-based (same as aiso.manual --queries)."""
    picked = list(range(len(queries))) if picked is None else picked
    return [{"engine": e, "repeat": r, "q_no": qi + 1, "query": queries[qi]}
            for e in engines for r in range(repeats) for qi in picked]


def _md_cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_markdown(rows, engines, repeats, queries, config_path):
    q_nos = sorted({r["q_no"] for r in rows})
    qflag = "" if len(q_nos) == len(queries) else " --queries " + ",".join(map(str, q_nos))
    L = ["# AISO manual collection checklist", "",
         f"config: `{config_path}`  |  engines: {', '.join(engines)}  |  repeats: {repeats}  |  "
         f"queries: {len(q_nos)}  |  total: {len(rows)}", "",
         "Protocol: `docs/run-sheet.md`. ติ๊ก ☐ → ☑ เมื่อเก็บครบ (คำตอบ + แหล่งที่มา). "
         "เจอ login/CAPTCHA = หยุด เขียน BLOCKED ในช่อง note", ""]
    for e in engines:
        for rep in range(repeats):
            block = [r for r in rows if r["engine"] == e and r["repeat"] == rep]
            if not block:
                continue
            L += [f"## {ENGINE_LABELS[e]} — repeat {rep}", "",
                  f"วันที่: ________  ผู้เก็บ: ____  เบราว์เซอร์/โหมด: ______________  "
                  f"คำสั่ง: `python -m aiso.manual --provider {e} --repeat {rep}{qflag} --who XX --note \"...\"`", "",
                  "| ✓ | Q | query | sources | note |", "|---|---|---|---|---|"]
            L += [f"| ☐ | {r['q_no']} | {_md_cell(r['query'])} | ☐ | |" for r in block]
            L.append("")
    return "\n".join(L)


def render_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({**{k: "" for k in CSV_FIELDS}, **r})
    return buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description="สร้าง checklist สำหรับเก็บข้อมูลด้วยมือ")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--engines", default="all", help=f"เช่น perplexity,chatgpt (ค่าเริ่มต้น: {','.join(PROVIDERS)})")
    ap.add_argument("--repeats", type=int, default=3, help="จำนวนรอบต่อ query ต่อ engine")
    ap.add_argument("--queries", default=None, help="เลือกบาง query เช่น 1,3,5-7")
    ap.add_argument("--format", choices=("md", "csv", "both"), default="md", help="สำหรับพิมพ์ออกหน้าจอ")
    ap.add_argument("--out", default=None,
                    help="prefix ไฟล์ เช่น reports/runsheet -> runsheet.md + runsheet.csv (ไม่ใส่ = พิมพ์ออกหน้าจอ)")
    args = ap.parse_args(argv)
    if args.repeats < 1:
        raise SystemExit("--repeats ต้อง >= 1")

    cfg_path = resolve_config(args.config)
    _, _, queries = load_config(cfg_path)
    try:
        engines = parse_engines(args.engines)
        picked = parse_query_subset(args.queries, len(queries))
    except ValueError as e:
        raise SystemExit(str(e))
    rows = build_rows(queries, engines, args.repeats, picked)
    md = render_markdown(rows, engines, args.repeats, queries, cfg_path)
    cs = render_csv(rows)

    if args.out:
        d = os.path.dirname(args.out)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(args.out + ".md", "w", encoding="utf-8") as f:
            f.write(md + "\n")
        # utf-8-sig so Excel / Google Sheets open Thai text correctly
        with open(args.out + ".csv", "w", encoding="utf-8-sig", newline="") as f:
            f.write(cs)
        print(f"เขียน {args.out}.md และ {args.out}.csv ({len(rows)} แถว)")
        return
    if args.format in ("md", "both"):
        print(md)
    if args.format in ("csv", "both"):
        print(cs, end="")


if __name__ == "__main__":
    main()
