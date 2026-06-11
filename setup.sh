#!/bin/bash
set -euo pipefail

# === Auto-détection — ne rien hardcoder ===
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTANCE="${1:-autobot}"
INSTANCE="$(echo "$INSTANCE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g')"

if [ "$INSTANCE" = "autobot" ]; then
  DATA_DIR="$(realpath -m "${DATA_DIR:-$HOME/.autobot}")"
else
  DATA_DIR="$(realpath -m "${DATA_DIR:-$HOME/.autobot-$INSTANCE}")"
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
mkdir -p "$DATA_DIR"/{data,routines,memory,scrapers}

# 3. .env (propre à l'instance)
if [ ! -f "$DATA_DIR/.env" ]; then
  sed -e "s|__DATA_DIR__|$DATA_DIR|g" \
      -e "s|__INSTANCE__|$INSTANCE|g" \
      "$REPO_DIR/.env.template" > "$DATA_DIR/.env"
  echo "→ Éditer $DATA_DIR/.env avec vos clés API"
fi

# 4. RULES.md par défaut (règles générales partagées chat + routines)
if [ ! -f "$DATA_DIR/RULES.md" ]; then
  cat > "$DATA_DIR/RULES.md" << 'RULES'
Tu es un assistant Discord autonome. Tu utilises tes tools pour répondre
aux questions et exécuter des tâches. Sois concis et utile.
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
