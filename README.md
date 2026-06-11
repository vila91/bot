# AutoBot

Framework Python pour créer des bots Discord autonomes alimentés par un LLM (DeepSeek par défaut).

Un bot AutoBot :

- **Discute** dans un channel Discord dédié avec function calling multi-tour
- **Exécute des routines planifiées** décrites en Markdown (cron)
- **Utilise des tools** modulaires : core Python ou déclaratifs `.md`
- **Lit vos données** depuis des CSV/MD que vous déposez
- **Se configure** à chaud via slash commands Discord (`/`)

Le framework est **générique** : on le décline pour son domaine (trading, veille tech, CRM, monitoring…) en déposant des fichiers de données et de routines, sans toucher au code.

Pour la vision complète, l'architecture détaillée et les invariants critiques, voir [CLAUDE.md](CLAUDE.md).

---

## Prérequis

- Python 3.12+
- Un serveur Linux (ou WSL/macOS pour le dev)
- Un bot Discord (token + channel ID)
- Une clé API LLM (DeepSeek recommandé, OpenAI/Anthropic supportés)
- Optionnel : clé Tavily pour la recherche web

---

## Installation rapide

```bash
git clone <repo_url> autobot
cd autobot
bash setup.sh                  # instance par défaut
# ou : bash setup.sh trading   # instance nommée
```

Le script :

1. Crée le venv (`./venv/`) et installe `requirements.txt`
2. Crée le `DATA_DIR` (`~/.autobot/` ou `~/.autobot-<instance>/`)
3. Génère le `.env` depuis `.env.template` avec les chemins résolus
4. Crée un `persona.md` par défaut
5. Installe le service systemd `autobot[-<instance>].service` (si `sudo` dispo)

À la fin, le script affiche le chemin du `.env` à compléter.

---

## Configuration

### 1. Renseigner le `.env`

```bash
nano "$HOME/.autobot/.env"           # ou .autobot-<instance>/.env
```

Variables minimales à remplir :

| Variable | Description |
|----------|-------------|
| `DISCORD_BOT_TOKEN` | Token du bot Discord |
| `DISCORD_CHANNEL_ID` | ID du channel écouté (un seul) |
| `LLM_API_KEY` | Clé du LLM (DeepSeek par défaut) |
| `TAVILY_KEY` | Optionnel — pour le tool `web_search` |

Les autres variables (`LLM_PROVIDER`, `LLM_MODEL`, `MEMORY_WINDOW_HOURS`, `MAX_TOOL_ROUNDS`, `LOG_LEVEL`) ont des défauts sains.

### 2. Définir le persona

Le persona pilote le ton et le rôle du bot. Édite `persona.md` dans le `DATA_DIR` :

```bash
nano "$HOME/.autobot/persona.md"
```

Exemple :

```markdown
Tu es un analyste trading. Réponses concises, focus portefeuille.
Tu utilises tes tools pour lire positions.csv et calculer les P&L.
```

Modifiable aussi à chaud via `/set_persona`.

### 3. Déposer vos données

Place tes fichiers dans `$DATA_DIR/data/` :

- CSV pour les données structurées (`positions.csv`, `watchlist.csv`, `contacts.csv`…)
- MD/TXT pour les notes, briefs, contextes longs

Le tool `read_csv` / `read_file` les lit à la demande du LLM.

### 4. Lancer le bot

```bash
sudo systemctl start autobot         # instance par défaut
sudo systemctl status autobot        # vérifier
journalctl -u autobot -f             # logs temps réel
```

Sans systemd :

```bash
DATA_DIR=$HOME/.autobot ./venv/bin/python3 bot.py
```

---

## Utilisation au quotidien

### Discuter

Écris dans le channel Discord configuré. Le bot répond avec la mémoire des dernières heures (fenêtre glissante de 24h par défaut).

### Slash commands

| Catégorie | Commandes |
|-----------|-----------|
| **Config** | `/set_llm` `/set_persona` `/set_memory_window` `/set_scraper` `/status` |
| **Mémoire** | `/reset` `/recall <date>` `/forget <before>` |
| **Routines** | `/routines` `/run <name>` `/pause <name>` `/resume <name>` `/create_routine` `/delete_routine` |
| **Tools** | `/tools` `/tool_info <name>` `/reload_tools` |

### Routines planifiées

Crée une routine via Discord (`/create_routine`) ou en déposant un `.md` dans `$DATA_DIR/routines/` :

```markdown
---
name: veille_tech
cron: "0 7 * * 1-5"
sources:
  - type: tavily
    params:
      query: "AI agents framework news"
---

Tu es un veilleur tech. Analyse les résultats et résume.
Si rien de notable, skip.
```

Puis installer la crontab :

```bash
bash $DATA_DIR/routines/install_crontab.sh
```

Le runner écrit sur le channel Discord (`POST: …`) ou skip silencieusement (`SKIP: …`).

### Tools personnalisés (sans Python)

Dépose un `.md` dans `$DATA_DIR/tools_md/` (voir le format dans CLAUDE.md, section **Tools déclaratifs**). Le bot le charge au démarrage ou via `/reload_tools`.

### Scrapers

Configure un site via `/set_scraper <name> <url>` (assistant interactif) ou dépose un `.md` dans `$DATA_DIR/scrapers/`. Le scraper devient un tool LLM utilisable dans le chat et dans les routines.

---

## Multi-instance

Un seul repo, plusieurs bots :

```bash
bash setup.sh trading
bash setup.sh veille-tech
bash setup.sh crm

sudo systemctl start autobot-trading autobot-veille-tech autobot-crm
```

Chaque instance a son `DATA_DIR`, son `.env`, son channel Discord, ses routines et sa mémoire. Le code et le venv sont partagés — un `git pull` met à jour toutes les instances.

---

## Mise à jour

```bash
cd autobot
git pull
./venv/bin/pip install -r requirements.txt
sudo systemctl restart autobot       # + les autres instances si besoin
```

Le `DATA_DIR` (données, routines, mémoire) n'est jamais touché par les mises à jour de code.

---

## Dépannage

| Symptôme | Piste |
|----------|-------|
| Le bot ne répond pas | `journalctl -u autobot -n 100` — vérifier token Discord et channel ID |
| Erreur LLM | Vérifier `LLM_API_KEY` et `LLM_BASE_URL` dans `.env` |
| Routine ne s'exécute pas | `crontab -l` puis consulter `/tmp/autobot_<name>.log` |
| Tool MD non chargé | `/reload_tools` puis `/tool_info <name>` ; vérifier le frontmatter YAML |
| Mémoire trop courte | `/set_memory_window 48` |

---

## Documentation complète

- [CLAUDE.md](CLAUDE.md) — architecture, stack technique, format des tools/routines/scrapers, invariants critiques, exemples de déclinaisons
- `tools_md/README.md` — format détaillé des tool descriptors
