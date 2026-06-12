# AutoBot

Framework Python pour créer des bots Discord autonomes alimentés par un LLM (DeepSeek par défaut).

Un bot AutoBot :

- **Discute** dans un channel Discord dédié avec function calling multi-tour
- **Exécute des routines planifiées** décrites en Markdown (cron)
- **Utilise des tools** modulaires : core Python ou déclaratifs `.md`
- **Lit vos données** depuis des CSV/MD que vous déposez
- **Se configure en langage naturel** : on parle au bot, il modifie sa propre config via ses tools

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
4. Crée un `RULES.md` par défaut (appliqué au chat et aux routines)
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

### 2. Définir les règles

`RULES.md` pilote le ton, le rôle et les contraintes du bot. Ces règles sont
**injectées dans le system prompt du chat ET dans celui de chaque routine** :
ce qui est défini ici s'applique partout. Édite le fichier dans le `DATA_DIR` :

```bash
nano "$HOME/.autobot/RULES.md"
```

Exemple :

```markdown
Tu es un analyste trading. Réponses concises, focus portefeuille.
Tu utilises tes tools pour lire positions.csv et calculer les P&L.
```

Modifiable aussi à chaud en demandant au bot : *« change tes règles : … »* — il édite `RULES.md` via son tool.

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

### Tout se pilote en langage naturel

AutoBot n'a **pas de slash commands**. On parle au bot comme à un humain — il dispose de tools pour tout ce qu'il faut configurer, inspecter ou planifier. Exemples :

| Intention | Ce que tu dis |
|-----------|---------------|
| Voir la config | *« montre-moi ta config »*, *« que sais-tu faire ? »* |
| Changer les règles | *« à partir de maintenant, réponds toujours en anglais »* |
| Changer le LLM | *« passe sur GPT-4o »* |
| Créer une routine | *« crée une routine qui me résume HN chaque matin à 7h »* |
| Lister les routines | *« quelles routines tournent ? »* |
| Lancer une routine | *« exécute la routine veille_tech maintenant »* |
| Mettre en pause | *« pause la routine metals »* |
| Recharger les tools MD | *« recharge tes tools »* |
| Reset mémoire | *« archive cette conversation et repars de zéro »* |
| Recall un jour passé | *« rappelle-toi notre échange du 2026-05-12 »* |
| Configurer un scraper | *« configure un scraper pour drouot.com »* |

Le bot utilise `introspect`, `scheduler`, `memory`, `set_rules`, etc. pour exécuter ces demandes. Si une formulation est ambiguë, il demande confirmation avant d'agir.

### Routines planifiées

Crée une routine en demandant au bot, ou en déposant un `.md` dans `$DATA_DIR/routines/` :

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

Dépose un `.md` dans `$DATA_DIR/tools_md/` (voir le format dans CLAUDE.md, section **Tools déclaratifs**). Le bot le charge au démarrage, ou demande-lui *« recharge tes tools »*.

### Scrapers

Demande au bot *« configure un scraper pour <url> »* (il te questionne sur les sélecteurs) ou dépose directement un `.md` dans `$DATA_DIR/scrapers/`. Le scraper devient un tool LLM utilisable dans le chat et dans les routines.

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
| Tool MD non chargé | Demander *« recharge tes tools »* puis *« décris le tool X »* ; vérifier le frontmatter YAML |
| Mémoire trop courte | *« passe ta fenêtre mémoire à 48h »* |

---

## Documentation complète

- [CLAUDE.md](CLAUDE.md) — architecture, stack technique, format des tools/routines/scrapers, invariants critiques, exemples de déclinaisons
- `tools_md/README.md` — format détaillé des tool descriptors
