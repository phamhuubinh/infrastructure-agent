#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s [--prefix DIRECTORY] [--no-dev]\n' "$0"
}

prefix="$(cd "$(dirname "$0")" && pwd)"
extras='[dev]'

while (($#)); do
  case "$1" in
    --prefix)
      (($# >= 2)) || { echo '--prefix requires a directory.' >&2; exit 2; }
      prefix="$2"
      shift 2
      ;;
    --no-dev)
      extras=''
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

python_bin="${ORION_PYTHON:-}"
if [[ -z "$python_bin" ]]; then
  for candidate in python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c \
      'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
      python_bin="$candidate"
      break
    fi
  done
fi
if [[ -z "$python_bin" ]] || ! "$python_bin" -c \
  'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo 'Python 3.12 or newer is required.' >&2
  exit 1
fi

source_root="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$prefix"
venv="$prefix/.venv"
if [[ ! -x "$venv/bin/python" ]]; then
  "$python_bin" -m venv "$venv"
fi
"$venv/bin/python" -m pip install -e "$source_root/backend$extras"
echo "Installed Orion in $venv. Run: $venv/bin/orion web"
