"""Similarity for clustering. Embeddings + cosine when an API key exists; otherwise a deterministic
normalized-token + category/subcategory score. Pure Python apart from the optional HTTP call."""
import json
import math
import re
import urllib.request

STOPWORDS = set("""a an the and or but if to of in on for from with at by is are was were be been being i me my we our us you your
it its this that these those am do does did not no can cannot cant can't unable able have has had will would should could
please help issue problem since still keeps keep also very just there their they them what when which who how any all
some many students student""".split())

SYNONYMS = {"payments": "payment", "pay": "payment", "paying": "payment", "paid": "payment", "fees": "fee",
            "failed": "fail", "failing": "fail", "fails": "fail", "failure": "fail", "error": "fail", "errors": "fail",
            "login": "access", "log": "access", "signin": "access", "access": "access", "accessing": "access",
            "registering": "register", "registration": "register", "registered": "register",
            "portal": "portal", "website": "portal", "site": "portal", "erp": "portal"}


def tokens(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    out = set()
    for w in words:
        if w in STOPWORDS or len(w) < 3:
            continue
        w = SYNONYMS.get(w, w)
        if len(w) > 4 and w.endswith("s"):
            w = w[:-1]
        out.add(w)
    return out


def fallback_similarity(text_a, cat_a, sub_a, text_b, cat_b, sub_b) -> float:
    ta, tb = tokens(text_a), tokens(text_b)
    jacc = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    # scale jaccard so that ~40% token overlap already counts as strong textual similarity
    text_score = min(1.0, jacc / 0.4)
    return round(0.55 * text_score + 0.25 * (cat_a == cat_b) + 0.20 * (sub_a == sub_b), 3)


def cosine(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def get_embedding(text: str, api_key: str, base_url: str, model: str, timeout: float):
    """Returns a vector or None. Never raises."""
    if not api_key:
        return None
    try:
        req = urllib.request.Request(
            f"{base_url}/embeddings",
            data=json.dumps({"model": model, "input": text[:4000]}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())["data"][0]["embedding"]
    except Exception:
        return None
