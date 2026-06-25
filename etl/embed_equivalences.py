"""
Infer course equivalences using multilingual sentence embeddings.

Model: paraphrase-multilingual-MiniLM-L12-v2
  Maps 50+ languages into a shared 384-dim space — handles FR↔EN pairs
  that TF-IDF cannot reach (zero shared vocabulary across languages).

Thresholds:
  THRESHOLD    = 0.78  all cross-university pairs
  POLY_ETS_THR = 0.72  Poly↔ETS only, gated by same course-code prefix
                       (both schools share LOG/IND/ELE/MTH conventions)

Scope: all courses with description > 30 chars, filtered to same academic cycle.
  Cycle is inferred from hors_perimetre: false → 1er cycle, true → 2e cycle+.

This script replaces infer_equivalences.py for the inferred edge set —
it clears all inferred edges first and rewrites them from scratch
(idempotent; safe to re-run).

Usage:
  python etl/embed_equivalences.py
"""

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).parent))
from equivalence_loader import INFERRED, clear_inferred_equivalences, write_inferred_batch

load_dotenv(Path(__file__).parents[1] / ".env")

MODEL_NAME   = "paraphrase-multilingual-MiniLM-L12-v2"
THRESHOLD    = 0.78   # active
PENDING_THR  = 0.70   # pending — requires admin review
POLY_ETS_THR = 0.72   # active for Poly↔ETS same-prefix pairs
MIN_DESC_LEN = 30

# Universities that teach primarily in French
FR_UNIS = {"UdeM", "UQAM", "Poly", "ETS"}
EN_UNIS = {"McGill", "Concordia"}

PREFIX_RE = re.compile(r"^([A-Z]+)", re.ASCII)


def code_prefix(sigle: str) -> str:
    m = PREFIX_RE.match(sigle.upper().replace(" ", ""))
    return m.group(1) if m else ""


def fetch_courses(session) -> list:
    return [dict(r["c"]) for r in session.run(
        "MATCH (c:Cours) RETURN c"
    )]


def course_cycle(c: dict) -> int:
    """1 = undergraduate (hors_perimetre=false), 2 = graduate (hors_perimetre=true)."""
    return 1 if not c.get("hors_perimetre") else 2


def fetch_covered_pairs(session) -> set:
    rows = session.run(
        "MATCH (a:Cours)-[:EQUIVAUT_A {status: 'active'}]-(b:Cours)"
        " RETURN a.sigle AS a, b.sigle AS b"
    )
    return {tuple(sorted((r["a"], r["b"]))) for r in rows}


def lang(uni: str) -> str:
    return "FR" if uni in FR_UNIS else "EN"


