# Neo4j Graph Schema

## Node Types

### `Cours`
Represents a university course. There are **525** course nodes in the graph.

| Property | Type | Description |
|---|---|---|
| `sigle` | string | Course code, unique identifier (e.g. `IFT1015`, `COMP 251`) |
| `universite` | string | Institution: `UdeM`, `UQAM`, `McGill`, `Concordia`, `Poly` |
| `titre` | string | Course title |
| `credits` | integer \| null | Credit value (null if not available) |
| `niveau` | integer | Course level (e.g. `1`, `2`, `3`, `8`) |
| `hors_perimetre` | boolean | True if course is outside the interuniversity program scope |
| `description` | string | Course description (may be empty) |
| `requirement_text` | string | Raw prerequisite text from the official catalogue |

---

### `PrerequisiteGroup`
Represents a logical AND/OR grouping of prerequisites. There are **175** group nodes (89 AND, 86 OR).

| Property | Type | Description |
|---|---|---|
| `id` | string | Auto-generated unique identifier (e.g. `IFT2125_g0`) |
| `type` | string | `AND` (all must be satisfied) or `OR` (any one suffices) |

---

## Relationship Types

### `REQUIERT`
A course requires a prerequisite — either a single course or a group.
- **219** total relationships
- `(Cours)-[:REQUIERT]->(Cours)` — 102 direct course-to-course prerequisites
- `(Cours)-[:REQUIERT]->(PrerequisiteGroup)` — 117 prerequisites with AND/OR logic

### `INCLUDES`
A prerequisite group includes its members.
- **386** total relationships
- `(PrerequisiteGroup)-[:INCLUDES]->(Cours)` — 328 group-to-course memberships
- `(PrerequisiteGroup)-[:INCLUDES]->(PrerequisiteGroup)` — 58 nested group-to-group (supports compound logic)

---

## Diagram

```
Simple case — direct prerequisite:

  (Cours: IFT1015) <──[:REQUIERT]── (Cours: IFT1025)

  "IFT1025 requires IFT1015"


AND group — all must be satisfied:

  (Cours: A) ──┐
               ├──[:INCLUDES]── (PrerequisiteGroup {type: AND}) <──[:REQUIERT]── (Cours: X)
  (Cours: B) ──┘

  "X requires both A and B"


OR group — any one suffices:

  (Cours: A) ──┐
               ├──[:INCLUDES]── (PrerequisiteGroup {type: OR}) <──[:REQUIERT]── (Cours: X)
  (Cours: B) ──┘

  "X requires either A or B"


Nested group — compound logic (AND of ORs, etc.):

  (Cours: A) ──┐
               ├──[:INCLUDES]── (Group {OR}) ──┐
  (Cours: B) ──┘                               ├──[:INCLUDES]── (Group {AND}) <──[:REQUIERT]── (Cours: X)
  (Cours: C) ──────────────────────────────────┘

  "X requires (A or B) and C"
```

---

## Example Cypher Queries

```cypher
-- All prerequisites for a course
MATCH (c:Cours {sigle: 'IFT2125'})-[:REQUIERT]->(t)
RETURN c, t

-- Full prerequisite chain (variable depth)
MATCH path = (c:Cours {sigle: 'IFT3395'})-[:REQUIERT*1..10]->()
RETURN path

-- All courses accessible given a set of completed courses
MATCH (c:Cours {hors_perimetre: false})
WHERE NOT (c)-[:REQUIERT]->()
RETURN c.sigle, c.titre

-- Courses offered by a specific university
MATCH (c:Cours {universite: 'UdeM'})
RETURN c.sigle, c.titre, c.niveau
ORDER BY c.niveau, c.sigle
```
