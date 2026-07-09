# Astra — Cours Interuniversitaire

Astra is a student-facing tool that helps university students in Montreal navigate inter-university course equivalences, plan their programs, and discover courses they can take at partner institutions (UdeM, UQAM, McGill, Concordia, Poly, ETS).

The core problem: students don't know which courses at other universities count toward their degree, and the official equivalence tables are hard to find and harder to read. Astra surfaces these connections visually.

---

# Product Vision

The long-term vision is a **student roadmap**: given a student's home university, program, completed courses, and orientation, Astra shows:

1. What courses are **available now** (all prerequisites satisfied), grouped by academic requirement block
2. What opens up **next** (one wave out), same grouping
3. Where equivalences from other universities can substitute for remaining requirements

The tone is a student advisor, not a database browser. Academic logic (ET/OU prerequisite nodes) is translated into human-readable segment clusters ("Programmation · OBLIGATOIRE · 9/15 cr"). The student reads their degree as a **roadmap**, not a graph.

---

# Current UX Direction

## What we decided

After multiple design iterations, the chosen approach is:

**Segment-cluster roadmap** — not a graph, not a flat list. Courses are grouped into requirement clusters that match the program structure (e.g. "Programmation", "Théorie et algorithmique", "Cours complémentaires"). Each cluster shows:
- A human-readable label
- A type badge (OBLIGATOIRE / OPTION / LIBRE)
- A credit progress bar (completed / max)
- Course cards for currently available courses

The roadmap has three horizontal sections:
- **Cours complétés** (green anchor on the left)
- **Disponible maintenant** (segment clusters in the center)
- **Et ensuite →** (reveals the next wave on click, same cluster format)

## What we explicitly rejected

- **Raw ET/OU graph nodes** in the roadmap view — confusing, developer-oriented. ET/OU logic is computed but never shown as graph nodes.
- **Per-course expansion** (clicking a course to expand its prerequisites into the graph) — the old graph model. The roadmap replaces this.
- **Hiding academic structure** — the opposite mistake. Segments map to real UdeM/McGill/etc. requirement blocks so students recognize the structure from their program guide.
- **Capping available courses** — for advanced students with many available courses, we organize them by segment, not hide them.

## Substitution mechanic (built, not active in roadmap V1)

The detail panel supports course substitution: the student can replace a remaining course with an equivalent from another university. The substituted node shows a dashed border, "via [Uni]" badge, and original sigle subtitle. This is wired in `ExplorationPage.jsx` and `graphShared.jsx` but not surfaced in the V1 roadmap UI.

---

# Technical Architecture

## Stack

```
etl/                      Python scripts — fetch, transform, load to Neo4j
  udem/
    fetch_courses.py      Fetch IFT + MAT courses from Planifium API
    tag_courses.py        Tag courses with topic labels (against Aura)
  embed_equivalences.py   Multilingual sentence embeddings (paraphrase-multilingual-MiniLM-L12-v2) → inferred equivalences (→ Aura)
  load_official_equivs.py Official equivalence table → Aura

api/                      FastAPI backend
  main.py                 App entrypoint, mounts routers
  database.py             Neo4j driver (singleton, reads NEO4J_URI env var)
  routes/
    courses.py            All course/program/equivalence endpoints
    admin.py              Admin auth, equivalence lifecycle, change-detection flagging

web/                      React 19 + Vite frontend
  src/
    App.jsx               Single-page shell — ExplorationPage by default, AdminPanel toggled via topbar button
    shared.jsx            Shared components: SearchSection, CompletedSection, useUniversities
    graphShared.jsx       Shared graph primitives: CourseNode, GroupNode, applyLayout, NODE_TYPES
    ExplorationPage.jsx   Roadmap page shell + sidebar + detail panel
    RoadmapView.jsx       V1 roadmap renderer
    AdminPanel.jsx        Admin login, pending queue, equivalence table, notification bell
    ExplorationGraph.jsx  DEPRECATED — dead code, can be deleted

vercel.json               ROOT-level — SPA routing + API proxy rewrites (see Deployment)
                          Do NOT confuse with web/vercel.json which no longer holds rewrites

programs/                 Program JSON files — one per university × program
  udem_informatique.json
  mcgill_computer_science.json
  concordia_computer_science.json
  uqam_informatique_genie_logiciel.json
  poly_genie_informatique.json
  poly_genie_logiciel.json
  ets_genie_logiciel.json
  ets_genie_technologies_information.json
```

