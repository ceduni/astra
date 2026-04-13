# Astra

Astra est une plateforme visant à modéliser, explorer et expliquer les relations d'ordre, de dépendance et d'équivalence entre les cours et les programmes offerts par les établissements d'enseignement supérieur. Elle vise à rendre explicites les structures de connaissance propres à chaque institution afin d'éclairer les parcours d'études et de soutenir une mobilité académique plus fluide et informée.

## Architecture

```
api/          FastAPI backend — REST endpoints + Neo4j queries
etl/          ETL pipelines — one subfolder per university
  udem/
  uqam/
  mcgill/
  concordia/
  poly/
web/          React frontend (Vite)
```

See [SCHEMA.md](SCHEMA.md) for the full Neo4j graph schema.

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/ceduni/astra.git
cd astra
```

### 2. Configure environment variables

Copy the example env file and fill in your Neo4j credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```
NEO4J_URI=bolt://localhost:7687   # or your Aura URI (neo4j+s://...)
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

### 3. Set up Neo4j

**Option A — Local (Neo4j Desktop)**
1. Download [Neo4j Desktop](https://neo4j.com/download/)
2. Create a new project and database
3. Start the database and set a password
4. Update `.env` with `bolt://localhost:7687` and your password

**Option B — Neo4j Aura (cloud, free tier)**
1. Go to [console.neo4j.io](https://console.neo4j.io) and create a free instance
2. Copy the connection URI (starts with `neo4j+s://`)
3. Update `.env` with the Aura URI, username, and password

### 4. Install API dependencies

```bash
pip install -r requirements.txt
```

### 5. Load the data

Each university has its own ETL pipeline. Run them in order — `transform.py` produces a `canonical_courses.json`, then `load_neo4j.py` loads it into the graph.

```bash
# UdeM
python etl/udem/transform.py && python etl/udem/load_neo4j.py

# UQAM
python etl/uqam/transform.py && python etl/uqam/load_neo4j.py

# McGill
python etl/mcgill/transform.py && python etl/mcgill/load_neo4j.py

# Concordia
python etl/concordia/transform.py && python etl/concordia/load_neo4j.py

# Poly
python etl/poly/transform.py && python etl/poly/load_neo4j.py
```

> The raw data files (`raw_courses.json`) are already committed. You do not need to re-run the fetch scripts unless you want to refresh the data from the university APIs.

### 6. Run the API

```bash
python -m uvicorn api.main:app --reload --port 8001
```

API is available at `http://localhost:8001`. Interactive docs at `http://localhost:8001/docs`.

### 7. Run the frontend

```bash
cd web
npm install
npm run dev
```

Frontend is available at `http://localhost:5173`.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Check Neo4j connectivity |
| `GET` | `/universities` | List universities with course counts |
| `GET` | `/courses` | List courses (filters: `universite`, `niveau`, `hors_perimetre`) |
| `GET` | `/courses/{sigle}` | Course details |
| `GET` | `/courses/{sigle}/prerequisite-chain` | Full prerequisite graph for visualization |
| `GET` | `/courses/{sigle}/prerequisites` | Structured prerequisite tree (AND/OR) |
| `POST` | `/courses/eligible` | Courses accessible given a list of completed course sigles |
| `GET` | `/search?q=` | Full-text search across sigle, title, and description |

> Sigles with spaces (McGill, Concordia) must be URL-encoded: `COMP%20251`
