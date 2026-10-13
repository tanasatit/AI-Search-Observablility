"""สถิติทั้งหมดที่ใช้ — อ่านไฟล์นี้ให้เข้าใจก่อนนำเสนอ อาจารย์จะถามตรงนี้
"""
import math
from itertools import combinations

Z95 = 1.96


def wilson(k, n, z=Z95):
    """Wilson score interval for a proportion k/n. Better than p±z*sqrt(p(1-p)/n) for small n
    and for p near 0 or 1 (common here). Returns (p_hat, low, high)."""
    if n == 0:
        return 0.0, 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def half_width(k, n):
    _, lo, hi = wilson(k, n)
    return (hi - lo) / 2


def jaccard(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def mean_pairwise_jaccard(sets):
    """How similar are the answers across repeats? 1.0 = always the same businesses."""
    sets = list(sets)
    if len(sets) < 2:
        return None
    pairs = list(combinations(sets, 2))
    return sum(jaccard(a, b) for a, b in pairs) / len(pairs)


def required_n(p, margin, z=Z95):
    """Repeats needed so the 95% CI half-width ≈ margin. Uses p=0.5 when p is 0 or 1
    (we can't trust an extreme estimate to size the sample)."""
    if p <= 0 or p >= 1:
        p = 0.5
    return max(1, math.ceil(z * z * p * (1 - p) / (margin * margin)))


def variance_decomposition(by_session):
    """by_session: {session: [0/1, ...]}.
    within  = randomness inside one day (model sampling)
    between = drift across days (retrieval/index/model changes)
    Needs >= 2 sessions."""
    groups = [v for v in by_session.values() if v]
    if len(groups) < 2:
        return None
    means = [sum(g) / len(g) for g in groups]
    within = sum(m * (1 - m) for m in means) / len(means)
    grand = sum(means) / len(means)
    between = sum((m - grand) ** 2 for m in means) / len(means)
    total = within + between
    return {"within": within, "between": between,
            "share_between": (between / total) if total > 0 else 0.0, "sessions": len(groups)}
