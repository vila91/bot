# AutoBot — Framework de bot Discord autonome personnalisable

## Vision

Un framework Python pour créer des bots Discord autonomes alimentés par un LLM (DeepSeek par défaut), avec :
- **Chat interactif** dans un channel Discord dédié
- **Routines planifiées** décrites en Markdown, exécutées par cron
- **Tools modulaires** en code Python (noyau) ou déclarés en `.md` (personnalisation)
- **Data layer** séparé du code : CSV (données structurées) + MD (routines, descripteurs de tools)
- **Pilotage 100 % en langage naturel** : pas de slash commands — on parle au bot, il modifie sa config via ses propres tools (`set_rules`, `set_llm`, `scheduler`, `introspect`, …)

Le framework est **générique** : l'utilisateur le décline pour son domaine (trading, veille tech, monitoring infra, CRM…) en déposant ses fichiers de données et de routines, sans toucher au code.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                          Discord (WebSocket)                       │
│              ┌──────────────┐   ┌──────────────────────────┐       │
│              │ Chat interactif│   │ Routines (cron → runner)│       │
│              └──────┬───────┘   └────────────┬─────────────┘       │
│                     │                         │                    │
│                     ▼                         ▼                    │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                    LLM Engine (multi-tour)                   │  │
│   │         DeepSeek / OpenAI-compatible endpoint                │  │
│   │         function calling → tool dispatch → réponse           │  │
│   └──────────────────────┬──────────────────────────────────────┘  │
│                          │                                         │
│   ┌──────────────────────▼──────────────────────────────────────┐  │
│   │                     Tool Registry                            │  │
│   │  ┌────────────┐  ┌───────────┐  ┌────────────────────────┐  │  │
│   │  │ Core tools  │  │ MD tools  │  │ Scraper tools (dynamic)│  │  │
│   │  │ (Python)    │  │ (déclaratifs)│ │ (site configuré)      │  │  │
│   │  └────────────┘  └───────────┘  └────────────────────────┘  │  │
│   └─────────────────────────────────────────────────────────────┘  │
│                          │                                         │
│   ┌──────────────────────▼──────────────────────────────────────┐  │
│   │                    Data Layer                                │  │
│   │       DATA_DIR (~/.autobot/ par défaut)                      │  │
│   │  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────────┐  │  │
│   │  │ *.csv   │  │ routines/│  │ memory/ │  │ tools_md/    │  │  │
│   │  │ (données│  │ *.md     │  │ current │  │ descripteurs │  │  │
│   │  │ fixes)  │  │ (cron)   │  │ + archives│ │ de tools    │  │  │
│   │  └─────────┘  └──────────┘  └─────────┘  └──────────────┘  │  │
│   └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## Stack technique

| Rôle | Choix | Justification |
|------|-------|---------------|
| Langage | **Python 3.12+** | Écosystème LLM/Discord le plus mature, `asyncio` natif, prototypage rapide |
| Bot Discord | `discord.py` (asyncio, WebSocket persistant) | Standard de facto, intégration native du flux message → LLM |
| LLM | DeepSeek `deepseek-chat` (OpenAI-compatible) | Function calling multi-tour, coût faible. Swappable via config. |
| Recherche web | Tavily (REST, clé API) | Recherche + résumé IA en un appel |
| Scraping ciblé | `httpx` + `beautifulsoup4` + descripteur `.md` | Un `.md` décrit la structure du site cible |
| Mémoire | JSON glissant (fenêtre configurable) + archives MD | Pas de DB externe, fichiers plats inspectables |
| Scheduler | crontab système via `runner.py` | Fiable, visible, debuggable (`/tmp/autobot_*.log`) |
| Logs | `structlog` (JSON → stdout → journald) | Structured logging, rotation par systemd |
| Config | `.env` chargé par `config.py` | Un seul endroit pour tous les secrets |

### Pourquoi Python et pas Go/Rust ?

- L'écosystème LLM (function calling, parsing JSON schema) est **natif** en Python
- `discord.py` est plus mature et mieux documenté que les alternatives Go/Rust
- Le bottleneck est l'I/O réseau (appels LLM, Discord, APIs), pas le CPU — `asyncio` suffit
- Go/Rust apporteraient de la robustesse au typage mais au prix d'un développement 3-5x plus lent pour un bot qui passe 99% de son temps à attendre des réponses réseau
- Le framework est destiné à être **personnalisé par des non-développeurs** (via MD/CSV), pas recompilé

---

## Structure des fichiers

Le projet sépare strictement **code (versionné git)** et **données runtime (persistantes hors repo)**. Cela permet de mettre à jour le code (`git pull`) sans toucher aux données, routines ou mémoire.

### Code (repo git)

