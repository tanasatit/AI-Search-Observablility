"""Label มือ เพื่อวัดว่าตัวแกะข้อความ (extract.py) นับถูกแค่ไหน — แก้ ตันที่ 4
  python -m aiso.label --n 50

Shows an answer, you type the numbers of the businesses that are mentioned / recommended.
Resumable: already-labelled answers are skipped. Results show up in section 5 of the report.
"""
import argparse
import json
import os
import random

from .entities import load_config
from .report import load_records


def parse_nums(s, entities):
    out = []
    for tok in s.replace(",", " ").split():
        if tok.isdigit() and 1 <= int(tok) <= len(entities):
            out.append(entities[int(tok) - 1].name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--data", default="data/raw/*.jsonl")
    ap.add_argument("--labels", default="data/labels.jsonl")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    _, entities, _ = load_config(args.config)
    recs = [r for r in load_records(args.data)
            if not r.get("error") and not r["provider"].endswith("_app")]
    done = set()
    if os.path.exists(args.labels):
        with open(args.labels, encoding="utf-8") as f:
            done = {json.loads(l)["record_id"] for l in f if l.strip()}
    pool = [r for r in recs if r["record_id"] not in done]
    random.Random(args.seed).shuffle(pool)
    pool = pool[: max(0, args.n - len(done))]
    if not pool:
        print(f"label ครบแล้ว ({len(done)} คำตอบ)")
        return

    legend = "  ".join(f"{i + 1}={e.name}" for i, e in enumerate(entities))
    os.makedirs(os.path.dirname(args.labels) or ".", exist_ok=True)
    with open(args.labels, "a", encoding="utf-8") as f:
        for i, r in enumerate(pool, 1):
            print("\n" + "=" * 70)
            print(f"[{len(done) + i}/{args.n}] Query: {r['query']}\n")
            print(r["answer"])
            print("\n" + legend)
            try:
                m = parse_nums(input("ร้านไหนถูก *พูดถึง* (ใส่เลข เว้นวรรค, ว่าง=ไม่มี): "), entities)
                rc = parse_nums(input("ร้านไหนถูก *แนะนำ* (ชี้ว่าเหมาะกับที่ถาม): "), entities)
            except EOFError:
                break
            f.write(json.dumps({"record_id": r["record_id"], "mentioned": m, "recommended": rc},
                               ensure_ascii=False) + "\n")
            f.flush()
    print("\nบันทึกแล้ว  ดูผลใน: python -m aiso.report (ข้อ 5)")


if __name__ == "__main__":
    main()
