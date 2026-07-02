"""
Infer course equivalences using multilingual sentence embeddings.

Model: paraphrase-multilingual-MiniLM-L12-v2
  Maps 50+ languages into a shared 384-dim space — handles FR↔EN pairs
  that TF-IDF cannot reach (zero shared vocabulary across languages).

Category-filtered matching (primary path):
  Each course is assigned one or more canonical categories based on its
  segment in the program JSONs (programs/*.json). Only courses that share
  at least one category are compared. This eliminates cross-domain noise
  (e.g. a database course matching a networking course) and allows a lower
  threshold — maximising recall for the student-facing equivalence view.

  Canonical categories: programming, algorithms_theory, systems,
  software_engineering, math, data, ai

  Courses not in any program JSON (mostly grad-level or out-of-scope) fall
  back to the original global thresholds with no category filter.

Thresholds:
  CAT_ACTIVE   = 0.65  within-category active   (lowered from 0.70)
  CAT_PENDING  = 0.55  within-category pending  (lowered from 0.58)
  THRESHOLD    = 0.78  no-category fallback active
  PENDING_THR  = 0.70  no-category fallback pending
  POLY_ETS_THR = 0.65  Poly↔ETS same-prefix within-category (was 0.72)

Scope: all courses with description > 30 chars, filtered to same academic
  cycle. Cycle is inferred from hors_perimetre: false → 1er cycle.

Usage:
  python etl/embed_equivalences.py
"""

import json
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

# Within-category thresholds (lower = more recall)
CAT_ACTIVE   = 0.65
CAT_PENDING  = 0.55

# Fallback thresholds for courses not in any program JSON
THRESHOLD    = 0.78
PENDING_THR  = 0.70

# Poly↔ETS same-prefix bonus (within-category)
POLY_ETS_THR = 0.65

MIN_DESC_LEN = 30

FR_UNIS = {"UdeM", "UQAM", "Poly", "ETS"}
EN_UNIS = {"McGill", "Concordia"}

PREFIX_RE = re.compile(r"^([A-Z]+)", re.ASCII)
LEVEL_RE  = re.compile(r"(\d)")

SKIP_TITLE_WORDS = {
    "project", "projet", "capstone", "stage", "internship",
    "intégrateur", "integrateur", "honor", "honours", "honors",
    "independent", "topics", "sujets",
}


def code_prefix(sigle: str) -> str:
    m = PREFIX_RE.match(sigle.upper().replace(" ", ""))
    return m.group(1) if m else ""


def course_level(sigle: str) -> int | None:
    m = LEVEL_RE.search(sigle)
    return int(m.group(1)) if m else None


def is_skip_title(titre: str) -> bool:
    words = re.split(r"[\s\-/]+", (titre or "").lower())
    return bool(SKIP_TITLE_WORDS.intersection(words))


def build_category_index(programs_dir: Path) -> dict[str, set[str]]:
    """
    Returns sigle → set[category] by reading all program JSONs.
    Handles both flat segments and UdeM's two-level group→bloc structure.
    Courses with no category assignment (empty list) are not added to the index,
    so they fall back to the global threshold path.
    """
    sigle_cats: dict[str, set[str]] = defaultdict(set)

    for path in programs_dir.glob("*.json"):
        prog = json.loads(path.read_text())
        segments = prog.get("segments", {})

        for seg_id, seg in segments.items():
            if not isinstance(seg, dict):
                continue

            if "cours" in seg:
                # Flat segment
                cats = seg.get("category", [])
                if cats:
                    for sigle in seg.get("cours", []):
                        sigle_cats[sigle].update(cats)
            else:
                # Two-level structure (UdeM): iterate blocs inside the group
                for bloc_id, bloc in seg.items():
                    if not isinstance(bloc, dict):
                        continue
                    cats = bloc.get("category", [])
                    if cats:
                        for sigle in bloc.get("cours", []):
                            sigle_cats[sigle].update(cats)

    return dict(sigle_cats)


def fetch_courses(session) -> list:
    return [dict(r["c"]) for r in session.run("MATCH (c:Cours) RETURN c")]