```
autobot/
├── bot.py                        # Point d'entrée : bot Discord + boucle LLM
├── runner.py                     # Exécute une routine (.md) à la demande ou via cron
├── config.py                     # Variables d'env + DATA_DIR + LLM_PROVIDER
│
├── engine/                       # Noyau LLM
│   ├── __init__.py
│   ├── llm.py                    # Client LLM abstrait (DeepSeek/OpenAI-compat)
│   └── loop.py                   # Boucle function calling multi-tour
│
├── tools/                        # Tools exposés au LLM (function calling)
│   ├── __init__.py               # Registre : TOOLS_DEFINITIONS + execute_tool()
│   ├── _base.py                  # Classe de base ToolDefinition + décorateur @tool
│   │
│   │  # --- Core tools (code Python, toujours présents) ---
│   ├── data_reader.py            # Lecture des CSV et fichiers de DATA_DIR
│   ├── scheduler.py              # CRUD routines + crontab
│   ├── memory.py                 # Mémoire conversationnelle (fenêtre + archives)
│   ├── tavily.py                 # Recherche web Tavily
│   ├── scraper.py                # Scraping ciblé (site configuré via le tool set_scraper)
│   ├── introspect.py             # Auto-analyse : le bot examine ses tools, routines, config
│   ├── config_tools.py           # set_llm, set_rules, set_memory_window, get_status
│   │
│   │  # --- Domain tools (ajoutés selon le domaine) ---
│   └── ...                       # L'utilisateur ajoute ses tools Python ici
│
├── tools_md/                     # Descripteurs de tools déclaratifs (pattern MD)
│   └── README.md                 # Doc du format des tool descriptors
│
├── requirements.txt
├── setup.sh                      # Installation automatique (venv, deps, systemd, dossiers)
└── CLAUDE.md                     # Ce fichier
```

### Données runtime (`DATA_DIR`)

Par défaut : `~/.autobot/` (surchargeable via `DATA_DIR` dans `.env`).

```
~/.autobot/
├── .env                          # Secrets et config (copié à l'install, jamais versionné)
│
├── data/                         # Données fixes (CSV) — le domaine de l'utilisateur
│   ├── *.csv                     # Ex: positions.csv, inventory.csv, contacts.csv...
│   └── README.md                 # Documentation du schéma des CSV
│
├── tools_md/                     # Tool descriptors déclaratifs (voir section dédiée)
│   └── *.md                      # Chaque .md = un tool supplémentaire pour le LLM
│
├── routines/                     # Routines de veille planifiées
│   ├── crontab                   # Jobs planifiés (installé via install_crontab.sh)
│   ├── crontab.bak               # Backup auto avant chaque modif
│   ├── install_crontab.sh        # Script d'installation crontab
│   └── *.md                      # Routines : frontmatter YAML + system_prompt
│
├── scrapers/                     # Descripteurs de sites pour le scraping ciblé
│   └── *.md                      # Chaque .md = un site cible avec ses sélecteurs
│
└── memory/                       # Mémoire conversationnelle
    ├── current.json              # Fenêtre glissante (durée configurable)
    └── YYYY-MM-DD.md             # Archives groupées par date du message
```

---

## Bot Discord (`bot.py`)

### Comportement

- Écoute **uniquement** le channel configuré (`DISCORD_CHANNEL_ID`)
- Ignore les messages du bot lui-même et des autres bots
- Chaque message utilisateur déclenche une complétion LLM avec les tools disponibles
- Répond dans le même channel en découpant les messages > 1990 caractères
- Aucune slash command : toute action passe par le flux LLM (function calling)

### Boucle LLM (function calling multi-tour)

```
message utilisateur
        ↓
charger contexte (mémoire fenêtre glissante)
        ↓
charger tools (core + tools_md/ dynamiques)
        ↓
appel LLM avec tools[]
        ↓
   finish_reason == "tool_calls" ?
        ├── oui → exécuter tool → ajouter résultat → rappel LLM
        └── non → réponse finale → envoyer sur Discord → sauvegarder en mémoire
```

Limite de sécurité : **max 15 tours par message** (configurable via `MAX_TOOL_ROUNDS`).

### System prompt

Le system prompt est assemblé dynamiquement à chaque message :

```
1. Règles de base (DATA_DIR/RULES.md si existant, sinon défaut générique)
2. Date/heure courante
3. Liste des tools disponibles (résumé)
4. Hint introspect : "Tu disposes d'un tool introspect pour examiner tes propres
   tools, routines, scrapers et données. Utilise-le quand on te pose une question
   sur tes capacités ou ta configuration."
5. Contexte mémoire (fenêtre glissante)
```

L'utilisateur personnalise le comportement du bot en éditant `RULES.md` dans `DATA_DIR`.
**Ce même `RULES.md` est aussi préfixé au system_prompt de chaque routine** (voir `runner.py`),
de sorte que les règles s'appliquent uniformément au chat interactif et aux exécutions cron.

---

## Pilotage en langage naturel (pas de slash commands)

AutoBot est un bot **LLM-first**. Il n'y a pas de slash commands : tout ce qu'un
utilisateur pourrait vouloir configurer, inspecter ou planifier passe par un
**tool exposé au LLM** que celui-ci appelle de lui-même quand l'utilisateur en
parle en langage naturel.

### Pourquoi pas de slash commands ?

- Le LLM sait déjà router une intention vers le bon tool — dupliquer ça en
  commandes statiques double la surface à maintenir.
- Les slash commands figent une syntaxe ; en langage naturel l'utilisateur
  formule comme il veut (*« reset ta mémoire »*, *« oublie tout »*,
  *« archive cette conversation »* → même tool `reset_memory`).
- Les paramètres complexes (créer une routine avec sources + cron + prompt)
  sont infiniment plus naturels en dialogue qu'en formulaire slash.
- Moins de code Discord, moins de couplage à la plateforme : porter le bot sur
  Slack/Telegram demande zéro réécriture côté UX.

