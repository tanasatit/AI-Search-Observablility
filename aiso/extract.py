"""แยกว่าแต่ละร้าน ถูกพูดถึง / ถูก cite / ถูกแนะนำ หรือไม่
Rule-based v1. It WILL make mistakes: use label.py to measure how many (ตันที่ 4).

Definitions:
  mentioned   = name or alias appears in the answer
  cited       = entity's domain/name appears in the citation list
  recommended = mentioned in a sentence/line that contains a recommendation marker
                (and no negation like "ไม่แนะนำ")
"""
import re
from urllib.parse import urlparse

from .entities import entity_cited, norm

REC_MARKERS = ["แนะนำ", "เหมาะ", "ดีที่สุด", "ควรไป", "ห้ามพลาด", "โดดเด่น", "ยอดนิยม", "ตัวเลือกที่ดี",
               "recommend", "best", "top pick", "ideal", "perfect for", "great for", "good for"]
NEG_MARKERS = ["ไม่แนะนำ", "ไม่เหมาะ", "not recommend", "avoid", "ไม่ค่อยดี"]
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+|\s{2,}")


def sentences(text):
    return [s for s in SENT_SPLIT.split(text or "") if s.strip()]


def is_source_chip(line, domains):
    """Perplexity's web page puts source chips inside the answer text ("powerbuy.co", "artandgungame", "+2").
    They are citations, not mentions; counting them would turn every cited shop into a mentioned one."""
    t = line.strip().lower()
    if not t or " " in t:
        return False
    if t[0] == "+" and t[1:].isdigit():
        return True
    return any(d.startswith(t) for d in domains)


def answer_text(record):
    """The answer with source chips removed. Raw data on disk is never changed."""
    text = record.get("answer", "")
    domains = [urlparse(c.get("url", "")).netloc.lower().removeprefix("www.") for c in record.get("citations") or []]
    if not domains:
        return text
    return "\n".join(l for l in text.split("\n") if not is_source_chip(l, domains))


def extract(record, entities):
    """-> {entity_name: {"mentioned", "cited", "recommended"}}"""
    text = answer_text(record)
    sents = [(s, norm(s), s.lower()) for s in sentences(text)]
    full = norm(text)
    out = {}
    for e in entities:
        keys = e.keys()
        mentioned = any(k in full for k in keys)
        rec = False
        if mentioned:
            for _raw, n, low in sents:
                if any(k in n for k in keys):
                    if any(m in low for m in NEG_MARKERS):
                        continue
                    if any(m in low for m in REC_MARKERS):
                        rec = True
                        break
        out[e.name] = {"mentioned": mentioned, "cited": entity_cited(e, record.get("citations")),
                       "recommended": rec}
    return out
