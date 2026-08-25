#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s [--prefix DIRECTORY] [--no-dev] [--global-launcher]\n' "$0"
}

source_root="$(cd "$(dirname "$0")" && pwd)"
prefix="$source_root"
extras='[dev]'
prefix_was_explicit=false
global_launcher=false

while (($#)); do
  case "$1" in
    --prefix)
      (($# >= 2)) || { echo '--prefix requires a directory.' >&2; exit 2; }
      prefix="$2"
      prefix_was_explicit=true
      shift 2
      ;;
    --no-dev)
      extras=''
      shift
      ;;
    --global-launcher)
      global_launcher=true
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

mkdir -p "$prefix"
prefix="$(cd "$prefix" && pwd)"
venv="$prefix/.venv"

python_candidates=()
python_bin="${ORION_PYTHON:-}"
if [[ -n "$python_bin" ]]; then
  python_candidates+=("ORION_PYTHON=$python_bin")
elif [[ -x "$venv/bin/python" ]]; then
  python_candidates+=("$venv/bin/python")
  if "$venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
    python_bin="$venv/bin/python"
  fi
fi

if [[ -z "$python_bin" ]]; then
  for candidate in python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      candidate_path="$(command -v "$candidate")"
      python_candidates+=("$candidate_path")
      if "$candidate_path" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
        python_bin="$candidate_path"
        break
      fi
    else
      python_candidates+=("$candidate (not found)")
    fi
  done
fi

if [[ -z "$python_bin" ]] || ! "$python_bin" -c \
  'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  {
    echo 'Python 3.12 or newer is required.'
    echo 'Checked Python candidates:'
    for candidate in "${python_candidates[@]}"; do
      if [[ "$candidate" == *' (not found)' ]]; then
        echo "  $candidate"
      elif [[ "$candidate" == ORION_PYTHON=* ]]; then
        value="${candidate#ORION_PYTHON=}"
        echo "  $candidate: $($value --version 2>&1 || echo unavailable)"
      else
        echo "  $candidate: $($candidate --version 2>&1 || echo unavailable)"
      fi
    done
    echo 'Set ORION_PYTHON to a Python 3.12+ interpreter, or create/reuse PREFIX/.venv first.'
  } >&2
  exit 1
fi

require_frontend_tooling() {
  if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "Node.js >=22.12 and npm are required to build Orion's packaged UI." >&2
    exit 1
  fi
  node_version="$(node --version)"
  if [[ ! "$node_version" =~ ^v([0-9]+)\.([0-9]+)\. ]] || \
    (( BASH_REMATCH[1] < 22 || (BASH_REMATCH[1] == 22 && BASH_REMATCH[2] < 12) )); then
    echo "Node.js >=22.12 is required to build Orion's packaged UI (found $node_version)." >&2
    exit 1
  fi
}

install_global_launcher() {
  local launcher_directory launcher temporary
  launcher_directory="${XDG_BIN_HOME:-$HOME/.local/bin}"
  launcher="$launcher_directory/orion"
  mkdir -p "$launcher_directory"
  if [[ -e "$launcher" || -L "$launcher" ]]; then
    if ! grep -Fq '# Orion managed launcher' "$launcher" 2>/dev/null && \
      ! grep -Fq 'scripts/orion' "$launcher" 2>/dev/null; then
      echo "Refusing to overwrite unrelated executable: $launcher" >&2
      echo 'Move it aside or choose a custom --prefix without --global-launcher.' >&2
      exit 1
    fi
  fi
  temporary="$launcher_directory/.orion-launcher.$$"
  {
    echo '#!/usr/bin/env bash'
    echo '# Orion managed launcher'
    printf 'exec %q "$@"\n' "$venv/bin/orion"
  } >"$temporary"
  chmod 755 "$temporary"
  mv -f "$temporary" "$launcher"
}

require_frontend_tooling
if [[ ! -x "$venv/bin/python" ]]; then
  "$python_bin" -m venv "$venv"
fi
"$venv/bin/python" -m pip install -e "$source_root/backend$extras"

# Build a deterministic client bundle. Only these static files are installed;
# normal Orion has no Vite development server or separate Node runtime.
npm ci --prefix "$source_root/ui"
npm run build --prefix "$source_root/ui"
ui_source="$source_root/ui/dist/client"
ui_destination="$prefix/.orion-ui"
if [[ ! -f "$ui_source/index.html" ]]; then
  echo "UI build did not create $ui_source/index.html." >&2
  exit 1
fi
rm -rf -- "$ui_destination"
mkdir -p "$ui_destination"
cp -a "$ui_source/." "$ui_destination/"

if [[ "$prefix_was_explicit" == false || "$global_launcher" == true ]]; then
  install_global_launcher
  echo "Installed Orion in $venv. Run: orion"
else
  echo "Installed Orion in $venv. Run: $venv/bin/orion"
  echo 'A custom --prefix does not change your global launcher; add --global-launcher to manage it.'
fi