### Tools de configuration exposés au LLM

Ces tools — répartis dans `tools/config_tools.py`, `tools/memory.py`,
`tools/scheduler.py`, `tools/introspect.py`, `tools/scraper.py` — sont
appelés par le LLM en réaction à une demande utilisateur.

| Tool | Effet | Phrase déclenchant l'appel (exemples) |
|------|-------|---------------------------------------|
| `set_llm(provider, model, api_key?)` | Change le LLM actif (à chaud) | *« passe sur GPT-4o »*, *« utilise Claude »* |
| `set_rules(text)` | Réécrit `RULES.md` | *« à partir de maintenant, réponds en anglais »* |
| `set_memory_window(hours)` | Durée fenêtre mémoire | *« étends ta mémoire à 48h »* |
| `set_scraper(name, url)` | Crée un descripteur scraper (interactif) | *« configure un scraper pour drouot.com »* |
| `get_status()` | Renvoie LLM, tools chargés, routines actives | *« montre-moi ta config »* |
| `reset_memory()` | Archive la fenêtre courante et la vide | *« reset ta mémoire »*, *« repars de zéro »* |
| `recall_day(date)` | Charge une archive en contexte | *« rappelle-toi le 2026-05-12 »* |
| `forget_before(date)` | Supprime archives antérieures | *« oublie tout avant mai »* |
| `list_routines()` / `read_routine(name)` | Inspection routines | *« quelles routines tournent ? »* |
| `create_routine(name, sources, system_prompt, cron_expr?)` | Crée + planifie | *« crée une routine qui résume HN à 7h »* |
| `delete_routine(name)` | Supprime + dé-planifie | *« supprime la routine metals »* |
| `schedule` / `reschedule` / `unschedule` | Planification fine | *« pause la routine X »*, *« change le cron de Y »* |
| `run_now(routine_name)` | Exécute une routine immédiatement | *« lance la routine veille_tech »* |
| `list_tools(type?)` / `read_tool_definition(name)` | Auto-inspection des tools | *« quels tools tu as ? »*, *« montre-moi le tool X »* |
| `reload_tools()` | Recharge `tools_md/` à chaud | *« recharge tes tools »* |
| `explain_self(question)` | Synthèse capacités (tools+routines+règles) | *« qu'est-ce que tu sais faire ? »* |

### Garde-fous

- Les tools qui **modifient** la config (set_llm, set_rules, create_routine,
  delete_routine, reset_memory, forget_before) sont décrits au LLM avec
  l'instruction explicite : *« confirme avec l'utilisateur avant d'appeler ce
  tool si la demande est ambiguë »*.
- Tous les noms (routine, tool, scraper) passent par `_validate_name`.
- Les tools d'introspection (`list_*`, `read_*`, `get_status`, `explain_self`)
  sont en lecture seule et peuvent être appelés sans confirmation.

---

## Système de Tools

Le framework distingue trois types de tools :

### 1. Core Tools (Python, toujours présents)

Implémentés en Python dans `tools/`. Ils constituent le noyau minimal du framework.

#### `data_reader` — Lecture des données

Lit les fichiers CSV et MD du dossier `DATA_DIR/data/`.

| Nom | Paramètres | Description |
|-----|-----------|-------------|
| `read_csv` | `filename: str`, `filters?: dict` | Lit un CSV, filtres optionnels sur colonnes |
| `list_data_files` | — | Liste les fichiers disponibles dans `data/` |
| `read_file` | `filename: str` | Lit un fichier texte/MD du dossier `data/` |

#### `scheduler` — Routines de veille

Gère `DATA_DIR/routines/` et le fichier `routines/crontab`.

> ⚠️ `install_crontab.sh` remplace TOUTE la crontab de l'utilisateur courant.
> Pour conserver des entrées externes, les ajouter directement dans `routines/crontab`.

**Invariants critiques :**

- **`PYTHON_BIN` unique** : toute invocation Python passe par cette constante (le venv). Interdit : `python3` littéral, `sys.executable`, `python` nu.
- **Matching par marker** : les fonctions détectent les lignes d'une routine via `$DATA_DIR/routines/<name>.md ` (chemin absolu + espace final). Le `DATA_DIR` dans le marker garantit qu'une instance ne touche jamais aux routines d'une autre. Helper unique `_routine_marker(name)`.
- **Validation du nom** : chaque fonction publique appelle `_validate_name` en première instruction (anti path-traversal).
- **Crontab isolée par instance** : `install_crontab.sh` ne remplace que les lignes contenant le `DATA_DIR` de l'instance courante, pas toute la crontab. Les entrées des autres instances et les entrées manuelles sont préservées.

| Nom | Paramètres | Description |
|-----|-----------|-------------|
| `list_routines` | — | Routines + statut planifié/non planifié |
| `create_routine` | `name, sources[], system_prompt, cron_expr?` | Crée `routines/name.md` et planifie |
| `delete_routine` | `routine_name` | Supprime fichier + entrée crontab |
| `schedule` | `routine_name, cron_expr` | Planifie une routine existante |
| `reschedule` | `routine_name, cron_expr` | Modifie la planification |
| `unschedule` | `routine_name` | Retire du cron sans supprimer |
| `run_now` | `routine_name` | Lance en subprocess détaché |

#### `memory` — Mémoire conversationnelle

