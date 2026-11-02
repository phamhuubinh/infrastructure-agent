"""Build a bounded fixed-source stdlib helper; no application installation remotely."""

from __future__ import annotations

from importlib.resources import files

_MODULES = ("remote_files", "remote_protocol", "remote_runner", "remote")


def helper_payload() -> bytes:
    package = files("orion.integrations.ssh")
    sources = {
        name: package.joinpath(name + ".py").read_text(encoding="utf-8") for name in _MODULES
    }
    supervisor = package.joinpath("supervisor.py").read_text(encoding="utf-8")
    # Only developer-owned packaged modules enter exec/compile. Model command
    # text travels later as validated JSON and is executed by the selected shell.
    payload = (
        "import sys,types\n"
        "package=types.ModuleType('_orion_ssh');package.__path__=[]\n"
        "sys.modules['_orion_ssh']=package\n"
        f"sources={sources!r}\n"
        "for name,source in sources.items():\n"
        " module=types.ModuleType('_orion_ssh.'+name);module.__package__='_orion_ssh'\n"
        " sys.modules[module.__name__]=module\n"
        " exec(compile(source,'<orion-ssh-'+name+'>','exec'),module.__dict__)\n"
        f"sys.modules['_orion_ssh.remote'].main({supervisor!r})\n"
    ).encode()
    if not 0 < len(payload) <= 131_072:
        raise ValueError("SSH helper payload exceeds its bound")
    return payload
