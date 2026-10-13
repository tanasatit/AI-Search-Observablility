"""Day 2: บันทึกคำตอบที่ถามมือในแอปจริง เพื่อเทียบกับ API

  python -m aiso.manual --provider gemini

For each query: open the Gemini app on your phone, ask the exact query, copy the answer,
paste it here, then type END on its own line. Lines starting with http are saved as citations.
Type SKIP to skip a query.
"""
import argparse
import datetime as dt
import json
import os
import sys
import uuid

from .entities import load_config


def read_block():
    lines = []
    for line in sys.stdin:
        s = line.rstrip("\n")
        if s.strip() in ("END", "SKIP"):
            return lines, s.strip() == "SKIP"
        lines.append(s)
    return lines, not lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--provider", default="gemini", help="API provider ที่จะเทียบ (บันทึกเป็น <provider>_app)")
    ap.add_argument("--session", default=dt.date.today().isoformat())
    ap.add_argument("--out", default="data/raw")
    args = ap.parse_args()

    _, _, queries = load_config(args.config)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"{args.session}_{args.provider}_app_manual.jsonl")
    print(f"บันทึกที่ {path}\nวางคำตอบจากแอป แล้วพิมพ์ END (หรือ SKIP)\n")
    saved = 0
    with open(path, "a", encoding="utf-8") as f:
        for qi, q in enumerate(queries):
            print(f"\n=== [{qi + 1}/{len(queries)}] ถามในแอป: {q}")
            lines, skipped = read_block()
            if skipped:
                print("  ข้าม")
                continue
            cites = [{"url": l.strip(), "title": l.strip()} for l in lines if l.strip().startswith("http")]
            text = "\n".join(l for l in lines if not l.strip().startswith("http"))
            rec = {"record_id": uuid.uuid4().hex[:12], "run_id": "manual", "session": args.session,
                   "ts": dt.datetime.now().isoformat(timespec="seconds"),
                   "provider": f"{args.provider}_app", "mode": "manual", "query_id": qi, "query": q,
                   "repeat": 0, "answer": text, "citations": cites}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            saved += 1
    print(f"\nบันทึก {saved} คำตอบ  ต่อไป: python -m aiso.report")


if __name__ == "__main__":
    main()