Fenêtre glissante (durée configurable, défaut 24h) + archives MD par date.

Format de `current.json` :
```json
[
  {"ts": "2026-05-16T08:32:11Z", "role": "user",      "content": "..."},
  {"ts": "2026-05-16T08:32:15Z", "role": "assistant",  "content": "..."}
]
```

À chaque message :
1. Charger `current.json`
2. Archiver les entrées hors fenêtre dans `memory/YYYY-MM-DD.md` (date du message)
3. Injecter les messages restants en contexte LLM
4. Ajouter le nouvel échange et sauvegarder

| Nom | Paramètres | Description |
|-----|-----------|-------------|
| `get_context` | — | Retourne la fenêtre mémoire courante |
| `reset_memory` | — | Archive tout et vide la fenêtre |
| `recall_day` | `date: str (YYYY-MM-DD)` | Charge une archive passée |

#### `tavily` — Recherche web

| Nom | Paramètres | Description |
|-----|-----------|-------------|
| `web_search` | `query: str`, `max_results: int = 5` | Recherche web Tavily + résumé IA |

#### `introspect` — Auto-analyse du bot

Le bot peut examiner sa propre configuration : tools, routines, scrapers, règles, données. C'est le mécanisme qui lui permet de **raisonner sur ses propres capacités** et de répondre à des questions comme "qu'est-ce que tu sais faire ?", "montre-moi la routine metals", "quel tool utilise positions.csv ?", "est-ce que tu as un scraper pour Drouot ?".

Le LLM utilise `introspect` spontanément quand une question porte sur les capacités ou la configuration du bot — il suffit de demander en langage naturel (« quels tools as-tu ? », « montre-moi le tool X »).

| Nom | Paramètres | Description |
|-----|-----------|-------------|
| `list_tools` | `type?: str` | Liste les tools enregistrés. `type` filtre : `core`, `md`, `scraper`, ou `all` (défaut). Retourne nom + description + source (Python/MD/scraper). |
| `read_tool_definition` | `name: str` | Retourne le contenu complet d'un tool : pour un core tool → le JSON schema exposé au LLM + docstring ; pour un tool MD → le fichier `.md` brut (frontmatter + corps) ; pour un scraper → le descripteur `.md` du scraper. |
| `list_routines_full` | — | Liste toutes les routines avec leur contenu complet (frontmatter + system_prompt), pas juste le nom. Permet au bot de comprendre ce que fait chaque routine. |
| `read_routine` | `name: str` | Retourne le `.md` brut d'une routine (frontmatter YAML + system_prompt). |
| `read_rules` | — | Retourne le contenu de `RULES.md`. |
| `list_data_schemas` | — | Pour chaque CSV dans `data/`, retourne le nom du fichier, les en-têtes de colonnes, le nombre de lignes, et un échantillon (5 premières lignes). Permet au bot de comprendre la structure des données sans tout charger. |
| `get_config_summary` | — | Retourne la config active (LLM provider/model, memory window, nombre de tools/routines/scrapers, DATA_DIR). Masque les clés API. |
| `explain_self` | `question: str` | Meta-tool : le bot reçoit la question + un dump de toute sa config (règles, liste tools, liste routines, liste scrapers, schémas CSV) et génère une réponse cohérente sur ses propres capacités. Utile pour "que sais-tu faire ?" sans que l'utilisateur connaisse les noms exacts. |

**Cas d'usage clés :**

- *L'utilisateur demande "qu'est-ce que tu peux faire ?"* → le LLM appelle `explain_self` qui agrège règles + tools + routines pour une réponse contextualisée.
- *L'utilisateur demande "montre-moi la routine quantum"* → `read_routine("quantum")` retourne le MD brut.
- *L'utilisateur demande "quel tool utilise positions.csv ?"* → `list_tools("all")` + `read_tool_definition` sur chaque tool pour chercher la référence au fichier.
- *Le LLM hésite entre deux tools* → il appelle `read_tool_definition` sur chacun pour comparer leurs capacités avant de choisir.
- *L'utilisateur veut modifier une routine* → le bot appelle `read_routine` pour voir l'état actuel avant de proposer les changements via `delete_routine` + `create_routine`.

**Sécurité :** les tools d'introspection sont en **lecture seule**. Ils ne modifient aucun fichier. Les clés API sont masquées dans `get_config_summary`.

---

#### `scraper` — Scraping ciblé

Scrape un site configuré via le tool `set_scraper` (déclenché en demandant au bot) ou via un descripteur `.md` dans `DATA_DIR/scrapers/`.

| Nom | Paramètres | Description |
|-----|-----------|-------------|
| `scrape_site` | `scraper_name: str`, `query?: str` | Scrape selon le descripteur MD du site |
| `list_scrapers` | — | Liste les scrapers configurés |

### 2. Tools déclaratifs (Markdown)

L'utilisateur peut créer des tools **sans écrire de Python** en déposant un fichier `.md` dans `DATA_DIR/tools_md/`.

#### Format d'un tool descriptor (`.md`)

