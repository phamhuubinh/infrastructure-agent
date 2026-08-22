"""Safe, local discovery of concrete SSH aliases.

This module only reads SSH configuration and invokes ``ssh -G`` for aliases
that configuration itself declares. It fails closed when `Match exec` is
present and disables hostname canonicalization before configuration expansion.
It never opens a transport connection or authenticates; actual reachability
remains the responsibility of TargetPreflight and SSHExecutionBackend.
"""

from __future__ import annotations

import fnmatch
import glob
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

_SAFE_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_WILDCARD_CHARS = frozenset("*!?")


@dataclass(frozen=True, slots=True)
class DiscoveredSSHTarget:
    """Connection fields resolved locally from one concrete SSH alias."""

    alias: str
    host: str
    user: str
    port: int
    identity_file: str | None
    strict_host_key_checking: bool


def discover_ssh_targets(
    config_path: Path | None = None,
) -> tuple[DiscoveredSSHTarget, ...]:
    """Return concrete aliases from SSH config, resolved without connecting.

    Missing, unreadable, malformed, or unresolvable configuration fails closed
    as an empty (or partial) discovery result.  Aliases come solely from Host
    directives; pattern-only directives are never promoted to targets.
    """

    path = config_path or Path.home() / ".ssh" / "config"
    include_base = path.expanduser().parent
    if _contains_match_exec(path, include_base=include_base, seen=set()):
        return ()
    aliases = _concrete_aliases(path, include_base=include_base)
    discovered: list[DiscoveredSSHTarget] = []
    for alias in aliases:
        target = _resolve_alias(path, alias)
        if target is not None:
            discovered.append(target)
    return tuple(discovered)


def _concrete_aliases(path: Path, *, include_base: Path) -> tuple[str, ...]:
    aliases: set[str] = set()
    for keyword, values in _config_directives(
        path,
        include_base=include_base,
        seen=set(),
    ):
        if keyword != "host":
            continue
        negatives = tuple(value[1:] for value in values if value.startswith("!"))
        for alias in values:
            if _is_concrete_alias(alias) and not any(
                fnmatch.fnmatchcase(alias, pattern) for pattern in negatives
            ):
                aliases.add(alias)
    return tuple(sorted(aliases))


def _config_directives(
    path: Path,
    *,
    include_base: Path,
    seen: set[Path],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Read aliases and unconditional includes from one SSH config tree."""

    directives = _read_config_directives(path, seen=seen)
    if directives is None:
        return ()

    result: list[tuple[str, tuple[str, ...]]] = []
    in_conditional_section = False
    for keyword, values in directives:
        if keyword == "include":
            if not in_conditional_section:
                for include_path in _included_paths(values, include_base):
                    result.extend(
                        _config_directives(
                            include_path,
                            include_base=include_base,
                            seen=seen,
                        )
                    )
        elif keyword == "host":
            result.append((keyword, values))
            in_conditional_section = True
        elif keyword == "match":
            in_conditional_section = True
    return tuple(result)


def _contains_match_exec(
    path: Path,
    *,
    include_base: Path,
    seen: set[Path],
) -> bool:
    """Return true when config expansion could execute a local Match command."""

    directives = _read_config_directives(path, seen=seen)
    if directives is None:
        return True
    for keyword, values in directives:
        if keyword == "match" and any(
            _is_match_exec_criterion(value) for value in values
        ):
            return True
        if keyword == "include":
            if _has_unscannable_include_path(values):
                return True
            for include_path in _included_paths(values, include_base):
                if _contains_match_exec(
                    include_path,
                    include_base=include_base,
                    seen=seen,
                ):
                    return True
    return False


def _read_config_directives(
    path: Path,
    *,
    seen: set[Path],
) -> tuple[tuple[str, tuple[str, ...]], ...] | None:
    try:
        resolved_path = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved_path in seen:
        return ()
    seen.add(resolved_path)

    try:
        lines = resolved_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None

    directives: list[tuple[str, tuple[str, ...]]] = []
    for line in lines:
        try:
            parts = shlex.split(line, comments=True, posix=True)
        except ValueError:
            return None
        directive = _normalize_config_directive(parts)
        if directive is not None:
            directives.append(directive)
    return tuple(directives)


def _normalize_config_directive(
    parts: list[str],
) -> tuple[str, tuple[str, ...]] | None:
    """Normalize OpenSSH's whitespace and ``keyword=value`` spellings."""

    if not parts:
        return None
    keyword, separator, inline_value = parts[0].partition("=")
    values = list(parts[1:])
    if separator:
        if inline_value:
            values.insert(0, inline_value)
    elif values and values[0] == "=":
        values.pop(0)
    elif values and values[0].startswith("="):
        values[0] = values[0][1:]
    if not keyword or not values:
        return None
    return keyword.lower(), tuple(values)


def _included_paths(values: tuple[str, ...], include_base: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for value in values:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = include_base / candidate
        paths.extend(Path(match) for match in sorted(glob.glob(str(candidate))))
    return tuple(paths)


def _has_unscannable_include_path(values: tuple[str, ...]) -> bool:
    """Reject Include token expansion that this static scanner cannot verify."""

    return any("$" in value or "%" in value for value in values)


def _is_match_exec_criterion(value: str) -> bool:
    criterion = value.lower()
    if criterion.startswith("!"):
        criterion = criterion[1:]
    return criterion == "exec"


def _is_concrete_alias(alias: str) -> bool:
    return (
        bool(_SAFE_ALIAS.fullmatch(alias))
        and not any(character in alias for character in _WILDCARD_CHARS)
    )


def _resolve_alias(path: Path, alias: str) -> DiscoveredSSHTarget | None:
    """Resolve a vetted alias with OpenSSH after static safety checks."""

    try:
        completed = subprocess.run(
            [
                "ssh",
                "-F",
                str(path),
                "-o",
                "CanonicalizeHostname=no",
                "-G",
                alias,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None

    options = _parse_ssh_options(completed.stdout)
    host = options.get("hostname", "").strip()
    user = options.get("user", "").strip()
    try:
        port = int(options.get("port", "22"))
    except ValueError:
        return None
    if not host or not user or not 1 <= port <= 65535:
        return None

    identity_file = options.get("identityfile") or None
    strict_value = options.get("stricthostkeychecking", "ask").lower()
    return DiscoveredSSHTarget(
        alias=alias,
        host=host,
        user=user,
        port=port,
        identity_file=identity_file,
        strict_host_key_checking=strict_value not in {"no", "off", "false"},
    )


def _parse_ssh_options(output: str) -> dict[str, str]:
    options: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition(" ")
        if separator and key and value and key not in options:
            options[key.lower()] = value.strip()
    return options
