# Recettes de tests manuels

Assurez-vous que le serveur FastAPI tourne (voir README) puis utilisez ces scénarios pour valider le moteur.

## Baseline
- Laissez tourner 30 min sans ingestion : le score converge vers la baseline (~95) et aucun événement n'est affiché.

## CPI T−20 min
```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source": "MacroCalendar",
    "category": "MACRO",
    "title": "US CPI (hawkish)",
    "ts": '"$(date +%s)"',
    "severity": 70,
    "meta": {
      "scenario": "CPI",
      "scheduled_ts": '"$(($(date +%s)+1200))"',
      "currencies": ["BTC","ETH"],
      "time_boost": 1.8,
      "explanation": "CPI attendu au-dessus du consensus"
    }
  }'
```
- Vérifier que le score baisse progressivement en approchant l'heure programmée.

## CPI résultat hawkish
Ajoutez un ajustement IA négatif une fois la publication sortie :
```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source": "IA",
    "category": "MACRO",
    "title": "CPI publié > consensus",
    "ts": '"$(date +%s)"',
    "severity": 65,
    "meta": {
      "scenario": "CPI",
      "score_adjustment_points": -6,
      "explanation": "CPI ressort au-dessus, pression vendeuse",
      "urgency": 80
    }
  }'
```
- Le score doit chuter davantage, sans duplication.

## Incident exchange majeur
```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source": "BinanceStatus",
    "category": "EXCHANGE_STATUS",
    "title": "Binance arrête les retraits BTC",
    "ts": '"$(date +%s)"',
    "severity": 85,
    "meta": {
      "currencies": ["BTC"],
      "urgency": 90,
      "explanation": "Binance suspend les retraits BTC"
    }
  }'
```
- Chute immédiate du CT%.

## Hack 15M
```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source": "OnChainAlert",
    "category": "HACK",
    "title": "Hack DeFi 15M",
    "ts": '"$(date +%s)"',
    "severity": 80,
    "meta": {
      "currencies": ["ETH","SOL"],
      "urgency": 85,
      "explanation": "Protocol DeFi drainé 15M"
    }
  }'
```
- Impact négatif net dans les minutes qui suivent.

## Rumeur lointaine
```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "source": "Twitter",
    "category": "RUMOR",
    "title": "Rumeur ETF semaine prochaine",
    "ts": '"$(date +%s)"',
    "severity": 30,
    "meta": {
      "score_adjustment_points": 0,
      "immediacy_minutes": 180,
      "explanation": "Rumeur lointaine, pas d'effet immédiat"
    }
  }'
```
- Pas de mouvement significatif (pondération temps nulle > fenêtre).

## Sessions US
- Laissez tourner autour de 15h30/22h CET : vérifiez l'apparition automatique des événements `SessionWatcher`.