```markdown
---
name: get_portfolio_summary
description: "Calcule la valeur totale du portefeuille et les P&L par position"
parameters:
  - name: assets
    type: array
    items: string
    description: "Filtre optionnel sur des assets spécifiques"
    required: false
source:
  type: csv
  file: positions.csv
logic: |
  1. Lire positions.csv
  2. Grouper par asset, calculer qty nette (purchases - sales)
  3. Pour chaque position ouverte, retourner: asset, qty, PRU (CMUP sur price_eur)
  4. Si le paramètre assets est fourni, filtrer
output: json
---

## Contexte

Ce tool calcule les positions courantes à partir du fichier positions.csv.
Le PRU est calculé par CMUP (coût moyen unitaire pondéré) sur les prix en EUR.
Les ventes réduisent la quantité mais ne modifient pas le PRU.
```

Le framework traduit ce `.md` en :
1. Un **JSON schema** pour le function calling du LLM
2. Une **fonction d'exécution** générée qui suit la `logic` décrite :
   - `source.type: csv` → charge le CSV, applique les filtres
   - `source.type: api` → appelle une URL avec les paramètres
   - `source.type: computed` → le LLM interprète la logique sur les données chargées
   - `source.type: scraper` → utilise un scraper configuré

#### Chargement dynamique

Au démarrage et lors d'un appel au tool `reload_tools` (que le LLM déclenche quand on lui demande de recharger ses tools), le framework :
1. Scanne `DATA_DIR/tools_md/*.md`
2. Parse le frontmatter YAML
3. Génère les `TOOLS_DEFINITIONS` correspondantes
4. Les ajoute au registre aux côtés des core tools

### 3. Scraper tools (dynamiques)

Configurés via le tool `set_scraper` (déclenché en langage naturel) ou en déposant un `.md` dans `DATA_DIR/scrapers/`.

#### Format d'un scraper descriptor (`.md`)

```markdown
---
name: drouot_search
base_url: https://www.drouot.com
description: "Recherche d'enchères sur Drouot"
parameters:
  - name: query
    type: string
    description: "Terme de recherche"
    required: true
---

## Méthode d'extraction

1. Naviguer vers {base_url}/recherche?q={query}
2. Extraire les éléments `.auction-card` :
   - Titre : `.auction-card__title`
   - Prix : `.auction-card__price`
   - Date : `.auction-card__date`
   - Lien : `a[href]`
3. Retourner un tableau JSON des résultats
```

Le framework génère :
- Un tool LLM (`drouot_search`) avec le schéma des paramètres
- Une fonction d'exécution qui utilise `httpx` + `beautifulsoup4` pour scraper selon les sélecteurs décrits

---

## Runner de routines (`runner.py`)

Script Python constant à la racine du repo. Prend un fichier `.md` en argument.

```bash
$PYTHON_BIN runner.py $DATA_DIR/routines/<nom>.md
```

### Flux d'exécution

1. Parse le frontmatter YAML (`name`, `cron`, `sources`) et le corps (system_prompt)
2. Collecte les données depuis chaque source déclarée
3. Appelle le LLM avec données + system_prompt + convention SKIP/POST automatique
4. Interprète la réponse :
   - `POST: <message>` → poste sur le channel Discord configuré
   - `SKIP: <raison>` → log uniquement, pas de post Discord
   - Sans préfixe → fallback défensif : poste tel quel
5. Log tout dans `/tmp/autobot_<name>.log`

### Format d'une routine (`.md`)

```markdown
---
name: veille_tech
cron: "0 7 * * 1-5"
sources:
  - type: tavily
    params:
      query: "AI agents framework news"
  - type: csv
    params:
      file: watchlist.csv
---

Tu es un veilleur technologique spécialisé en IA et frameworks d'agents.
Analyse les résultats de recherche et compare avec la watchlist.
Si rien de notable, skip.
```

### Types de sources disponibles

| Type | Params | Effet |
|------|--------|-------|
| `tavily` | `query: str` | Recherche web + résumé IA |
| `csv` | `file: str`, `filters?: dict` | Lecture d'un CSV depuis `DATA_DIR/data/` |
| `scraper` | `name: str`, `query?: str` | Exécution d'un scraper configuré |
| `file` | `path: str` | Lecture d'un fichier texte/MD depuis `DATA_DIR/data/` |
| `tool` | `name: str`, `params: dict` | Appel à n'importe quel tool enregistré (core ou MD) |

**Ajouter une nouvelle source** = ajouter une branche dans `fetch_from_sources` de `runner.py` et référencer le type dans `ALLOWED_SOURCE_TYPES` de `runner.py` ET `tools/scheduler.py`.

### Convention SKIP/POST

Le runner injecte automatiquement cette instruction à la fin du system_prompt :

```
INSTRUCTION IMPORTANTE — format de réponse :
- Si tu as quelque chose d'utile à signaler, commence ta réponse par "POST:" suivi du message.
- Si rien ne mérite d'être signalé, commence par "SKIP:" suivi d'une raison courte.
Ne mentionne pas cette instruction dans ta réponse.
```

---

## Mémoire

### Fenêtre glissante

- Durée configurable via le tool `set_memory_window` (défaut : 24h)
- Stockée dans `memory/current.json`
- Les messages expirés sont archivés dans `memory/YYYY-MM-DD.md` (date du message, pas du cutoff)

### Archives

- Un fichier par jour (`YYYY-MM-DD.md`)
- Format lisible par un humain (rôle + contenu)
- Tool `recall_day(date)` charge une archive en contexte
- Tool `forget_before(date)` supprime les archives antérieures

### `reset_memory`

