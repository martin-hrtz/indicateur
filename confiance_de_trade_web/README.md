# Confiance de Trade Web

Application temps réel affichant le pourcentage de Confiance de Trade (CT%) pour le marché crypto.

## Aperçu

- **Backend** : FastAPI (Python 3.10+), WebSocket 1 Hz, moteur de score configurable par YAML.
- **Frontend** : HTML/CSS/JS vanilla, interface minimaliste (CT% + événements actifs).
- **IA** : squelette d'intégration LLM pour classifier l'impact de tweets/news.

## Pré-requis

- Python 3.10+
- Node non requis (frontend statique)

## Installation backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copiez `.env.example` vers `.env` et renseignez les clés si disponibles :

```
cp .env.example .env
# éditer TIMEZONE, OPENAI_API_KEY, ...
```

## Lancer le serveur

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Endpoints clés :

- `GET /health` : statut simple.
- `GET /api/score` : score courant + contributions.
- `POST /api/ingest` : injecter un `RiskEvent` (tests manuels).
- `WS /ws` : diffusion 1 Hz `{score, active}`.

Le frontend (`frontend/`) peut être servi par n'importe quel serveur statique ou via `python -m http.server`.

## Configuration & connaissance

Les réglages sont centralisés dans `backend/knowledge/` :

- `score.yaml` : baseline, poids par catégorie, demi-vies, déduplication.
- `sessions.yaml` : horaires d'ouvertures/fermetures marchés.
- `scenarios.yaml` : scénarios (CPI, FOMC, hack...).
- `twitter_sources.yaml` : comptes suivis & crédibilité.

## Observateurs

Chaque watcher tourne dans une tâche asynchrone indépendante avec backoff :

- `sessions.py` : génère automatiquement les événements de session (pré/post fenêtres).
- `exchange_status.py`, `macro.py`, `regulatory.py`, `onchain.py`, `microstructure.py`, `twitter_stream.py` : squelettes prêts à relier aux APIs.

## Moteur de score

- Baseline 95% quand aucun risque actif.
- Chaque `RiskEvent` contribue via une courbe logistique (gravité), poids catégorie, multiplicateur actif, pondération temporelle (planifiée vs breaking).
- EMA demi-vie 30 s + clamp ±5/±3 pts par seconde.
- Déduplication (source+titre) 5 minutes.

## Frontend

- Affiche CT% en grand.
- Liste max 5 événements actifs, chacun avec contribution et explication IA si disponible.
- Silence by design : aucun placeholder lorsqu'il n'y a pas d'événement.

## Tests manuels

Voir [`run_local.md`](run_local.md) pour des recettes (ingestion CPI, hack, incident exchange, etc.).
