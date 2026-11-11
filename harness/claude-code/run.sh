#!/usr/bin/env bash
# Ejecuta un prompt del harness con Claude Code (usa tu suscripción, no una API key).
#   harness/claude-code/run.sh audit gnome-warlock 01-coldridge
#   harness/claude-code/run.sh watch 7
#   harness/claude-code/run.sh tips Gnome WARLOCK
set -euo pipefail
cd "$(dirname "$0")/../.."
task="${1:?uso: run.sh audit|watch|tips [argumentos]}"; shift || true
file="harness/claude-code/${task}.md"
[ -f "$file" ] || { echo "no existe $file" >&2; exit 2; }
# Quita el frontmatter YAML y sustituye $ARGUMENTS.
prompt="$(awk 'BEGIN{fm=0} NR==1&&/^---$/{fm=1;next} fm&&/^---$/{fm=0;next} !fm' "$file")"
prompt="${prompt//\$ARGUMENTS/$*}"
tools="$(sed -n 's/^allowed-tools: //p' "$file")"
exec claude -p "$prompt" --allowedTools "$tools" --permission-mode acceptEdits
