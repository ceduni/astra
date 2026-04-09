"""
Layer 2 prerequisite extraction: regex pass over requirement_text.

Extracts course codes that appear as plain text but were not captured
as structured prerequisites by the HTML scraper (Layer 1).

Strategy:
  - Only add codes that are known to exist in the university's own
    course catalogue (known_sigles) — prevents dangling references.
  - Skip codes listed in equivalent_courses — those are substitutes,
    not prerequisites.
  - Skip codes already in prerequisite_courses — no duplicates.

Corequisites ("completed previously or concurrently") are intentionally
promoted to prerequisites — the conservative choice for a planning tool.
"""

import re
from typing import List, Set

# Matches both formats:
#   no-space : IFT1015, MAT1400, LOG2400, INF1010
#   with-space: COMP 248, MATH 203, SOEN 331
_CODE_RE = re.compile(r'\b([A-Z]{2,4}(?:\s\d{3}|\d{4})[A-Z]?)\b')

# Text fragments that introduce exclusion clauses rather than prerequisites.
# Codes following these patterns should NOT be added.
_EXCLUSION_RE = re.compile(
    r'(not open to|may not take|credit for|registered in|'
    r'equivalent to|cannot be taken|cannot take|exclu)',
    re.IGNORECASE,
)


def extract_from_text(
    requirement_text: str,
    known_sigles: Set[str],
    already_present: List[str],
    equivalents: List[str],
) -> List[str]:
    """
    Return a list of course codes found in requirement_text that should be
    added to prerequisite_courses (not already present, not equivalents,
    not in exclusion clauses, and known to exist in the catalogue).
    """
    if not requirement_text:
        return []

    present = set(already_present)
    excluded = set(equivalents)
    new_codes: List[str] = []

    # Split text into segments; any segment following an exclusion keyword
    # is treated as an exclusion context and its codes are ignored.
    segments = _EXCLUSION_RE.split(requirement_text.upper())
    # segments alternates: [normal, separator, normal, separator, ...]
    # We skip every segment at an odd index (the separator itself) and
    # the segment immediately after it.
    safe_text_parts = []
    i = 0
    skip_next = False
    for part in segments:
        if skip_next:
            skip_next = False
            continue
        if _EXCLUSION_RE.match(part):
            skip_next = True
            continue
        safe_text_parts.append(part)

    safe_text = ' '.join(safe_text_parts)

    for match in _CODE_RE.finditer(safe_text):
        code = match.group(1).strip()
        # Normalise internal whitespace (handles "COMP  248" edge cases)
        code = re.sub(r'\s+', ' ', code)
        if code in known_sigles and code not in present and code not in excluded:
            present.add(code)  # deduplicate within this call
            new_codes.append(code)

    return new_codes


def augment_prerequisites(courses: List[dict]) -> dict:
    """
    Given a list of canonical course dicts (all courses for one university),
    run the Layer 2 regex pass and return a stats dict:
      {"added": int, "courses_affected": int}

    Mutates courses in place.
    """
    known_sigles = {c['sigle'] for c in courses}
    total_added = 0
    courses_affected = 0

    for course in courses:
        new = extract_from_text(
            requirement_text=course.get('requirement_text', ''),
            known_sigles=known_sigles,
            already_present=course.get('prerequisite_courses', []),
            equivalents=course.get('equivalent_courses', []),
        )
        if new:
            course['prerequisite_courses'] = course.get('prerequisite_courses', []) + new
            total_added += len(new)
            courses_affected += 1

    return {'added': total_added, 'courses_affected': courses_affected}