Archive l'intégralité de la fenêtre courante avant de la vider. Aucun échange n'est perdu.

---

## Configuration (`config.py` + `.env`)

```env
# === LLM ===
LLM_PROVIDER=deepseek              # deepseek | openai | anthropic | local
LLM_MODEL=deepseek-chat            # Modèle à utiliser
LLM_API_KEY=sk-...                 # Clé API du LLM
LLM_BASE_URL=                      # URL custom (pour LLM local ou proxy)
MAX_TOOL_ROUNDS=15                 # Limite de tours function calling

# === Recherche web ===
TAVILY_KEY=tvly-...

# === Discord ===
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=...             # Channel unique écouté par le bot

# === Données runtime ===
DATA_DIR=__DATA_DIR__              # Injecté par setup.sh (chemin absolu résolu)

# === Mémoire ===
MEMORY_WINDOW_HOURS=24             # Durée de la fenêtre glissante

# === Logs ===
LOG_LEVEL=INFO                     # DEBUG | INFO | WARNING | ERROR
```

### Variables dérivées (calculées par `config.py`)

```python
DATA_DIR       = Path(os.getenv("DATA_DIR", Path.home() / ".autobot"))
ROUTINES_DIR   = DATA_DIR / "routines"
MEMORY_DIR     = DATA_DIR / "memory"
TOOLS_MD_DIR   = DATA_DIR / "tools_md"
SCRAPERS_DIR   = DATA_DIR / "scrapers"
DATA_FILES_DIR = DATA_DIR / "data"
PYTHON_BIN     = Path(__file__).parent / "venv" / "bin" / "python3"
```

**En production, utiliser des chemins absolus** dans `.env` et dans les commandes shell. Ne jamais `~/` dans systemd ou crontab.

---

## Logs (`structlog`)

`bot.py` configure `structlog` avec `JSONRenderer` + `PrintLoggerFactory`. Les logs partent sur **stdout**. En production, le service systemd les capture dans le journal.

```json
{"event":"tool_call","tool":"web_search","query":"AI news","level":"info","timestamp":"2026-05-16T08:32:11Z"}
```

Consultation : `journalctl -u autobot`

Les routines cron redirigent vers `/tmp/autobot_<name>.log`.

---

## Installation (`setup.sh`)

### Principe : zéro chemin hardcodé, multi-instance natif

Le script détecte automatiquement où il se trouve et en déduit tout le reste. Il accepte un **nom d'instance** optionnel pour déployer plusieurs bots depuis le même repo.

```bash
bash setup.sh                  # instance par défaut : "autobot"
bash setup.sh trading          # instance nommée "trading"
bash setup.sh veille-tech      # instance nommée "veille-tech"
```

Chaque instance a son propre `DATA_DIR`, son propre service systemd, son propre channel Discord et ses propres routines. Le code et le venv sont **partagés** (un seul repo git).

```
Un repo, N instances :

    $REPO_DIR/                         ← code partagé (git)
    $REPO_DIR/venv/                    ← venv partagé
    │
    ├── $HOME/.autobot/                ← instance par défaut
    ├── $HOME/.autobot-trading/        ← instance "trading"
    └── $HOME/.autobot-veille-tech/    ← instance "veille-tech"

    systemd :
    ├── autobot.service
    ├── autobot-trading.service
    └── autobot-veille-tech.service
```

### Permissions — pas besoin de root

Le bot tourne entièrement en espace utilisateur. Le seul `sudo` est pour créer le service systemd. Sans accès sudo, une alternative `nohup` est fournie en bas.

```
Quoi                              Root ?
───────────────────────────────────────────
Code + venv ($REPO_DIR)           Non
Données runtime ($DATA_DIR)       Non
Crontab utilisateur               Non
Service systemd                   sudo (optionnel)
```

### Script

```bash
#!/bin/bash
set -euo pipefail

# === Auto-détection — ne rien hardcoder ===
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCE="${1:-autobot}"                              # nom d'instance (défaut: autobot)
INSTANCE="$(echo "$INSTANCE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')"

if [ "$INSTANCE" = "autobot" ]; then
  DATA_DIR="$(realpath "${DATA_DIR:-$HOME/.autobot}")"
else
  DATA_DIR="$(realpath "${DATA_DIR:-$HOME/.autobot-$INSTANCE}")"
fi

SERVICE_NAME="autobot-$INSTANCE"
[ "$INSTANCE" = "autobot" ] && SERVICE_NAME="autobot"
PYTHON_BIN="$REPO_DIR/venv/bin/python3"

echo "=== AutoBot Setup ==="
echo "  INSTANCE = $INSTANCE"
echo "  REPO_DIR = $REPO_DIR"
echo "  DATA_DIR = $DATA_DIR"
echo "  SERVICE  = $SERVICE_NAME"
echo "  USER     = $USER"

# 1. Venv (partagé entre instances, créé une seule fois)
if [ ! -f "$PYTHON_BIN" ]; then
  python3 -m venv "$REPO_DIR/venv"
  "$REPO_DIR/venv/bin/pip" install --upgrade pip
fi
"$REPO_DIR/venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

# 2. Dossiers data (propres à l'instance)
mkdir -p "$DATA_DIR"/{data,routines,memory,tools_md,scrapers}

# 3. .env (propre à l'instance)
if [ ! -f "$DATA_DIR/.env" ]; then
  sed -e "s|__DATA_DIR__|$DATA_DIR|g" \
      -e "s|__INSTANCE__|$INSTANCE|g" \
      "$REPO_DIR/.env.template" > "$DATA_DIR/.env"
  echo "→ Éditer $DATA_DIR/.env avec vos clés API"
fi

# 4. Règles par défaut (appliquées au chat et aux routines)
if [ ! -f "$DATA_DIR/RULES.md" ]; then
  cat > "$DATA_DIR/RULES.md" << 'RULES'
Tu es un assistant Discord autonome. Tu utilises tes tools pour répondre
aux questions et exécuter des tâches. Sois concis et utile.

Ces règles s'appliquent au chat interactif et aux routines planifiées.
RULES
fi

# 5. Service systemd (optionnel — skip si pas sudo)
if command -v sudo &> /dev/null && sudo -n true 2>/dev/null; then
  sudo tee "/etc/systemd/system/$SERVICE_NAME.service" > /dev/null << EOF
[Unit]
Description=AutoBot Discord ($INSTANCE)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$DATA_DIR/.env
ExecStart=$PYTHON_BIN $REPO_DIR/bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable "$SERVICE_NAME"
  echo "=== Lancer : sudo systemctl start $SERVICE_NAME ==="
else
  echo "=== Pas d'accès sudo — lancer manuellement ==="
  echo "  DATA_DIR=$DATA_DIR $PYTHON_BIN $REPO_DIR/bot.py"
fi
```

