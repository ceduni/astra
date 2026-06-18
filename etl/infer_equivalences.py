"""
Infer course equivalences from description similarity (TF-IDF cosine).

SCOPE: only UdeM-course <-> other-university-course pairs are scored.
All 12 known official equivalences are UdeM-anchored (see
etl/official_equivalences.json), so that's the only regime this was
calibrated against — there's no ground truth to justify scoring e.g.
UQAM<->Poly pairs.

THRESHOLD: 0.30, chosen by analysis (not guessed):
  - 2 of the 12 official pairs are French<->English (UdeM-Concordia) and
    score 0.00-0.05 — lexical TF-IDF shares ~no vocabulary across
    languages, so these are structurally unrecoverable at any threshold.
    KNOWN LIMITATION: this is a ceiling on this script, not a tuning
    problem — French<->English equivalences (UdeM/UQAM/Poly <-> McGill/
    Concordia) will never surface here. Recovering them needs a
    multilingual embedding model (e.g. LaBSE or a multilingual
    sentence-transformer) to compare descriptions in shared semantic
    space instead of raw token overlap.
  - Of the other 10 (all French<->French), scores range 0.10-0.46.
    Manually inspecting candidate bands showed a precision cliff around
    0.25-0.30: below it, generic shared words ("sciences", "technologie")
    start producing clear nonsense pairs; at/above 0.30 the vast majority
    of non-official candidates are still plausible real equivalences
    (e.g. "Bases de données" <-> "Bases de données").
  - 0.30 recovers 6/12 official pairs (60% of the 10 that are even
    reachable). Lowering to 0.10 would recover 10/12 but at 5500+
    candidates of mostly degrading quality — since write_inferred_batch
    marks edges status='active' immediately (no review queue), precision
    was weighted over recall here.
  Re-running with a different THRESHOLD is cheap: clear_inferred_equivalences
  wipes prior inferred edges first, so this script is idempotent.

Corpus: title + description (title-only overlap recovers pairs where the
description happens to be empty), tokenized with \\w+ (lowercase, no
stemming/stopwords — the corpus is bilingual FR/EN so an English-only
stopword list would be lopsided; IDF weighting handles common words fine).

Usage:
  python etl/infer_equivalences.py
"""

import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).parent))
from equivalence_loader import clear_inferred_equivalences, write_inferred_batch

load_dotenv(Path(__file__).parents[1] / ".env")

THRESHOLD = 0.30

TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list:
    return TOKEN_RE.findall((text or "").lower())


def build_tfidf(docs: dict) -> dict:
    """docs: sigle -> token list. Returns sigle -> {term: weight}, L2-normalized."""
    n_docs = len(docs)
    doc_freq = Counter()
    for tokens in docs.values():
        for term in set(tokens):
            doc_freq[term] += 1
    idf = {term: math.log((1 + n_docs) / (1 + c)) + 1 for term, c in doc_freq.items()}

    vectors = {}
    for sigle, tokens in docs.items():
        term_freq = Counter(tokens)
        vec = {term: count * idf[term] for term, count in term_freq.items()}
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        vectors[sigle] = {term: w / norm for term, w in vec.items()}
    return vectors


def cosine(vec_a: dict, vec_b: dict) -> float:
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    return sum(weight * vec_b.get(term, 0.0) for term, weight in vec_a.items())


def fetch_courses(session) -> list:
    return [dict(r["c"]) for r in session.run(
        "MATCH (c:Cours {hors_perimetre: false}) RETURN c"
    )]


def fetch_covered_pairs(session) -> set:
    """Pairs that already have ANY active EQUIVAUT_A edge (official/inferred/request)."""
    rows = session.run(
        "MATCH (a:Cours)-[:EQUIVAUT_A {status: 'active'}]-(b:Cours) RETURN a.sigle AS a, b.sigle AS b"
    )
    return {tuple(sorted((r["a"], r["b"]))) for r in rows}


def main():
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )

    with driver.session() as session:
        courses = fetch_courses(session)
        official_pairs = {
            tuple(sorted((r["a"], r["b"])))
            for r in session.run(
                "MATCH (a:Cours)-[:EQUIVAUT_A {source: 'official'}]->(b:Cours)"
                " RETURN a.sigle AS a, b.sigle AS b"
            )
        }
        # Clear stale inferred edges first (idempotent rebuild) so the
        # "already covered" check below only reflects official/request
        # edges, not last run's own inferred output.
        for uni in {c["universite"] for c in courses}:
            clear_inferred_equivalences(session, uni)
        covered_pairs = fetch_covered_pairs(session)

    by_sigle = {c["sigle"]: c for c in courses}
    docs = {
        s: tokenize((c["titre"] or "") + " " + (c["description"] or ""))
        for s, c in by_sigle.items()
    }
    vectors = build_tfidf(docs)

    udem = [s for s, c in by_sigle.items() if c["universite"] == "UdeM"]
    others = [s for s, c in by_sigle.items() if c["universite"] != "UdeM"]

    # All pairs scoring >= threshold, regardless of existing coverage — this
    # is what measures the algorithm's actual recall against ground truth.
    above_threshold = []  # (sigle_a, sigle_b, score, sorted_pair)
    for a in udem:
        for b in others:
            score = cosine(vectors[a], vectors[b])
            if score >= THRESHOLD:
                above_threshold.append((a, b, score, tuple(sorted((a, b)))))

    recovered_official = {pair for *_, pair in above_threshold} & official_pairs

    # What's actually safe to write: exclude pairs that already have an
    # active equivalence of any source (don't duplicate the official edges).
    candidates = [(a, b, score) for a, b, score, pair in above_threshold if pair not in covered_pairs]

    with driver.session() as session:
        def tx_write(tx):
            return write_inferred_batch(tx, [
                {
                    "sigle_a": a,
                    "sigle_b": b,
                    "confidence": round(score, 4),
                    "evidence": f"tfidf_cosine_similarity={score:.4f}",
                }
                for a, b, score in candidates
            ])

        written = session.execute_write(tx_write)

    driver.close()

    print(f"Threshold:                          {THRESHOLD}")
    print(f"UdeM courses x other-uni courses:    {len(udem)} x {len(others)} = {len(udem) * len(others)} pairs evaluated")
    print(f"Inferred equivalences written:       {written}")
    print(f"Official pairs recovered:            {len(recovered_official)} / {len(official_pairs)}")
    for a, b in sorted(official_pairs):
        tag = "RECOVERED" if (a, b) in recovered_official else "missed"
        print(f"  [{tag:9s}] {a} <-> {b}")


if __name__ == "__main__":
    main()
