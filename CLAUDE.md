# Cours Interuniversitaire

Plateforme de découverte de cours interuniversitaire (UdeM, et autres à venir).

## Architecture

```
etl/          Scripts d'extraction et transformation des données de cours
  udem/       Pipeline ETL pour l'Université de Montréal
    fetch_courses.py   Fetch les cours IFT + prérequis MAT depuis l'API UdeM
    raw_courses.json   Données brutes (généré)

api/          Backend API (à venir)
web/          Frontend (à venir)
data/         Données transformées/normalisées (à venir)
```

## APIs externes

| Source | Base URL |
|--------|----------|
| UdeM (Planifium) | `https://planifium-api.onrender.com/api/v1` |

### Endpoints UdeM utilisés

- `GET /courses?response_level=full` — tous les cours (12 343 au total), filtrés côté client
  - Note: les paramètres `subject` et `limit` sont ignorés par l'API — on récupère tout en un appel
- `GET /courses/{course_id}` — cours individuel par ID

### Structure d'un cours (response_level=full)

```json
{
  "id": "IFT1015",
  "name": "...",
  "credits": 3.0,
  "description": "...",
  "available_terms": { "autumn": true, "winter": true, "summer": false },
  "available_periods": { "daytime": true, "evening": false },
  "schedules": [],
  "requirement_text": "Préalable: IFT1005",
  "prerequisite_courses": ["IFT1005"],
  "concomitant_courses": [],
  "equivalent_courses": []
}
```

## Commandes utiles

```bash
# Fetch les cours UdeM
python etl/udem/fetch_courses.py
```

## Conventions

- Les données brutes sont sauvegardées telles quelles depuis l'API, sans transformation.
- Les prérequis MAT sont inclus dans `raw_courses.json` pour permettre la visualisation du graphe de dépendances.
- Toujours utiliser `response_level=full` pour avoir les champs de prérequis.