### Variantes de lancement (sans systemd)

```bash
# Foreground (dev/debug) — DATA_DIR en variable d'env pour sélectionner l'instance
DATA_DIR=$HOME/.autobot-trading ./venv/bin/python3 bot.py

# Background avec nohup
DATA_DIR=$HOME/.autobot-trading nohup ./venv/bin/python3 bot.py >> /tmp/autobot-trading.log 2>&1 &

# tmux (une session par instance)
tmux new -d -s trading "DATA_DIR=$HOME/.autobot-trading ./venv/bin/python3 bot.py"
tmux new -d -s veille  "DATA_DIR=$HOME/.autobot-veille-tech ./venv/bin/python3 bot.py"
```

### Gestion multi-instance

```bash
# Installer 3 instances depuis le même repo
cd ~/autobot
bash setup.sh trading
bash setup.sh veille-tech
bash setup.sh crm

# Chaque instance a son propre service
sudo systemctl start autobot-trading
sudo systemctl start autobot-veille-tech
sudo systemctl start autobot-crm

# Logs séparés
journalctl -u autobot-trading -f
journalctl -u autobot-veille-tech -f

# Les routines cron sont isolées (chaque DATA_DIR a son propre dossier routines/)
# Le scheduler utilise un marker par instance pour ne pas écraser les cron des autres
```

### Ce qui est partagé vs isolé

| Élément | Partagé | Isolé par instance |
|---------|---------|-------------------|
| Code Python (`bot.py`, `tools/`, `engine/`) | ✅ | |
| Venv + dépendances | ✅ | |
| `.env` (clés API, channel Discord) | | ✅ |
| `RULES.md` | | ✅ |
| `data/*.csv` | | ✅ |
| `tools_md/*.md` | | ✅ |
| `scrapers/*.md` | | ✅ |
| `routines/*.md` + crontab | | ✅ |
| `memory/` | | ✅ |
| Service systemd | | ✅ |
| Channel Discord | | ✅ |

---

## Chemins — règle absolue

Aucun fichier du projet ne contient de chemin hardcodé vers un utilisateur ou un dossier spécifique.

| Contexte | Comment le chemin est résolu |
|----------|------------------------------|
| `config.py` | `REPO_DIR = Path(__file__).parent` / `DATA_DIR = Path(os.getenv("DATA_DIR", Path.home() / ".autobot"))` |
| `setup.sh` | `REPO_DIR="$(cd "$(dirname "$0")" && pwd)"` / instance → `$HOME/.autobot-<name>` |
| crontab | Le scheduler écrit les chemins absolus résolus au moment de la création de la routine |
| systemd | `EnvironmentFile=$DATA_DIR/.env` — le `.env` contient `DATA_DIR` résolu |
| runner.py | Reçoit le `.md` en argument absolu, lit `DATA_DIR` depuis env ou `config.py` |
| bot.py | Lit `DATA_DIR` depuis env (injecté par systemd via `.env`) |

**Audit** : `grep -rn '/home/' *.py tools/ engine/` ne doit rien retourner.

---

## Création d'un bot personnalisé — Guide rapide

### Étape 1 : Cloner et installer

```bash
git clone <repo_url> autobot
cd autobot
bash setup.sh mon-bot           # choisir un nom pour l'instance
```

### Étape 2 : Configurer les clés API

Le setup a créé un `.env` pré-rempli avec les chemins. Il reste à ajouter vos clés :

```bash
nano "$HOME/.autobot-mon-bot/.env"
```

Chaque instance a **son propre `DISCORD_BOT_TOKEN` et `DISCORD_CHANNEL_ID`** — c'est ce qui permet d'avoir plusieurs bots sur le même serveur Discord (un channel par bot).

### Étape 3 : Définir les règles

```bash
nano "$HOME/.autobot-mon-bot/RULES.md"
```

