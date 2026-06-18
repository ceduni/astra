"""
Recover missing Poly course data using the new title-slug URL pattern.

Poly retired the /programmes/cours/{sigle.lower()} URL scheme. The catalogue
now exposes courses at /programmes/cours/{title-slug} and the sigle→slug
mapping is discoverable via /programmes/cours/par-critere?sigle={PREFIX}.

Pipeline:
  1. Read raw_courses.json. Identify courses with no description, no prereqs,
     and no requirement_text — these are the fetch failures from the original
     scrape.
  2. For each unique 3-letter subject prefix in the missing set, fetch the
     par-critere list page and harvest sigle → title-slug.
  3. Visit each detail page (Playwright defeats Incapsula), parse
     Préalable(s) / Corequis / Description from div.details + div.desc.
  4. Write the recovered records to raw_courses_recovered.json (audit log).
  5. Merge into raw_courses.json — only fill empty fields, never overwrite.

Idempotent: re-running re-fetches only courses still missing data.

Usage:
  .venv-playwright/bin/python etl/poly/playwright_recover.py
"""

import asyncio
import json
import re
import shutil
import time
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


ROOT      = Path(__file__).parent
RAW_FILE  = ROOT / "raw_courses.json"
RECOVERED = ROOT / "raw_courses_recovered.json"
BACKUP    = ROOT / "raw_courses.backup.json"

BASE = "https://www.polymtl.ca"
UA   = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36")

SIGLE_RE = re.compile(r"\b([A-Z]{2,4}\d{4}[A-Z]?)\b")


# ── Identify what needs recovery ─────────────────────────────────────────────

def missing_courses(raw: dict) -> list[dict]:
    """Courses with no description, no prereqs, and no requirement_text."""
    all_courses = raw["courses"]["PROGRAM"] + raw["courses"]["OTHER"]
    return [
        c for c in all_courses
        if not c.get("description")
        and not c.get("prerequisite_courses")
        and not c.get("requirement_text")
    ]


# ── Slug discovery ───────────────────────────────────────────────────────────

async def discover_slugs(ctx, prefixes: set[str]) -> dict[str, str]:
    """For each 3-letter prefix, harvest sigle → title-slug from par-critere."""
    mapping: dict[str, str] = {}
    for prefix in sorted(prefixes):
        url = f"{BASE}/programmes/cours/par-critere?sigle={prefix}"
        page = await ctx.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            await page.wait_for_timeout(1500)
            rows = await page.evaluate(
                """() => Array.from(document.querySelectorAll('tr')).map(tr => {
                    const cells = tr.querySelectorAll('td');
                    if (cells.length < 2) return null;
                    const sigle = cells[0].innerText.trim();
                    const link  = cells[1].querySelector('a[href*="/programmes/cours/"]');
                    return link ? {sigle, href: link.href} : null;
                }).filter(Boolean)"""
            )
        finally:
            await page.close()

        before = sum(1 for s in mapping if s.startswith(prefix))
        for row in rows:
            m = SIGLE_RE.search(row["sigle"])
            if not m:
                continue
            sigle = m.group(1)
            slug = row["href"].rstrip("/").split("/")[-1]
            # Skip par-critere/horaire/etc. — only real detail slugs
            if slug and not slug.startswith(("par-critere", "horaire")):
                mapping.setdefault(sigle, slug)
        after = sum(1 for s in mapping if s.startswith(prefix))
        print(f"  [{prefix}] +{after - before} slugs  (total {after})")
    return mapping


# ── Detail page parsing ──────────────────────────────────────────────────────

_SECTION_RE = re.compile(
    r"(Préalable\(s\)|Corequis|Notes|Responsable\(s\)|Site web)\s*:?",
    re.IGNORECASE,
)
_SECTION_KEY = {
    "préalable(s)": "prereq",
    "corequis":     "coreq",
    "notes":        "note",
    "responsable(s)": None,
    "site web":     None,
}


def parse_detail(html: str) -> dict:
    """Extract description, credits, prereqs, corequis, requirement_text.

    Uses a single-line flat text + regex section split. Earlier line-scan
    approach silently dropped 2nd+ codes when BS4 inserted newlines between
    text nodes (e.g. between <a> tags inside the Préalable line).
    """
    soup = BeautifulSoup(html, "html.parser")

    desc_div = soup.find("div", class_="desc")
    description = desc_div.get_text(" ", strip=True) if desc_div else ""
    if description.lower().startswith("description"):
        description = description[len("description"):].strip()

    details_div = soup.find("div", class_="details")
    sections: dict[str, str] = {"prereq": "", "coreq": "", "note": ""}

    if details_div:
        # Flat single-line text — every text node joined by space, no newlines
        text = details_div.get_text(" ", strip=True)
        # Split by section labels; result alternates [pre-text, label, body, label, body, ...]
        parts = _SECTION_RE.split(text)
        for i in range(1, len(parts) - 1, 2):
            label = parts[i].strip().lower()
            body  = parts[i + 1].strip(" :\xa0")
            key   = _SECTION_KEY.get(label)
            if key and not sections[key]:
                sections[key] = body

    prereqs = list(dict.fromkeys(SIGLE_RE.findall(sections["prereq"])))
    coreqs  = list(dict.fromkeys(SIGLE_RE.findall(sections["coreq"])))
    prereq_line = sections["prereq"]
    coreq_line  = sections["coreq"]
    note_line   = sections["note"]

    # Credits — scan full HTML, cap at 15 to avoid catching degree totals
    credits = 0.0
    m = re.search(r"\b(\d{1,2}(?:[.,]\d)?)\s*cr[ée]dit", html, re.I)
    if m:
        v = float(m.group(1).replace(",", "."))
        if v <= 15:
            credits = v

    # requirement_text mirrors the original scraper's format: concatenated subsections
    req_text = " ".join(s for s in (prereq_line, coreq_line, note_line) if s).strip()

    return {
        "description":          description,
        "credits":              credits,
        "prerequisite_courses": prereqs,
        "concomitant_courses":  coreqs,
        "requirement_text":     req_text,
    }


