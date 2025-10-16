# Confiance de Trade Web

## Démarrage express (macOS)
1. Double-cliquez `FIX-PERMISSIONS.command` si macOS signale un blocage après le dézip.
2. Double-cliquez `START.command` : le script crée le venv Python, installe les dépendances, génère `.env` au besoin puis lance le backend FastAPI (8000 → 8001 si occupé) et le serveur statique (8080 → 8081). Le navigateur s'ouvre automatiquement.
3. Double-cliquez `STOP.command` pour arrêter proprement les processus et libérer les ports.

## Infos rapides
- Backend FastAPI : `GET /health`, `GET /version`, `GET /api/score`, `POST /api/ingest`, `WS /ws`, `GET /sse`.
- Frontend vanilla (HTML/CSS/JS) : interface silencieuse affichant CT% et les événements actifs.
- Scripts et journaux : `.runtime/pids.json` et `.runtime/logs/*.log` permettent le diagnostic. Les watchers sans clé API se désactivent automatiquement (aucun bruit côté UI).
