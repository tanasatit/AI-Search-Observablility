"""จับชื่อธุรกิจในคำตอบ (รองรับไทย/อังกฤษ)
Entity resolution: normalize names, find mentions, check citations, discover unknown names.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field

ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\ufeff]")
PUNCT = re.compile(r"[\s\-_.,:;!?'\"“”‘’()\[\]{}/\\|*#@&+–—]+")


def norm(s: str) -> str:
    """lowercase, drop spaces/punctuation/zero-width chars. 'Baan Suan Café' -> 'baansuancafé'"""
    s = unicodedata.normalize("NFC", s or "")
    s = ZERO_WIDTH.sub("", s).lower()
    return PUNCT.sub("", s)


@dataclass
class Entity:
    name: str
    role: str  # "target" | "competitor"
    aliases: list = field(default_factory=list)
    domains: list = field(default_factory=list)

    def keys(self):
        ks = {norm(x) for x in [self.name, *self.aliases]}
        return {k for k in ks if len(k) >= 2}


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    ents = [Entity(cfg["target"]["name"], "target",
                   cfg["target"].get("aliases", []), cfg["target"].get("domains", []))]
    for c in cfg.get("competitors", []):
        ents.append(Entity(c["name"], "competitor", c.get("aliases", []), c.get("domains", [])))
    queries = cfg["queries"]
    if not queries:
        raise SystemExit("config ไม่มี queries")
    return cfg, ents, queries


def find_mentions(text, entities):
    t = norm(text)
    return {e.name for e in entities if any(k in t for k in e.keys())}


def entity_in(text, entity):
    t = norm(text)
    return any(k in t for k in entity.keys())


def entity_cited(entity, citations):
    for c in citations or []:
        blob = f"{c.get('url', '')} {c.get('title', '')}".lower()
        if any(d.lower() in blob for d in entity.domains if d):
            return True
        if entity_in(c.get("title", ""), entity):
            return True
    return False


LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)$", re.M)
BOLD = re.compile(r"\*\*(.+?)\*\*")
SPLIT_AT = re.compile(r"\s+[–—\-:]\s+|[:(（]")


def discover_names(text):
    """Pull candidate business names from bold text and list items,
    so you can spot competitors you haven't added to config yet.
    Returns {normalized: display}. Noisy by design: a human reviews it."""
    found = {}
    for m in BOLD.finditer(text or ""):
        name = m.group(1).strip()
        if 1 < len(name) <= 40:
            found.setdefault(norm(name), name)
    for m in LIST_ITEM.finditer(text or ""):
        head = SPLIT_AT.split(m.group(1).replace("**", ""), maxsplit=1)[0].strip()
        if 1 < len(head) <= 40:
            found.setdefault(norm(head), head)
    return {k: v for k, v in found.items() if k}
