"""แยกว่าแต่ละร้าน ถูกพูดถึง / ถูก cite / ถูกแนะนำ หรือไม่
Rule-based v1. It WILL make mistakes: use label.py to measure how many (ตันที่ 4).

Definitions:
  mentioned   = name or alias appears in the answer
  cited       = entity's domain/name appears in the citation list
  recommended = mentioned in a clause that contains a recommendation marker that is not negated
                ("ไม่แนะนำ", "isn't the best", "far from ideal"), or in a list item under a recommending
                heading ("แนะนำ 3 ร้าน:", "Top picks:"). In "A better than B" / "A แทน B" only A counts.
  Latin names match whole words only ("Network Brewery" is not "Work & Brew"). Thai names are substrings.
"""
import re
from urllib.parse import urlparse

from .entities import clean, entity_cited

REC_MARKERS = ["แนะนำ", "เหมาะ", "ดีที่สุด", "ควรไป", "ห้ามพลาด", "โดดเด่น", "ยอดนิยม", "ตัวเลือกที่ดี",
               "ดีกว่า", "เหนือกว่า", "ต้องลอง", "ควรลอง", "ลองไป", "ลองแวะ", "คุ้มค่า", "ปักหมุด",
               "recommend", "best", "top pick", "ideal", "perfect for", "great for", "good for",
               "great choice", "great option", "good choice", "good option", "better choice", "better option",
               "best bet", "my pick", "i'd pick", "i'd go with", "go with", "must-try", "better than",
               "superior to", "top-rated", "top rated"]
# อันดับ 1 / #1 / top 3 — เขียนเป็น regex เพราะมีตัวเลข
REC_PATTERNS = [r"อันดับ\s?(?:1(?!\d)|หนึ่ง)", r"(?<![\w])(?:no\.?\s?|#|rank\s?)1(?!\d)", r"\btop[\s-]?\d+",
                r"\b(?:good|great|solid|top|nice|excellent)\s+(?:place|spot|cafe|café|shop|choice|option|pick|fit|bet)\b",
                r"\bpick\b(?![-\s]*up)", r"\bgo for\b"]
# วลีเชิงลบที่ไม่มีคำ REC อยู่ในตัว ใช้เป็นหลักฐานว่า "ถูกบอกให้เลี่ยง" (ชนะค่าเริ่มต้นจากหัวข้อลิสต์)
NEG_MARKERS = ["ไม่แนะนำ", "ไม่เหมาะ", "not recommend", "avoid", "ไม่ค่อยดี", "หลีกเลี่ยง", "ไม่ควรไป", "worst", "แย่ที่สุด",
               "ไม่โอเค", "เลี่ยง", "steer clear", "skip"]
# ข้อความที่บอกว่า "ไม่รู้/ไม่แน่ใจ" -> ไม่นับเป็นการแนะนำ
UNCERTAIN = ["ไม่มีข้อมูล", "ไม่ทราบ", "ไม่แน่ใจ", "ไม่ชัดเจน", "not sure", "no information", "unclear", "unsure",
             "don't know", "do not know", "neither", "none of", "ไม่มีร้านไหน"]
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+|\s{2,}")


def _words(phrases):
    return "|".join((r"\b" if p[0].isascii() and p[0].isalnum() else "") + re.escape(p) for p in phrases)


MARKER_RE = re.compile("|".join([_words(REC_MARKERS), *REC_PATTERNS]), re.I)
NEG_RE = re.compile(_words(NEG_MARKERS), re.I)
UNCERTAIN_RE = re.compile(_words(UNCERTAIN), re.I)
# a negator right before the marker: "not recommended", "isn't the best", "far from ideal" / "ไม่แนะนำ", "ไม่ใช่ร้านที่ดีที่สุด"
NEGATED_BEFORE = re.compile(
    r"(?:\bnot|n't|\bnever|\bno longer|\bhardly|\bfar from)(?!\s+only\b)(?:\s+[\w']+){0,3}\s*$"
    r"|(?:ไม่|มิ)(?:ค่อย|ได้|ใช่|ควร)?(?:ร้าน|ที่|เป็น|ตัวเลือก|สถานที่){0,2}\s*$", re.I)