# ── Fetch one detail page ────────────────────────────────────────────────────

async def fetch_course(ctx, slug: str) -> dict:
    url = f"{BASE}/programmes/cours/{slug}"
    page = await ctx.new_page()
    try:
        try:
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            try:
                await page.wait_for_selector("div.details", timeout=15_000)
            except Exception:
                pass
            html = await page.content()
        except Exception as e:
            return {"_error": f"{type(e).__name__}: {e}"}
    finally:
        await page.close()

    if "_Incapsula_" in html and len(html) < 5000:
        return {"_error": "incapsula"}

    return parse_detail(html)


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    raw = json.loads(RAW_FILE.read_text())
    needed = missing_courses(raw)
    print(f"Courses needing recovery: {len(needed)}")
    if not needed:
        print("Nothing to do.")
        return

    prefixes = {c["id"][:3] for c in needed}
    print(f"Subject prefixes: {sorted(prefixes)}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="fr-CA",
                                        viewport={"width": 1280, "height": 800})

        # Warm up cookies on the directory page
        warmup = await ctx.new_page()
        await warmup.goto(f"{BASE}/programmes/cours",
                          wait_until="networkidle", timeout=30_000)
        await warmup.wait_for_timeout(1500)
        await warmup.close()

        print("\n── Discovering slugs ──")
        slug_map = await discover_slugs(ctx, prefixes)
        print(f"Total slugs discovered: {len(slug_map)}")

        print("\n── Fetching detail pages ──")
        recovered: dict[str, dict] = {}
        for i, course in enumerate(needed, 1):
            sigle = course["id"]
            slug = slug_map.get(sigle)
            if not slug:
                recovered[sigle] = {"_error": "no slug discovered"}
                print(f"  [{i:3d}/{len(needed)}] {sigle:10s} NO SLUG")
                continue

            t0 = time.time()
            detail = await fetch_course(ctx, slug)
            elapsed = time.time() - t0
            recovered[sigle] = {**detail, "_slug": slug}

            if detail.get("_error"):
                tag = f"ERR ({detail['_error'][:25]})"
                extra = ""
            else:
                tag = "OK"
                extra = f"  ← {detail.get('prerequisite_courses', [])}" \
                    if detail.get("prerequisite_courses") else "  ← (no prereq)"
            print(f"  [{i:3d}/{len(needed)}] {sigle:10s} {tag:30s} "
                  f"{elapsed:4.1f}s  {slug[:35]:35s}{extra}")

        await browser.close()

    # Write audit log
    RECOVERED.write_text(json.dumps(recovered, ensure_ascii=False, indent=2))
    print(f"\nAudit log: {RECOVERED}")

    # Back up raw_courses.json once
    if not BACKUP.exists():
        shutil.copy(RAW_FILE, BACKUP)
        print(f"One-time backup: {BACKUP}")

    # Merge — only fill empty fields. Skip _slug and _error metadata.
    merged_fields = 0
    for section in ("PROGRAM", "OTHER"):
        for course in raw["courses"][section]:
            rec = recovered.get(course["id"])
            if not rec or rec.get("_error"):
                continue
            for field in ("description", "prerequisite_courses",
                          "concomitant_courses", "requirement_text"):
                if not course.get(field) and rec.get(field):
                    course[field] = rec[field]
                    merged_fields += 1
            if not course.get("credits") and rec.get("credits"):
                course["credits"] = rec["credits"]
                merged_fields += 1

    RAW_FILE.write_text(json.dumps(raw, ensure_ascii=False, indent=2))

    # Summary
    successes      = sum(1 for r in recovered.values() if not r.get("_error"))
    with_prereqs   = sum(1 for r in recovered.values() if r.get("prerequisite_courses"))
    errors         = sum(1 for r in recovered.values() if r.get("_error"))
    no_slug        = sum(1 for r in recovered.values() if r.get("_error") == "no slug discovered")

    print(f"\n── Recovery summary ──")
    print(f"  attempted:       {len(needed)}")
    print(f"  page loads:      {successes}")
    print(f"  with new prereq: {with_prereqs}")
    print(f"  errors:          {errors}  (no-slug: {no_slug})")
    print(f"  fields merged:   {merged_fields}")
    print(f"\nNext: python3 etl/poly/transform.py && python3 etl/poly/load_neo4j.py")


if __name__ == "__main__":
    asyncio.run(main())