## Deployment

| Layer | Platform | URL |
|-------|----------|-----|
| Frontend | Vercel | `https://astra-beta-chi.vercel.app` |
| Backend | Railway | `https://astra-beta-production.up.railway.app` |
| Database | Neo4j Aura | `neo4j+s://7707976b.databases.neo4j.io` |

The root `vercel.json` sets `installCommand`, `buildCommand`, `outputDirectory` to scope Vercel to the `web/` subdirectory (prevents Python build detection), and rewrites `/api/*` → Railway for production. Vite's dev proxy (`vite.config.js`) handles the same rewrite locally.

## Local development

Three terminals:
```bash
# Terminal 1: API
python3 -m uvicorn api.main:app --reload --port 8001

# Terminal 2: Frontend
cd web && npm run dev
# Vite proxies /api → localhost:8001 (see vite.config.js)

# Terminal 3: (optional) ETL scripts as needed
```

---

## Admin Authentication

### Account model

Every admin account has exactly one `university` scope. There is no super-admin. University-scoped admins see only equivalences where their university is one of the two endpoint courses.

The `university` value in an account **must match the `universite` field stored on `Cours` nodes in Neo4j exactly** (case-sensitive). Verify valid values with:
```cypher
MATCH (c:Cours) RETURN DISTINCT c.universite ORDER BY c.universite
```

### Primary: `ADMIN_ACCOUNTS` env var

Set this env var to a JSON array. Each entry requires `username`, `password`, and `university`:

```json
[
  {"username": "admin_udem",      "password": "...", "university": "UdeM"},
  {"username": "admin_concordia", "password": "...", "university": "Concordia"},
  {"username": "admin_ets",       "password": "...", "university": "ÉTS"},
  {"username": "admin_poly",      "password": "...", "university": "Poly"},
  {"username": "admin_mcgill",    "password": "...", "university": "McGill"},
  {"username": "admin_uqam",      "password": "...", "university": "UQAM"}
]
```

On Railway: set `ADMIN_ACCOUNTS` as a single-line JSON string. The API parses it on each request.

**Passwords are plaintext in the prototype.** TODO: replace with bcrypt hashing before any public-facing deployment. See `require_admin()` in `api/routes/admin.py`.

### Fallback: legacy single-account env vars

If `ADMIN_ACCOUNTS` is not set, the API falls back to:
```
ADMIN_USER        (default: admin)
ADMIN_PASSWORD    (default: astra-admin)
ADMIN_UNIVERSITY  (optional — if unset, no university scoping is applied)
```

This is backward-compatible with the original single-admin setup. Remove these once `ADMIN_ACCOUNTS` is confirmed working in production.

### What university scoping controls

- `GET /admin/equivalences` — automatically filters to equivalences where either endpoint course belongs to the admin's university
- `GET /admin/equivalences/pending` — inferred pending items + any `needs_review` item (any source) for the admin's university. Filter: `(source='inferred' AND status='pending') OR status='needs_review'`
- `POST /admin/equivalences` — `created_by` is stamped from the authenticated username
- All other endpoints (approve, revoke, skip, restore) are not university-gated at the query level — an admin can technically act on any equivalence ID they know. This is acceptable for the prototype.

