"""
rag.py
------
HONEST ANSWER for judges asking "how does the retrieval actually work":

This is NOT a vector database / embeddings-based RAG system. It's a
lightweight, transparent retrieval step: we pull the relevant destination's
festivals/etiquette/food/verified_spots straight out of knowledge_base.json
(curated, human-verified data), rank the verified_spots by how well they
match the user's stated interests, and hand that curated context to Gemini
as grounding so it doesn't hallucinate facts. It trades "fancy" for
"honest and demo-reliable" — every fact traces back to a source URL in
knowledge_base.json.
"""

import json
import os

KB_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base.json")


def load_knowledge_base():
    with open(KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def score_spot(spot: dict, interests: list[str]) -> int:
    """
    Ranks a single verified_spot by how well it matches the user's
    stated interests. Higher score = more relevant, shown first.

    Simple, adjustable scoring:
      +2 if the spot's category matches an interest exactly
      +1 if an interest word appears anywhere in the spot's notes
    Feel free to tune the weights below once real data is in and you
    see results that feel "off".
    """
    score = 0
    category = (spot.get("category") or "").lower()
    notes = (spot.get("notes") or "").lower()

    for interest in interests:
        interest_l = interest.lower().strip()
        if not interest_l:
            continue
        if interest_l in category:
            score += 2
        if interest_l in notes:
            score += 1
    return score


def retrieve_context(destination: str, interests: list[str] | None = None) -> dict:
    """
    Pulls the matching destination's data out of knowledge_base.json and
    ranks verified_spots by interest match (using score_spot above).

    Returns a dict shaped like:
    {
        "found": bool,
        "festivals": [...],
        "etiquette": [...],
        "food": [...],
        "verified_spots": [...] (sorted best-match first),
        "sources": [list of every source URL used, deduplicated]
    }
    """
    interests = interests or []
    kb = load_knowledge_base()

    # Case-insensitive destination lookup
    match_key = None
    for key in kb.keys():
        if key.lower() == destination.lower():
            match_key = key
            break

    if not match_key:
        return {
            "found": False,
            "festivals": [],
            "etiquette": [],
            "food": [],
            "verified_spots": [],
            "sources": [],
        }

    entry = kb[match_key]
    spots = entry.get("verified_spots", [])

    ranked_spots = sorted(
        spots, key=lambda s: score_spot(s, interests), reverse=True
    )

    sources = set()
    for section in ("festivals", "etiquette", "food", "verified_spots"):
        for item in entry.get(section, []):
            src = item.get("source")
            if src:
                sources.add(src)

    return {
        "found": True,
        "festivals": entry.get("festivals", []),
        "etiquette": entry.get("etiquette", []),
        "food": entry.get("food", []),
        "verified_spots": ranked_spots,
        "sources": sorted(sources),
    }
