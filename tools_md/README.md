# Tool descriptors déclaratifs (`.md`)

Ce dossier contient les **tools déclaratifs** du bot, versionnés dans le
repo. Pour un tool plus complexe qui demande du code, ajouter un module
Python dans `tools/` (core tool).

Les tools sont gérés par l'**admin** : pas de création depuis le chat ni
via slash command. Pour ajouter un tool, committer un fichier ici puis
redémarrer ou appeler `/reload_tools`.

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
  type: csv          # csv | api | scraper | computed | file
  file: positions.csv
logic: |
  1. Lire positions.csv
  2. Grouper par asset, calculer la quantité nette
  3. Retourner asset, qty, PRU
secrets:
  - POLYGON_API_KEY  # optionnel, lu depuis le .env de l'instance
---

## Contexte

Documentation libre destinée au LLM : règles de calcul, conventions,
hypothèses. Ce corps est transmis au LLM avec les données.
```

## Types de `source`

| `type`     | Comportement |
|------------|--------------|
| `csv`      | Charge `source.file` depuis `DATA_DIR/data/`, transmet les lignes au LLM |
| `file`     | Lit un fichier texte/MD depuis `DATA_DIR/data/` |
| `api`      | `GET source.url` avec `headers` et `params` ; `${VAR}` substitué depuis l'environnement |
| `scraper`  | Exécute le scraper `source.name` (déclaré dans `DATA_DIR/scrapers/`) |
| `computed` | Le LLM interprète `logic` sur les paramètres fournis |

## Secrets

Si un tool a besoin de clés API, les référencer en `${NOM_VAR}` dans
`source.url`, `source.headers` ou `source.params`, et les lister dans
`secrets:`. L'admin renseigne la valeur dans `$DATA_DIR/.env`. À
l'exécution, une variable manquante fait retourner au LLM un message
`{"error": "missing_secrets", "secrets": [...]}` sans appeler l'API.

## Règles

- **Aucun code exécutable** dans un `.md` : la `logic` est interprétée
  par le LLM, jamais évaluée (`eval`/`exec` interdits).
- Les clés `python`, `exec`, `eval`, `code`, `import` dans le
  frontmatter sont rejetées au chargement.
- Le nom du tool doit être en `snake_case` (validé anti-path-traversal).
- `source.type` doit être l'un des cinq types listés.
