# Cross-Codebase CSV Import Format Mapping

## Pattern

Quand on importe un CSV exporté d'une codebase A (ex: Android/Kotlin) dans une codebase B (ex: Web/Python), les colonnes et valeurs d'enum diffèrent. Un import qui échoue silencieusement avec "0 imported, 1 error" sans détail est un piège classique.

## Exemple concret : AlphaRadar Android → Web

### Colonnes Android (CSV mouliné)

```
processedAt, symbol, isin, name, exchange, market, currency, assetType,
positionStatus, quantity, averagePrice, averagePriceCurrency, currentPrice,
displayPrice, quoteSymbol, quoteCurrency, sniper1, sniper2, capitulation,
sniperCurrency, displayCurrency, category, riskLevel, enabled, notes, sourceUrl
```

### Colonnes Web (attendues par l'importeur)

```
ticker, name, type, purchase_price, current_price, currency
```

### Mapping implémenté

| Colonne Android | Colonne Web | Notes |
|---|---|---|
| `symbol` | `ticker` | Renommage simple |
| `assetType` | `type` | **+ mapping de valeurs** (EQUITY→watchlist) |
| `averagePrice` | `purchase_price` | Renommage simple |
| `currentPrice` | `current_price` | Renommage simple |
| `name` | `name` | Identique |
| `currency` | `currency` | Identique |
| `processedAt`, `isin`, `exchange`, ... | ignorées | Colonnes sans équivalent web |

### Mapping de valeurs d'enum

| Android `assetType` | Web `type` |
|---|---|
| `EQUITY` | `watchlist` |
| `ETF` | `watchlist` |
| `CRYPTO` | `watchlist` |
| `BOND` | `watchlist` |
| `POSITION` | `position` |
| `WATCHLIST` | `watchlist` |

**Raison** : Android a `assetClass: EQUITY/ETF/CRYPTO` + `positionStatus: POSITION/WATCHLIST` séparés. Web fusionne en un seul `type: position/watchlist`. Par défaut conservateur, tout ce qui n'est pas explicitement `POSITION` → `watchlist`.

## Checklist d'audit pour tout CSV cross-codebase

- [ ] Lister TOUTES les colonnes de la source (ex: exporter une ligne et l'inspecter)
- [ ] Lister TOUTES les colonnes acceptées par la cible (`KNOWN_COLUMNS` dans le code d'import)
- [ ] Identifier les colonnes :
  - Renommées (même sémantique, nom différent)
  - Avec mapping de valeurs (même colonne, valeurs d'enum différentes)
  - Manquantes (dans la source mais pas dans la cible — à ignorer)
  - Requises manquantes (dans la cible mais pas dans la source — à dériver ou default)
- [ ] Implémenter l'auto-détection de format (checker la présence de `symbol`+`assetType` vs `ticker`+`type`)
- [ ] Logger l'erreur **détaillée** en cas d'échec (pas juste "errors=1")
- [ ] Tester avec un CSV source réel (pas un CSV mock)

## Code pattern (Python/FastAPI)

```python
# Auto-détection du format Android
def _is_android_format(headers: set[str]) -> bool:
    return "symbol" in headers and "ticker" not in headers and "assetType" in headers

# Normalisation des headers
ANDROID_COLUMN_MAP = {
    "symbol": "ticker",
    "assetType": "type",
    "averagePrice": "purchase_price",
    "currentPrice": "current_price",
}

# Normalisation des valeurs d'enum
ANDROID_TYPE_VALUES = {
    "EQUITY": "watchlist",
    "ETF": "watchlist",
    "POSITION": "position",
    "WATCHLIST": "watchlist",
}

# Application dans la boucle d'import
if clean.get("type"):
    clean["type"] = ANDROID_TYPE_VALUES.get(clean["type"], "watchlist")
```

## Pièges

- ❌ Dire "c'est le même format" sans vérifier les noms de colonnes
- ❌ Logger "errors=1" sans le texte de l'erreur — impossible à diagnostiquer
- ❌ Supposer que le hot-reload (uvicorn --reload) a pris sur NTFS
- ❌ Oublier que les valeurs d'enum diffèrent entre codebases (EQUITY ≠ position ≠ watchlist)