# a clause boundary only matters when two businesses share a sentence: "A เหมาะ แต่ B ไม่เหมาะ"
CLAUSE_SPLIT = re.compile(r";|\b(?:but|while|whereas|however|although|though)\b|แต่(?!ง)|"
                          r"ส่วน(?!ตัว|ใหญ่|ลด|ผสม|ประกอบ|หนึ่ง)|ขณะที่|แม้ว่า|แม้|อย่างไรก็ตาม", re.I)
CONCESSIVE_START = re.compile(r"\s*(?:while|although|though|แม้ว่า|แม้|ถึงแม้)", re.I)
# "A better than B": A is recommended, B is not. "A แทน B": B is not (A needs its own marker).
PIVOT_UP = re.compile(r"\b(?:better|superior)(?:\s+(?:choice|option|pick|fit))?\s+(?:than|to)\b|\binstead of\b|"
                      r"\brather than\b|ดีกว่า|เหนือกว่า", re.I)
PIVOT_EXCLUDE = re.compile(r"(?<!ตัว)แทน|มากกว่า", re.I)
PIVOT_DOWN = re.compile(r"\bworse than\b|\bnot as good as\b|แย่กว่า|ด้อยกว่า|ไม่ดีเท่า", re.I)
LIST_BULLET = re.compile(r"^\s*(?:[-•·▪–—✓✔✅❌]|\*(?!\*)|\d+[.)]|\|)")
BOLD_ONLY = re.compile(r"\s*\*\*[^*]+\*\*:?\s*")
TABLE_RULE = re.compile(r"^[\s:|-]+$")


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


def marker_hits(text):
    """-> (has a non-negated recommendation marker, has a negated one)"""
    pos = neg = False
    for m in MARKER_RE.finditer(text):
        if NEGATED_BEFORE.search(text[max(0, m.start() - 60):m.start()]):
            neg = True
        else:
            pos = True
    return pos, neg


def _clause_ranges(sent, n_entities):
    if n_entities < 2:
        return [(0, len(sent))]
    cuts = [m.span() for m in CLAUSE_SPLIT.finditer(sent)]
    if CONCESSIVE_START.match(sent):  # "While A is X, B is Y" -> the comma ends the concessive part
        comma = re.search(r"[,，]", sent)
        if comma:
            cuts.append(comma.span())
    ranges, pos = [], 0
    for a, b in sorted(cuts):
        if a >= pos:
            ranges.append((pos, a))
            pos = b
    ranges.append((pos, len(sent)))
    return ranges


def _marker_events(clause):
    """[(start, end, is_positive)] for every recommendation marker and explicit negative cue in the clause"""
    events, spans = [], []
    for m in MARKER_RE.finditer(clause):
        events.append((m.start(), m.end(), not NEGATED_BEFORE.search(clause[max(0, m.start() - 60):m.start()])))
        spans.append(m.span())
    for m in NEG_RE.finditer(clause):
        if not any(a < m.end() and m.start() < b for a, b in spans):
            events.append((m.start(), m.end(), False))
    return events


def _nearest(found, start, end):
    """entity whose mention is closest to the marker; on a tie, the one after it ("ผมแนะนำ X")"""
    best = None
    for i, (_e, spans) in enumerate(found):
        for a, b in spans:
            gap = max(a - end, start - b, 0)
            key = (gap, 0 if a >= end else 1)
            if best is None or key < best[0]:
                best = (key, i)
    return best[1]


def _score_clause(clause, found, default, rec):
    """found = [(entity, [(start, end) inside clause])]. default = +1/-1/0 from a list heading above."""
    events = _marker_events(clause)
    pos = any(p for _, _, p in events)
    pivot_up, pivot_ex, pivot_down = PIVOT_UP.search(clause), PIVOT_EXCLUDE.search(clause), PIVOT_DOWN.search(clause)
    pivot = pivot_up or pivot_ex or pivot_down
    if UNCERTAIN_RE.search(clause):
        return
    # two businesses with opposite verdicts in one clause ("ไม่แนะนำ A ... ควรไป B"): each marker goes to the nearest one
    owners = None
    if len(found) > 1 and pos and any(not p for _, _, p in events):
        owners = {found[_nearest(found, a, b)][0].name for a, b, p in events if p}
    for e, spans in found:
        left = not pivot or any(a < pivot.start() for a, _ in spans)
        if pivot_down:
            ok = not left and marker_hits(clause[pivot.end():])[0]
        elif not left:
            ok = False
        elif owners is not None:
            ok = e.name in owners
        elif events or pivot_up:
            ok = pos or bool(pivot_up)
        else:
            ok = default > 0
        if ok:
            rec.add(e.name)