`RULES.md` est injecté à la fois dans le system prompt du chat et dans celui de chaque routine.

### Étape 4 : Déposer vos données

Placer vos CSV dans `$DATA_DIR/data/`.

### Étape 5 : Créer des tools personnalisés (optionnel)

Déposer des `.md` dans `$DATA_DIR/tools_md/`.

### Étape 6 : Configurer des scrapers (optionnel)

Demander au bot dans Discord *« configure un scraper pour <url> »* ou déposer un `.md` dans `$DATA_DIR/scrapers/`.

### Étape 7 : Créer des routines

Via Discord en demandant *« crée une routine qui … »* (le bot appelle `create_routine`) ou en déposant un `.md` dans `$DATA_DIR/routines/`.

### Étape 8 : Lancer

```bash
sudo systemctl start autobot-mon-bot
```

---

## Exemples de déclinaisons

### Bot de trading (l'original)

```
RULES.md       → Analyste trading, style concis, focus portefeuille
data/          → positions.csv, observed_tickers.csv
tools_md/      → get_portfolio_summary.md, get_moving_averages.md
scrapers/      → (aucun)
routines/      → quantum.md, metals.md, weekly_recap.md
.env           → + POLYGON_API_KEY pour un tool Python custom polygon.py
```

### Bot de veille technologique

```
RULES.md       → Veilleur tech, résumés quotidiens, focus IA/cloud
data/          → watchlist.csv (entreprises et sujets suivis)
tools_md/      → analyze_trend.md
scrapers/      → hackernews.md, techcrunch.md
routines/      → daily_digest.md, breaking_news.md
```

### Bot de suivi CRM

```
RULES.md       → Assistant commercial, suivi pipeline
data/          → contacts.csv, deals.csv, activities.csv
tools_md/      → deal_summary.md, next_actions.md
scrapers/      → linkedin_company.md
routines/      → daily_pipeline.md, stale_deals_alert.md
```

---

## Sécurité et garde-fous

### Validation des entrées LLM

- `_validate_name()` sur tout nom de fichier fourni par le LLM (anti path-traversal)
- Sanitisation CSV anti-injection (`= + - @ | \t \r` → préfixe `'`)
- Limite de tours function calling (`MAX_TOOL_ROUNDS`)
- Timeout sur les appels réseau (LLM, Tavily, scraping)

### Crontab

- `install_crontab.sh` ne touche qu'aux lignes contenant le `DATA_DIR` de l'instance courante
- Les routines des autres instances et les entrées manuelles sont préservées
- `crontab.bak` backup automatique avant chaque modification
- Logs des routines dans `/tmp/autobot-<instance>_<name>.log`

### Mémoire

- La fenêtre glissante évite l'explosion du contexte
- Les archives sont des fichiers plats inspectables
- Le tool `forget_before` permet le RGPD-compliant data cleanup

### Scraping

- Rate limiting configurable par scraper
- User-Agent configurable
- Respect des `robots.txt` (optionnel, activable)

---

## Invariants critiques (à ne PAS casser)

1. **`PYTHON_BIN` unique** : toute invocation Python (crontab, subprocess) utilise cette constante. `grep -n 'python3\|sys.executable' tools/scheduler.py` ne doit retourner que la définition.

2. **Matching crontab par marker** : `$DATA_DIR/routines/<name>.md ` (chemin absolu + espace final). Le `DATA_DIR` dans le marker isole les instances entre elles. Helper `_routine_marker(name)`. Ne jamais matcher sur `<name>.md` seul.

3. **Séparation code/data** : aucun chemin hardcodé dans le code. Tout passe par `config.py` qui lit `DATA_DIR` depuis l'environnement.

4. **Zéro chemin hardcodé** : `grep -rn '/home/' *.py tools/ engine/` ne doit rien retourner. Tous les chemins sont résolus dynamiquement.

5. **Tools MD = déclaratifs** : un `.md` dans `tools_md/` ne doit jamais contenir de code exécutable. La logique est interprétée, pas exécutée.

6. **Runner constant** : `runner.py` est versionné dans le repo. Toute routine de toute instance bénéficie des correctifs après `git pull + systemctl restart`.

7. **Append-only pour les données** : les CSV dans `data/` sont append-only. Les outils d'écriture ajoutent des lignes, jamais de modification ni suppression.

8. **Isolation des instances** : chaque instance a son propre `DATA_DIR`, `.env`, channel Discord, mémoire et routines. Le code et le venv sont partagés.

---

## Dépendances (`requirements.txt`)

```
discord.py>=2.3
httpx>=0.27
beautifulsoup4>=4.12
structlog>=24.0
python-dotenv>=1.0
pyyaml>=6.0
aiofiles>=24.0
```

Plus les dépendances spécifiques au domaine (ex: `yfinance`, `polygon-api-client` pour le bot trading).

---

## Roadmap framework

- [ ] Interface web de configuration (alternative au dialogue Discord)
- [ ] Support multi-channel (un set de règles par channel)
- [ ] Webhook Discord en plus du bot (pour intégrations externes)
- [ ] Plugin system pour les core tools (pip installable)
- [ ] Support Telegram / Slack en plus de Discord
- [ ] Dashboard de monitoring des routines (statut, dernière exécution, erreurs)
- [ ] Tests automatisés des tools MD (validation du schema + dry-run)