def course_cycle(c: dict) -> int:
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
    programs_dir = Path(__file__).parents[1] / "programs"
    sigle_cats = build_category_index(programs_dir)

    categorised = sum(1 for cats in sigle_cats.values() if cats)
    print(f"Category index: {categorised} courses assigned to at least one category")
    cat_counts: dict[str, int] = defaultdict(int)
    for cats in sigle_cats.values():
        for c in cats:
            cat_counts[c] += 1
    for cat, n in sorted(cat_counts.items()):
        print(f"  {cat:<25} {n:>4} courses")

    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )

    with driver.session() as session:
        all_courses = fetch_courses(session)

        before_total = session.run(
            "MATCH ()-[r:EQUIVAUT_A]->() RETURN count(r) AS n"
        ).single()["n"]
        before_inferred = session.run(
            "MATCH ()-[r:EQUIVAUT_A {source: $s}]->() RETURN count(r) AS n",
            s=INFERRED,
        ).single()["n"]
        print(f"\nEdges before — total: {before_total}  (inferred: {before_inferred})")

        for uni in {c["universite"] for c in all_courses}:
            clear_inferred_equivalences(session, uni)
        covered_pairs = fetch_covered_pairs(session)

    courses = [
        c for c in all_courses
        if c.get("description") and len(c["description"]) > MIN_DESC_LEN
        and not is_skip_title(c.get("titre", ""))
    ]
    skipped_titles = sum(
        1 for c in all_courses
        if c.get("description") and len(c["description"]) > MIN_DESC_LEN
        and is_skip_title(c.get("titre", ""))
    )
    print(f"Skipped {skipped_titles} courses with project/capstone/stage titles")

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
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    sigle_to_idx = {c["sigle"]: i for i, c in enumerate(courses)}

    uni_names  = sorted(by_uni.keys())
    candidates = []
    skipped_domain = 0
    cat_filtered   = 0
    fallback_pairs = 0

    for i_u, uni_a in enumerate(uni_names):
        for uni_b in uni_names[i_u + 1:]:
            items_a = by_uni[uni_a]
            items_b = by_uni[uni_b]
            is_poly_ets = {uni_a, uni_b} == {"Poly", "ETS"}

            idxs_a = [sigle_to_idx[c["sigle"]] for c in items_a]
            idxs_b = [sigle_to_idx[c["sigle"]] for c in items_b]
            emb_a  = embeddings[idxs_a]
            emb_b  = embeddings[idxs_b]
            sims   = emb_a @ emb_b.T

            for row_i, ca in enumerate(items_a):
                for col_j, cb in enumerate(items_b):
                    score = float(sims[row_i, col_j])
                    pair  = tuple(sorted((ca["sigle"], cb["sigle"])))

                    if pair in covered_pairs:
                        continue
                    if course_cycle(ca) != course_cycle(cb):
                        continue

                    lv_a, lv_b = course_level(ca["sigle"]), course_level(cb["sigle"])
                    if lv_a is not None and lv_b is not None and abs(lv_a - lv_b) > 1:
                        continue

                    cats_a = sigle_cats.get(ca["sigle"], set())
                    cats_b = sigle_cats.get(cb["sigle"], set())
                    both_categorised = bool(cats_a) and bool(cats_b)
                    shared = cats_a & cats_b

                    # Both courses are in the category index but share no category → skip
                    if both_categorised and not shared:
                        skipped_domain += 1
                        continue

                    if both_categorised and shared:
                        # Within-category path: lower thresholds
                        cat_filtered += 1
                        if is_poly_ets:
                            same_prefix = (
                                code_prefix(ca["sigle"]) == code_prefix(cb["sigle"])
                                and code_prefix(ca["sigle"]) != ""
                            )
                            thr_active  = POLY_ETS_THR if same_prefix else CAT_ACTIVE
                            thr_pending = CAT_PENDING
                        else:
                            thr_active  = CAT_ACTIVE
                            thr_pending = CAT_PENDING
                    else:
                        # Fallback: at least one course not in any program JSON
                        fallback_pairs += 1
                        if is_poly_ets:
                            same_prefix = (
                                code_prefix(ca["sigle"]) == code_prefix(cb["sigle"])
                                and code_prefix(ca["sigle"]) != ""
                            )
                            thr_active  = POLY_ETS_THR if same_prefix else THRESHOLD
                            thr_pending = PENDING_THR
                        else:
                            thr_active  = THRESHOLD
                            thr_pending = PENDING_THR

                    if score >= thr_active:
                        candidates.append((ca["sigle"], cb["sigle"], score, "active"))
                    elif score >= thr_pending:
                        candidates.append((ca["sigle"], cb["sigle"], score, "pending"))

    candidates.sort(key=lambda x: -x[2])
    active_cands  = [c for c in candidates if c[3] == "active"]
    pending_cands = [c for c in candidates if c[3] == "pending"]

    print(f"\nPairs evaluated:")
    print(f"  Within-category (lower threshold): {cat_filtered:>7}")
    print(f"  Cross-domain skipped:              {skipped_domain:>7}")
    print(f"  Fallback (uncategorised):          {fallback_pairs:>7}")
    print(f"  Active candidates  (≥{CAT_ACTIVE} cat / {THRESHOLD} fallback): {len(active_cands)}")
    print(f"  Pending candidates ({CAT_PENDING}–{CAT_ACTIVE} cat / {PENDING_THR}–{THRESHOLD} fallback): {len(pending_cands)}")

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

    print(f"\nEdges after  — total: {after_total}  (inferred: {after_inferred})")
    print(f"New inferred edges written: {written}  (active: {len(active_cands)}, pending: {len(pending_cands)})")

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

    print(f"\nTop 30 pairs by confidence:")
    print(f"  {'Score':>6}  {'Status':<8} {'A':<22} {'B':<22} {'Shared cats'}")
    print(f"  {'─'*6}  {'─'*8} {'─'*22} {'─'*22} {'─'*20}")
    for a, b, score, st in candidates[:30]:
        shared = sigle_cats.get(a, set()) & sigle_cats.get(b, set())
        cats_str = ",".join(sorted(shared)) if shared else "—"
        print(f"  {score:.4f}  {st:<8} {a:<22} {b:<22} {cats_str}")


if __name__ == "__main__":
    main()
