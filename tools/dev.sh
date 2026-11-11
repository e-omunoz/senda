#!/usr/bin/env sh
# Atajos de desarrollo de Senda (Linux/macOS/Git Bash). Ver tools/README.md.
#   tools/dev.sh build | validate [--json] | check | test | package | all
#   tools/dev.sh install-dev --target "/ruta/a/_forever_/Interface/AddOns"
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
fi

cmd="${1:-help}"
[ $# -gt 0 ] && shift

case "$cmd" in
  build)    exec "$PY" "$ROOT/tools/build.py" "$@" ;;
  check)    exec "$PY" "$ROOT/tools/build.py" --check "$@" ;;
  validate) exec "$PY" "$ROOT/tools/validate.py" "$@" ;;
  test)     exec "$PY" -m unittest discover -s "$ROOT/tests" -p "test_*.py" "$@" ;;
  package)  exec "$PY" "$ROOT/tools/package.py" "$@" ;;
  all)
    "$PY" "$ROOT/tools/validate.py"
    "$PY" "$ROOT/tools/build.py"
    exec "$PY" "$ROOT/tools/package.py"
    ;;
  install-dev)
    # Sin ruta por defecto: --target es obligatorio y package.py lo vuelve a comprobar.
    case " $* " in
      *" --target "*|*" --target="*) ;;
      *) echo "install-dev: falta --target <ruta a Interface/AddOns>. No hay ruta por defecto." >&2; exit 2 ;;
    esac
    exec "$PY" "$ROOT/tools/package.py" --install-dev "$@"
    ;;
  help|-h|--help)
    sed -n '2,4p' "$0" | sed 's/^# \{0,1\}//'
    ;;
  *)
    echo "Comando desconocido: $cmd (build, check, validate, test, package, all, install-dev)" >&2
    exit 2
    ;;
esac