# "Bean Lab opened in 2019. I recommend it for meetings." -> a pronoun-only sentence after a sentence naming exactly one business
PRONOUN = re.compile(r"\b(?:it|it's|they|this (?:place|cafe|café|shop|spot))\b|ร้านนี้|ที่นี่|ที่นั่น", re.I)
NOT_A_VERDICT = re.compile(r"\b(?:best|ideal)\s+(?:to|if|when|time|before|after)\b", re.I)
AFFIRMATIVE = re.compile(r"\s*(?:yes|yeah|yep|sure|absolutely|definitely|ใช่|ได้เลย|ครับ|ค่ะ)", re.I)


def _line_sentences(line):
    """sentences of a line; an interjection ("ห้ามพลาด!") stays with the sentence it introduces"""
    out, carry = [], ""
    for sent in sentences(line):
        if sent.endswith("!") and len(sent) <= 30:
            carry += sent + " "
            continue
        out.append(carry + sent)
        carry = ""
    if carry:
        out.append(carry.strip())
    return out


def recommended_names(text, entities):
    """names of entities that are recommended, scanning line by line so a list heading can carry over to its items"""
    rec, ctx, prev = set(), 0, None  # ctx: +1 under a recommending heading, -1 under a "not recommended" one
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or TABLE_RULE.match(stripped):
            continue
        in_list = bool(LIST_BULLET.match(line))
        sentence_like = stripped[-1] in ".!?。" or len(stripped) > 120
        has_entity = any(e.spans(line) for e in entities)
        if not has_entity:
            if not in_list and (stripped.endswith((":", "：")) or BOLD_ONLY.fullmatch(line)):
                pos, neg = marker_hits(line)
                ctx = 1 if pos else -1 if neg or NEG_RE.search(line) else 0
            elif sentence_like:
                ctx = 0
            if prev and PRONOUN.search(line) and not NOT_A_VERDICT.search(line) and not UNCERTAIN_RE.search(line):
                events = _marker_events(line)
                if events and all(p for _, _, p in events):
                    rec.add(prev)
            prev = None
            continue
        default = ctx if (in_list or not sentence_like) else 0
        if not in_list and sentence_like:
            ctx = 0
        pending = set()  # businesses praised inside a question ("Is X good for work?") wait for the answer
        for sent in _line_sentences(line):
            found = [(e, e.spans(sent)) for e in entities]
            found = [(e, sp) for e, sp in found if sp]
            if pending:
                if AFFIRMATIVE.match(sent):
                    rec |= pending
                pending = set()
            if not found:
                if prev and PRONOUN.search(sent) and not NOT_A_VERDICT.search(sent):
                    events = _marker_events(sent)
                    if events and all(p for _, _, p in events) and not UNCERTAIN_RE.search(sent):
                        rec.add(prev)
                prev = None
                continue
            prev = found[0][0].name if len(found) == 1 else None
            hits = set()
            for a, b in _clause_ranges(sent, len(found)):
                inside = [(e, [(x - a, y - a) for x, y in sp if a <= x < b]) for e, sp in found]
                inside = [(e, sp) for e, sp in inside if sp]
                if inside:
                    _score_clause(sent[a:b], inside, default, hits)
            if sent.rstrip().endswith("?"):
                pending = hits
            else:
                rec |= hits
    return rec


def extract(record, entities):
    """-> {entity_name: {"mentioned", "cited", "recommended"}}"""
    text = clean(answer_text(record))
    rec = recommended_names(text, entities)
    return {e.name: {"mentioned": bool(e.spans(text)), "cited": entity_cited(e, record.get("citations")),
                     "recommended": e.name in rec} for e in entities}
