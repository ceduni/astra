"""
Sample test: can Playwright defeat the Incapsula JS challenge on Poly course
pages? Run against 10 missing courses and report what we'd recover.

Decision criterion for the full Playwright recovery: report which fraction
of probed courses yield real course-level prereqs (vs admin notes like
'70 crédits' which are not modellable as edges).

  .venv-playwright/bin/python etl/poly/playwright_sample.py
"""

import asyncio
import re
import time
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE = "https://www.polymtl.ca/programmes/cours"

# Bucket A targets (totally empty in current data), 200/300/400-level
# CS-adjacent — where prereq structure is most useful for eligibility.
SAMPLES = [
    "inf3710",  # Fichiers et bases de données
    "inf8480",  # Systèmes répartis et infonuagique
    "inf8175",  # IA: méthodes et algorithmes
    "inf8775",  # Analyse et conception d'algorithmes
    "log3210",  # Éléments de langages et compilateurs
    "log3420",  # Analyse et spécif. des exigences
    "log3430",  # Méthodes de test et de validation
    "log8430",  # Architecture logicielle avancée
    "log2420",  # Anal. et conc. des IU
    "log8371",  # Ingénierie de la qualité en logiciel
]

SIGLE_RE = re.compile(r"\b([A-Z]{2,4}\d{4}[A-Z]?)\b")


def parse_course_page(html: str) -> dict:
    """Apply the same parsing logic the fetcher would use."""
    soup = BeautifulSoup(html, "html.parser")
    node = soup.find("div", class_="node--cours") or soup.find("div", class_=re.compile("cours"))

    desc = ""
    details_text = ""
    prereq_links: list[str] = []

    if node:
        desc_div = node.find("div", class_="desc")
        if desc_div:
            desc = desc_div.get_text(" ", strip=True)

        details_div = node.find("div", class_="details")
        if details_div:
            details_text = details_div.get_text(" ", strip=True)
            # Extract prereq codes both as <a> links and as plain text
            for a in details_div.find_all("a"):
                code = a.get_text(strip=True).upper()
                if SIGLE_RE.match(code):
                    prereq_links.append(code)

    # Layer-2-style regex over details_text (codes mentioned in plain text)
    text_codes = list(dict.fromkeys(SIGLE_RE.findall(details_text.upper())))

    return {
        "has_desc": bool(desc),
        "desc_preview": desc[:80],
        "details_preview": details_text[:120],
        "prereq_links": list(dict.fromkeys(prereq_links)),
        "text_codes": text_codes,
    }


async def fetch_one(context, slug: str) -> Optional[dict]:
    page = await context.new_page()
    url = f"{BASE}/{slug}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        # Incapsula JS challenge can take a few seconds; wait for real content
        try:
            await page.wait_for_selector("div.node--cours, div.desc, div.details",
                                         timeout=20_000)
        except Exception:
            pass  # Maybe page rendered without those divs; parse anyway
        html = await page.content()
    except Exception as e:
        await page.close()
        return {"error": f"{type(e).__name__}: {e}"}

    await page.close()

    is_incap = "_Incapsula_" in html and len(html) < 5000
    result = {
        "slug":      slug,
        "bytes":     len(html),
        "incapsula": is_incap,
    }
    if not is_incap:
        result.update(parse_course_page(html))
    return result


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
            viewport={"width": 1280, "height": 800},
            locale="fr-CA",
        )

        # Warm up: visit the program page once so Incapsula cookies are set
        warmup = await context.new_page()
        await warmup.goto("https://www.polymtl.ca/programmes/programmes/bc-informatique",
                          wait_until="domcontentloaded", timeout=30_000)
        try:
            await warmup.wait_for_selector("table.tableau-cours", timeout=20_000)
            print("  warmup: program page loaded ok")
        except Exception:
            print("  warmup: program page selector not found (may still have cookies)")
        await warmup.close()

        results = []
        for slug in SAMPLES:
            t0 = time.time()
            r = await fetch_one(context, slug)
            r["elapsed_s"] = round(time.time() - t0, 1)
            results.append(r)
            print(f"  {slug:10s} {r.get('elapsed_s'):>4}s  "
                  f"bytes={r.get('bytes', 0):>6}  "
                  f"incap={r.get('incapsula', '-')}  "
                  f"desc={r.get('has_desc', '-')}  "
                  f"links={r.get('prereq_links', [])}  "
                  f"text_codes={r.get('text_codes', [])}")

        await browser.close()

    # Summary
    print("\n── summary ──")
    n = len(results)
    n_incap = sum(1 for r in results if r.get("incapsula"))
    n_ok = sum(1 for r in results if r.get("has_desc"))
    n_with_links = sum(1 for r in results if r.get("prereq_links"))
    n_with_text_codes = sum(1 for r in results if r.get("text_codes"))
    print(f"  probed:                  {n}")
    print(f"  still Incapsula:         {n_incap}")
    print(f"  page loaded (has desc):  {n_ok}")
    print(f"  prereq <a> links found:  {n_with_links}")
    print(f"  prereq codes in text:    {n_with_text_codes}")


if __name__ == "__main__":
    asyncio.run(main())
