# Tool descriptors déclaratifs (`.md`)

Un fichier `.md` déposé dans `DATA_DIR/tools_md/` devient un tool
disponible pour le LLM, **sans écrire de Python**.

Le framework parse le frontmatter YAML, en génère un JSON schema pour le
function calling, et une fonction d'exécution qui suit la `source`
déclarée.

## Format

```markdown
---
name: get_portfolio_summary
description: "Calcule la valeur du portefeuille et les P&L par position"
parameters:
  - name: assets
    type: array
    items: string
    description: "Filtre optionnel sur des assets"
    required: false
source:
  type: csv          # csv | api | scraper | computed
  file: positions.csv
logic: |
  1. Lire positions.csv
  2. Grouper par asset, calculer la quantité nette
  3. Retourner asset, qty, PRU
output: json
---

## Contexte

Documentation libre destinée au LLM : règles de calcul, conventions,
hypothèses. Ce corps est transmis au LLM avec les données.
```

## Types de `source`

| `type`     | Comportement |
|------------|--------------|
| `csv`      | Charge `source.file` depuis `data/`, transmet les lignes au LLM |
| `api`      | `GET source.url` avec les paramètres du tool |
| `scraper`  | Exécute le scraper `source.name` |
| `computed` | Le LLM interprète `logic` sur les paramètres fournis |

## Règles

- **Aucun code exécutable** dans un `.md` : la `logic` est interprétée,
  jamais évaluée (`eval`/`exec` interdits).
- Le nom du tool doit être un identifiant simple (pas de `/`, `..`).
- `/reload_tools` recharge les descripteurs à chaud.