def main():
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )

    # ── Snapshot + clear ─────────────────────────────────────────────────────
    with driver.session() as session:
        all_courses = fetch_courses(session)

        before_total = session.run(
            "MATCH ()-[r:EQUIVAUT_A]->() RETURN count(r) AS n"
        ).single()["n"]
        before_inferred = session.run(
            "MATCH ()-[r:EQUIVAUT_A {source: $s}]->() RETURN count(r) AS n",
            s=INFERRED,
        ).single()["n"]

        print(f"Edges before — total: {before_total}  (inferred: {before_inferred})")

        for uni in {c["universite"] for c in all_courses}:
            clear_inferred_equivalences(session, uni)

        covered_pairs = fetch_covered_pairs(session)

    # ── Filter to courses with usable descriptions ────────────────────────────
    courses = [
        c for c in all_courses
        if c.get("description") and len(c["description"]) > MIN_DESC_LEN
    ]
    by_uni: dict[str, list] = defaultdict(list)
    for c in courses:
        by_uni[c["universite"]].append(c)

    c1 = sum(1 for c in courses if course_cycle(c) == 1)
    c2 = sum(1 for c in courses if course_cycle(c) == 2)
    print(f"Courses with usable descriptions: {len(courses)} / {len(all_courses)}  (cycle 1: {c1}, cycle 2+: {c2})")
    for uni in sorted(by_uni):
        u_c1 = sum(1 for c in by_uni[uni] if course_cycle(c) == 1)
        u_c2 = sum(1 for c in by_uni[uni] if course_cycle(c) == 2)
        print(f"  {uni:<12} {len(by_uni[uni]):>4}  (c1: {u_c1}, c2+: {u_c2})")

    # ── Encode ────────────────────────────────────────────────────────────────
    print(f"\nLoading {MODEL_NAME} …")
    model = SentenceTransformer(MODEL_NAME)

    texts = [
        ((c.get("titre") or "") + ". " + (c.get("description") or "")).strip()
        for c in courses
    ]
    print(f"Encoding {len(texts)} descriptions …")
    embeddings = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,   # L2-norm → cosine = dot product
        convert_to_numpy=True,
    )

    # Index: sigle → (embedding index, course dict)
    sigle_to_idx  = {c["sigle"]: i for i, c in enumerate(courses)}

    # ── Score cross-university pairs ─────────────────────────────────────────
    uni_names  = sorted(by_uni.keys())
    candidates = []   # (sigle_a, sigle_b, score, status)

    for i_u, uni_a in enumerate(uni_names):
        for uni_b in uni_names[i_u + 1:]:
            items_a = by_uni[uni_a]
            items_b = by_uni[uni_b]
            is_poly_ets = {uni_a, uni_b} == {"Poly", "ETS"}

            idxs_a = [sigle_to_idx[c["sigle"]] for c in items_a]
            idxs_b = [sigle_to_idx[c["sigle"]] for c in items_b]
            emb_a  = embeddings[idxs_a]   # (n_a, 384)
            emb_b  = embeddings[idxs_b]   # (n_b, 384)
            sims   = emb_a @ emb_b.T      # (n_a, n_b) — cosine scores

            for row_i, ca in enumerate(items_a):
                for col_j, cb in enumerate(items_b):
                    score = float(sims[row_i, col_j])
                    pair  = tuple(sorted((ca["sigle"], cb["sigle"])))

                    if pair in covered_pairs:
                        continue

                    if course_cycle(ca) != course_cycle(cb):
                        continue

                    if is_poly_ets:
                        same_prefix = (
                            code_prefix(ca["sigle"]) == code_prefix(cb["sigle"])
                            and code_prefix(ca["sigle"]) != ""
                        )
                        if same_prefix and score >= POLY_ETS_THR:
                            candidates.append((ca["sigle"], cb["sigle"], score, "active"))
                        elif same_prefix and score >= PENDING_THR:
                            candidates.append((ca["sigle"], cb["sigle"], score, "pending"))
                    else:
                        if score >= THRESHOLD:
                            candidates.append((ca["sigle"], cb["sigle"], score, "active"))
                        elif score >= PENDING_THR:
                            candidates.append((ca["sigle"], cb["sigle"], score, "pending"))

    candidates.sort(key=lambda x: -x[2])
    active_cands  = [(a, b, s, st) for a, b, s, st in candidates if st == "active"]
    pending_cands = [(a, b, s, st) for a, b, s, st in candidates if st == "pending"]
    print(f"  Active candidates (≥{THRESHOLD}):  {len(active_cands)}")
    print(f"  Pending candidates ({PENDING_THR}–{THRESHOLD}): {len(pending_cands)}")

    # ── Write to Neo4j ────────────────────────────────────────────────────────
    sigle_to_course = {c["sigle"]: c for c in courses}

    with driver.session() as session:
        written = session.execute_write(
            lambda tx: write_inferred_batch(tx, [
                {
                    "sigle_a":    a,
                    "sigle_b":    b,
                    "confidence": round(score, 4),
                    "evidence":   f"embed_cosine={score:.4f}",
                    "status":     st,
                }
                for a, b, score, st in candidates
            ])
        )

        after_total = session.run(
            "MATCH ()-[r:EQUIVAUT_A]->() RETURN count(r) AS n"
        ).single()["n"]
        after_inferred = session.run(
            "MATCH ()-[r:EQUIVAUT_A {source: $s}]->() RETURN count(r) AS n",
            s=INFERRED,
        ).single()["n"]

    driver.close()

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\nEdges after  — total: {after_total}  (inferred: {after_inferred})")
    print(f"New inferred edges written: {written}  (active: {len(active_cands)}, pending: {len(pending_cands)})")

    # Breakdown by university pair
    pair_counts: dict[str, int] = defaultdict(int)
    pair_fr_en:  dict[str, int] = defaultdict(int)
    for a, b, _, _st in candidates:
        ca = sigle_to_course[a]
        cb = sigle_to_course[b]
        key = f"{ca['universite']}↔{cb['universite']}"
        pair_counts[key] += 1
        if lang(ca["universite"]) != lang(cb["universite"]):
            pair_fr_en[key] += 1

    print(f"\nBreakdown by university pair (active + pending):")
    for key, n in sorted(pair_counts.items(), key=lambda x: -x[1]):
        fr_en = pair_fr_en.get(key, 0)
        tag = f"  ({fr_en} FR↔EN)" if fr_en else ""
        print(f"  {key:<25} {n:>4}{tag}")

    print(f"\nTop 25 pairs by confidence:")
    print(f"  {'Score':>6}  {'Status':<8} {'A':<22} {'B':<22} {'Direction'}")
    print(f"  {'─'*6}  {'─'*8} {'─'*22} {'─'*22} {'─'*20}")
    for a, b, score, st in candidates[:25]:
        ca = sigle_to_course.get(a, {})
        cb = sigle_to_course.get(b, {})
        direction = f"[{ca.get('universite','')}↔{cb.get('universite','')}] {lang(ca.get('universite',''))}↔{lang(cb.get('universite',''))}"
        print(f"  {score:.4f}  {st:<8} {a:<22} {b:<22} {direction}")


if __name__ == "__main__":
    main()