### Admin endpoints summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/me` | Returns `{username, university}` for the authenticated account |
| GET | `/admin/equivalences` | List equivalences (scoped to admin's university) |
| GET | `/admin/equivalences/pending` | Inferred + needs_review items for the admin's university |
| POST | `/admin/equivalences` | Create equivalence (`source: admin_created`, `evidence` required) |
| PATCH | `/admin/equivalences/{id}/approve` | Confirm valid — sets `status = active`, stamps `approved_by` |
| PATCH | `/admin/equivalences/{id}/skip` | Pass without approval — sets `status = active`, clears flags |
| PATCH | `/admin/equivalences/{id}/reject` | Revoke — sets `status = revoked` |
| PATCH | `/admin/equivalences/{id}/restore` | Re-activate a revoked equivalence |
| DELETE | `/admin/equivalences/{id}` | Soft-delete (same as reject) |

---

## Content-hash change detection

`Cours` nodes carry a `content_hash` field: a SHA-256 (truncated to 16 hex chars) of `titre + credits + description`. On every ETL run, `merge_cours()` in `etl/prereq_parser.py` compares the stored hash against the new values. If they differ, it:

1. Updates `content_hash` and sets `changed_at = now` on the course node
2. Flags all `active` or `needs_review` edges of source `admin_created`, `official_table`, or `official` involving that course: sets `status = needs_review`, `flagged_at`, `flag_reason` (e.g. `"credits: 3 → 4"`)

**Bootstrap (run once before first ETL after deploying this feature):**
```bash
python3 etl/bootstrap_content_hashes.py
```
This populates `content_hash` on all existing nodes from current data without flagging anything. If skipped, the first ETL run silently populates hashes anyway (null-check in `merge_cours` prevents false flags) — but you lose the ability to compare against pre-deployment state.

**False-positive prevention:** `merge_cours` only flags when the stored hash is non-null AND differs from the new hash. New courses and first-run nodes are never flagged.

---

# Data Model

## Neo4j schema

**Nodes:**
- `Cours` — `sigle`, `universite`, `titre`, `credits`, `niveau`, `hors_perimetre`, `description`, `requirement_text`, `prereqs_known`, `tags[]`
- `PrerequisiteGroup` — `id`, `type` (`AND` | `OR`)

**Relationships:**
- `(Cours)-[:REQUIERT]->(Cours|PrerequisiteGroup)` — prerequisite
- `(PrerequisiteGroup)-[:INCLUDES]->(Cours|PrerequisiteGroup)` — group membership
- `(Cours)-[:REQUIERT_CONCOMITANT]->(Cours)` — corequisite (treated as blocking in eligibility)
- `(Cours)-[:EQUIVAUT_A {source, confidence, status}]-(Cours)` — equivalence (undirected)

**Edge direction in program-graph:** `source = course, target = prerequisite`. So `outgoing[course]` gives its prerequisite nodes. This is the direction in both Neo4j (`REQUIERT` goes from course to prereq) and in the returned edge list. The dagre layout places courses on the left and their prerequisites on the right.

## Program JSON schema

Each `programs/*.json` file follows this enriched schema (updated in this session):

```json
{
  "universite": "udem",
  "programme": "informatique",
  "version": "v1",
  "credits_total": 90,

  // UdeM-only: orientation selection
  "orientation_commune": "01_commun",
  "orientations": [
    { "id": "76_orientation_generale", "label": "Orientation générale" },
    { "id": "77_orientation_coop",     "label": "Orientation coopérative" },
    { "id": "78_cheminement_honor",    "label": "Cheminement Honor" }
  ],

  // Two-level (UdeM) or flat (all others) segment structure
  "segments": {
    "01_commun": {
      "label": "Tronc commun",          // group label (UdeM two-level)
      "bloc_01A_programmation": {
        "label": "Programmation",        // human-readable, added in this session
        "type": "obligatoire",           // obligatoire | option | libre
        "credits_min": 15,              // normalized in this session
        "credits_max": 15,
        "cours": ["IFT1005", "IFT1015", "IFT1025", "IFT2015", "IFT2035"]
      }
    }
  },

  // Flat list of all program courses for graph traversal
  "tous_les_cours": ["IFT1005", ...]
}
```

**`type: "libre"`** — free-choice segments with no specific course list (e.g. "Cours au choix hors IFT"). Rendered as informational cards only, no course cluster.

**`_flatten_segments()` in `api/routes/courses.py`** — normalizes UdeM's two-level structure into a flat list, filtered by `orientation_commune + chosen_orientation`.

## Availability computation

Availability is computed **client-side** in `RoadmapView.jsx` from the graph data returned by `POST /courses/program-graph`.

`program-graph` now returns `expanded_completed` — the student's completed sigles plus any courses that are active/needs_review equivalents of completed courses (1-hop expansion via Neo4j). `RoadmapView` uses `expanded_completed` (not raw `completedSigles`) when calling `computeAvailability`, so equivalence-aware availability works without a second API call.

A course is available if all entries in `outgoing[sigle]` are satisfied:
- For a `course` node: `completedSet.has(nodeId)`
- For a `group` node (AND): all children satisfied
- For a `group` node (OR): at least one child satisfied

Corequisites are treated as blocking (same conservative policy as the backend).

---

# API Reference

Run: `python3 -m uvicorn api.main:app --reload`  
Base path in frontend: `/api` (proxied to Railway in production via `vercel.json`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Neo4j connection check |
| GET | `/courses` | Paginated course list (filters: `universite`, `niveau`, `hors_perimetre`) |
| GET | `/courses/{sigle}` | Course details |
| GET | `/courses/{sigle}/prerequisite-chain` | Full prerequisite graph for one course |
| GET | `/courses/{sigle}/prerequisites` | Structured prerequisite tree (AND/OR) |
| POST | `/courses/eligible` | Courses available given a completed list |
| POST | `/courses/eligible-graph` | Eligible courses + edges for one university program |
| GET | `/courses/programs` | All programs by university (with orientations) |
| POST | `/courses/program-graph` | Full prerequisite graph for a program + enriched segments |
| GET | `/equivalences` | Search equivalences by sigle |
| GET | `/universities` | All universities with course counts |

### `POST /courses/program-graph` — updated in this session

**Request:**
```json
{
  "uni": "UdeM",
  "program": "informatique",
  "orientation": "76_orientation_generale",
  "completed_sigles": ["IFT1005", "IFT1015"]
}
```

**Response:** `{ nodes, edges, program_sigles, segments, expanded_completed }`

`expanded_completed` — the student's completed sigles unioned with their active/needs_review equivalents (1-hop). Used by `RoadmapView` for equivalence-aware availability computation client-side.

`segments` is a flat list of enriched segment objects:
```json
[{
  "id": "bloc_01A_programmation",
  "label": "Programmation",
  "type": "obligatoire",
  "credits_min": 15,
  "credits_max": 15,
  "cours": ["IFT1005", ...],
  "note": null,
  "group_label": "Tronc commun"
}]
```

### Sigles with spaces (McGill, Concordia)

Must be URL-encoded in paths: `COMP%20251`, `MATH%20203`.

---

# V1 Scope — What's Been Built

## App shell (App.jsx)
- Single page — no tabs. Visualiseur, Cours accessibles, and Équivalences tabs were removed.
- Default view: `ExplorationPage`
- "Admin" button in topbar toggles `AdminPanel` (replaces the main view while open)
- Completed courses and homeUniversite persisted in localStorage

## Exploration tab (RoadmapView — V1)
- University + program selector in sidebar
- **Orientation selector** for UdeM (3 tracks: générale, coopérative, honor)
- Completed courses entry (search + add)
- `POST /courses/program-graph` fetches the full program graph
- Roadmap renders: Completed bubble → Disponible maintenant → Et ensuite
- Courses grouped by segment labels with credit progress bars
- `type: "libre"` segments rendered as informational cards
- "Et ensuite →" reveals next-wave courses (client-side, same segment structure)
- Clicking a course opens the detail/equivalence panel
- Detail panel shows equivalences with OFFICIELLE/SIMILAIRE badges and confidence bars
- Substitution mechanic in detail panel (wired but not V1 roadmap feature)

## Admin panel (AdminPanel.jsx)
- Login screen with university-scoped Basic Auth
- **Notification bell** in topbar: shows count of `needs_review` equivalences with `flag_reason`. Clicking opens an Instagram-style dropdown listing each alert with the course, university, parsed change reason (e.g. "Les crédits sont passés de 3 à 4"), and date.
- Pending queue: shows inferred `pending` items + `needs_review` alerts from any source. Alert rows have "Confirmer valide" button instead of "Approuver".
- Full equivalence table with filters (source, status, sigle)
- Create equivalence form
- Revoke / restore actions

## Student-facing equivalence visibility rule
- `active` → visible to students
- `needs_review` → **visible to students** (`needs_review` is internal admin quality-control state, not a visibility blocker)
- `pending` → hidden from students
- `revoked` → hidden from students

All student-facing Cypher queries filter `r.status IN ['active', 'needs_review']`. This applies to: program-graph equiv nodes, prereq-chain equiv nodes, expanded_completed computation, eligible/eligible-graph Phase 1a expansion, and the `/equivalences` search endpoint.

---

# Decisions Made — Do Not Revisit

1. **No ET/OU nodes in the roadmap.** The segment-cluster approach replaces graph node notation. ET/OU logic is computed inside `computeAvailability` but never rendered.

2. **Segment labels come from the JSON, not derived from keys.** Keys like `bloc_01A_programmation` are machine IDs. Labels were authored manually in this session. Never try to derive display names from key patterns.

3. **Credit normalization: `credits_min` / `credits_max` everywhere.** For fixed blocks, both are equal. For the `type: "libre"` segments, both are set to the free-choice requirement. The `credits` field from the old schema is gone in program JSONs.

4. **UdeM requires an orientation selector.** The JSON has `orientation_commune` + `orientations[]`. The UI gates "Visualiser" until orientation is picked. The `_flatten_segments()` function handles the two-level hierarchy.

5. **Client-side availability computation with server-side equivalence expansion.** `computeAvailability()` in `RoadmapView.jsx` uses the graph edges returned by `program-graph`. It does NOT call the `/eligible` endpoint. Equivalence expansion is handled server-side: `program-graph` returns `expanded_completed` (completed sigles + 1-hop active/needs_review equivalents), and the client passes this to `computeAvailability` instead of the raw completed list.

6. **`ExplorationGraph.jsx` is dead code.** It was replaced by `RoadmapView.jsx`. Do not restore it. It can be deleted in a cleanup pass.

7. **`type: "libre"` segments never show course cards.** They render as info text cards with a note. Courses like "any non-IFT course" can't be listed.

8. **Corequisites are blocking.** Same policy as the backend `/eligible` query. This is conservative and intentional for a planning tool.

9. **`vercel.json` rewrites for production API proxy.** Vite's dev proxy (`/api → localhost:8001`) only works in dev. The `web/vercel.json` rewrites `/api/*` to the Railway URL for production. Do not remove or change this without re-validating production.

10. **The roadmap is not a graph.** `RoadmapView.jsx` uses pure CSS flexbox, not ReactFlow. The Visualiseur tab keeps ReactFlow. These are two different components for two different purposes.

---

# Known Issues

## Bug 1 — IFT2125 (and similar concomitant-OR courses) permanently blocked

**Root cause:** ETL data modeling bug. IFT2125's requirement text is:
```
concomitant_courses: IFT2125 et IFT2015 et (MAT1978 ou MAT1720)
```
The ETL created:
- A `REQUIERT` (prerequisite) edge to an AND group — **wrong**, should not exist (it's all concomitant)
- Flat `REQUIERT_CONCOMITANT` edges to both MAT1978 **and** MAT1720 individually — **OR semantics lost**

Effect: `computeAvailability` sees MAT1720 as a required target. MAT1720 is `hors_perimetre: true` and is never in any student's completed list → IFT2125 is permanently blocked in the roadmap.

**Correct behavior:** IFT2125 should appear in "Et ensuite" when IFT2015 is available and MAT1978 (the OR branch that IS completed) is in the completed set.

**Fix needed:** ETL rewrite — preserve OR group semantics for `REQUIERT_CONCOMITANT` edges, and do not create a `REQUIERT` edge when the requirement is entirely concomitant.

**Scope:** ETL-level. Does not require roadmap or API changes.

## Bug 2 — FIXED

`program-graph` now returns `expanded_completed` and `RoadmapView` uses it for availability computation. Cross-university equivalences are properly accounted for.

## Bug 3 — Credits default to 3 for null values (minor display)

In `RoadmapView.jsx` `SegmentCluster`:
```javascript
// TODO V2: courses with null credits in Neo4j default to 3cr — may cause inaccurate progress bars
return sum + (nodeById[s]?.data?.credits ?? 3)
```
Most UdeM IFT courses are 3cr so this is usually correct. MAT1978 is 4cr (verified). The progress bar for "Mathématiques" shows 9/12 instead of the correct 11/12 (MAT1978=4cr + MAT1400=4cr + MAT1600=3cr = 11cr... but `credits_max` is 12 in the JSON which also needs verification against the actual program).

**Fix:** Verify credit values in Neo4j for all program courses; update `credits_min/credits_max` in program JSONs where needed.

---

# Deferred Ideas (V2+)

These were discussed and explicitly deferred. Do not implement in V1.

- **Animations** — horizontal canvas pan when "Et ensuite" is clicked, staggered course card appearance, edge draw-in animations
- **Advanced substitution UI** — the mechanic is wired (`substitutions` Map in `ExplorationPage`) but not surfaced in the roadmap. V2 would let students click a course card in the roadmap → detail panel → "Substituer" → node updates with dashed border and "via [Uni]" badge
- **Equivalence-aware availability** — expand equivalences in client-side availability computation (fix for Bug 2)
- **Multiple "Et ensuite" waves** — currently only one additional wave. Could reveal a third wave, fourth, etc.
- **Horizontal swimlane layout** — full roadmap from Year 1 to graduation laid out in columns, scrollable horizontally, with opacity gradient (full opacity = now, fading = future)
- **Requirement progress summary** — "You've completed 3/6 credits in the Algorithm Option" summary banner above the roadmap
- **Poly/ETS concentration mapping** — `concentrations_orientations` segments have empty `cours: []`. Need to add the actual concentration course lists to the program JSONs
- **McGill/Concordia credit verification** — credit estimates for optional blocks were derived from course counts × 3cr. Should be verified against official program guides
- **ETL: concomitant OR groups** — fix the ETL to model `REQUIERT_CONCOMITANT` with OR group semantics (fixes Bug 1)
- **Libre segment examples** — show 2-3 representative examples for "Cours au choix" instead of just the note text
- **Mobile layout** — the roadmap is desktop-only currently (horizontal scroll required)

---

# Development Principles

## Commit messages
No `Co-Authored-By` lines. No author attribution of any kind. Just the commit message.

## Code style
- Inline styles throughout the frontend (consistent with existing code)
- No new CSS classes unless the component is complex enough to warrant it
- No comments unless the WHY is non-obvious. No docstrings.
- No error handling for scenarios that can't happen. Trust framework guarantees.
- No backwards-compatibility shims. If something is unused, delete it.

## Data flow
- Program structure (segments, labels, credit requirements) → program JSONs
- Course knowledge (prerequisites, equivalences, metadata) → Neo4j via API
- Availability computation → client-side from returned graph data (no second API call)

## Segment display rules
- `type: "obligatoire"` → green progress bar, renders course cards
- `type: "option"` → orange progress bar, renders course cards
- `type: "libre"` → no progress bar, renders info text card only
- A segment only renders if it has ≥1 available course that exists in `nodeById` (fix for empty-cluster bug)

## Availability computation
Edge direction: `source = course, target = prerequisite`. `outgoing[course]` gives prerequisites. Group nodes (AND/OR) have their children in `outgoing[groupId]`. Both prerequisite and corequisite edges are treated as blocking.

## Adding a new program
1. Create `programs/{uni}_{program}.json` following the enriched schema
2. Add `label` to every segment, `credits_min`/`credits_max` to every segment, `type: "libre"` for free-choice blocks
3. For UdeM-style programs with orientation tracks, add `orientation_commune` and `orientations[]`
4. `_load_programs()` picks it up automatically at server restart
5. Run the ETL to load the program's courses into Neo4j

## Adding a new equivalence source
See `etl/load_official_equivs.py` and `etl/embed_equivalences.py`. Equivalences are filtered in `embed_equivalences.py` by:
- Skip courses with titles containing: project, projet, capstone, stage, internship, intégrateur, honor, honours, independent, topics, sujets
- Skip pairs where the absolute difference in course level (first digit of sigle) > 1

---

# External APIs

| Source | Base URL |
|--------|----------|
| UdeM (Planifium) | `https://planifium-api.onrender.com/api/v1` |

### UdeM endpoints used

- `GET /courses?response_level=full` — all courses (12 343 total), filtered client-side
  - `subject` and `limit` parameters are ignored by the API — fetch everything in one call
- `GET /courses/{course_id}` — individual course by ID

---

# Current Next Steps

In priority order:

1. **Fix the IFT2125-class ETL bug** — rewrite concomitant OR group handling so OR semantics are preserved as `REQUIERT_CONCOMITANT` edges pointing to a group node (same pattern as REQUIERT uses PrerequisiteGroup)
2. **Verify credit values** — check `credits` in Neo4j for UdeM informatique courses; update `credits_max` in segment JSON where needed (MAT1978=4cr, MAT1400=4cr, MAT1600=3cr → math bloc likely 11cr not 12cr)
3. **Delete `ExplorationGraph.jsx`** — dead code
4. **Admin equivalence review** — 329 pending inferred equivalences need human review by university staff. More approvals = better student experience.
5. **V2 substitution UI in roadmap** — wire existing substitution mechanic into course cards in `RoadmapView.jsx`

## Manual test scenario

**UdeM → Informatique → Orientation générale**, with these completed courses:
```
IFT1005, IFT1015, IFT1025    (Programmation, 9cr)
IFT1065, IFT1575              (Théorie, 6cr)
IFT1215, IFT1227              (Systèmes, 6cr)
MAT1400, MAT1600, MAT1978     (Mathématiques, 10cr actual / shows 9cr due to Bug 3)
```

**Expected "Disponible maintenant":**
- Programmation: IFT2015, IFT2035
- Théorie et algorithmique: IFT2105 (IFT2125 is permanently blocked — known Bug 1)
- Systèmes informatiques: IFT2255 (IFT2245 needs IFT1065+IFT2105 → Et ensuite)
- Interfaces et bases de données: IFT2905 (requires IFT2905 prereqs — verify)
- Cours complémentaires: IFT2425, IFT2505, and several IFT3xxx

**Expected "Et ensuite":**
- Systèmes: IFT2245
- Interfaces: IFT2935 (needs IFT2905 available in wave 1)
- Génie logiciel: IFT3911, IFT3913
- Additional complémentaires

---

# How to Continue This Project

When starting a new Claude Code session:

1. Read this file first — it captures all major decisions and their rationale
2. Read `web/src/RoadmapView.jsx` for the current roadmap rendering logic
3. Read `web/src/AdminPanel.jsx` for the admin UI including notification bell and pending queue
4. Read `api/routes/courses.py` starting at `_load_programs()` and `get_program_graph()` for the data pipeline
5. Read `api/routes/admin.py` for the full admin API including auth, equivalence lifecycle, and change-detection flagging
6. Read `programs/udem_informatique.json` as the canonical example of the enriched program JSON schema
7. Read `etl/prereq_parser.py` — `merge_cours()` includes content-hash change detection and equivalence flagging

**Do not** re-read `web/src/ExplorationGraph.jsx` — it's dead code.

**Do not** suggest going back to a graph-based view for the Exploration tab — the roadmap approach is decided.

**Do not** propose deriving segment labels from JSON key names — labels were manually authored.

**Do not** add a Visualiseur tab back — it was intentionally removed. The Exploration roadmap is the sole student-facing view.
