#!/usr/bin/env bash
set -euo pipefail

bundle="$(cd "$(dirname "$0")" && pwd)"
prefix="${HOME}/.local/share/orion-install"
explicit=false
global_launcher=false
while (($#)); do
  case "$1" in
    --prefix) (($# >= 2)) || { echo '--prefix requires a directory' >&2; exit 2; }; prefix="$2"; explicit=true; shift 2 ;;
    --global-launcher) global_launcher=true; shift ;;
    -h|--help) echo 'Usage: install.sh [--prefix DIRECTORY] [--global-launcher]'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ -n "${ORION_PYTHON:-}" ]]; then
  python_bin="$ORION_PYTHON"
else
  python_bin=''
  for candidate in python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
      python_bin="$(command -v "$candidate")"
      break
    fi
  done
fi
if [[ -z "$python_bin" ]] || ! "$python_bin" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
  echo 'Python 3.12 or newer is required; set ORION_PYTHON if necessary.' >&2
  exit 1
fi
"$python_bin" "$bundle/payload.py" verify --root "$bundle" --platform linux-x86_64
version="$("$python_bin" -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$bundle/release-manifest.json")"
wheel="$bundle/orion-$version-py3-none-any.whl"

mkdir -p "$prefix"
prefix="$(cd "$prefix" && pwd)"
venv="$prefix/.venv"
if [[ ! -x "$venv/bin/python" ]]; then
  "$python_bin" -m venv "$venv"
fi
"$venv/bin/python" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))' || {
  echo 'Existing Orion virtual environment requires Python 3.12+.' >&2; exit 1;
}
"$venv/bin/python" -m pip install "$wheel"
"$venv/bin/python" -c 'import json,sys; from pathlib import Path; m=json.loads(Path(sys.argv[1]).read_text()); Path(sys.prefix,".orion-build.json").write_text(json.dumps({"version":m["version"],"source_sha":m["commit"]}))' "$bundle/release-manifest.json"
"$venv/bin/python" -c 'import orion.ui_package,sys; from pathlib import Path; orion.ui_package.replace_ui_bundle(Path(sys.argv[1]),Path(sys.argv[2]))' "$bundle/ui" "$prefix/.orion-ui"
"$venv/bin/orion" model install embeddings

if [[ "$explicit" == false || "$global_launcher" == true ]]; then
  launcher_dir="${XDG_BIN_HOME:-$HOME/.local/bin}"
  launcher="$launcher_dir/orion"
  mkdir -p "$launcher_dir"
  if [[ -e "$launcher" || -L "$launcher" ]] &&
    ! grep -Fq '# Orion managed launcher' "$launcher" 2>/dev/null &&
    ! grep -Fq 'scripts/orion' "$launcher" 2>/dev/null; then
    echo "Refusing to overwrite unrelated launcher: $launcher" >&2
    exit 1
  fi
  temporary="$(mktemp "$launcher_dir/.orion-launcher.XXXXXX")"
  {
    echo '#!/usr/bin/env bash'
    echo '# Orion managed launcher'
    printf 'exec %q "$@"\n' "$venv/bin/orion"
  } > "$temporary"
  chmod 755 "$temporary"
  mv -f "$temporary" "$launcher"
  echo "Installed Orion $version. Run: orion"
else
  echo "Installed Orion $version. Run: $venv/bin/orion"
fi
