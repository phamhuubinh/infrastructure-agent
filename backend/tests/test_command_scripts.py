"""Private script lifecycle, crash provenance and conservative orphan cleanup."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from orion_endpoint.command_scripts import ScriptCache, _ordinary, protect_script_path


def write_script(cache, directory):
    path = directory / "command.sh"
    path.touch(mode=0o600)
    protect_script_path(path)
    _ordinary(path, cache.owner)
    path.write_text("private-script-marker", encoding="utf-8")
    return path


def test_private_cache_removes_only_owned_script(tmp_path):
    cache = ScriptCache(tmp_path)
    with cache.directory("sh") as directory:
        script = write_script(cache, directory)
        _ordinary(directory, cache.owner, directory=True)
    assert not script.exists() and not directory.exists()
    with cache.directory("sh") as directory:
        script = write_script(cache, directory)
        unrelated = directory / "shell-created-file"
        unrelated.write_text("preserve", encoding="utf-8")
    assert not script.exists()
    assert unrelated.read_text() == "preserve"
    ScriptCache(tmp_path)
    assert unrelated.exists()


def test_crash_orphan_pruning_preserves_live_and_unknown_paths(tmp_path):
    cache = ScriptCache(tmp_path)
    foreign = cache.root / ("a" * 32)
    foreign.mkdir()
    (foreign / "unknown").write_text("preserve")
    program = (
        "import os,sys; from pathlib import Path; "
        "from orion_endpoint.command_scripts import ScriptCache,protect_script_path; "
        "cache=ScriptCache(Path(sys.argv[1])); cm=cache.directory('sh'); "
        "directory=cm.__enter__(); p=directory/'command.sh'; p.touch(mode=0o600); "
        "protect_script_path(p); p.write_text('orphan-private-script'); "
        "print(directory,flush=True); os._exit(0)"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", program, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    orphan = Path(completed.stdout.strip())
    assert orphan.parent == cache.root and (orphan / "command.sh").exists()
    with cache.directory("sh") as live:
        live_script = write_script(cache, live)
        ScriptCache(tmp_path)
        assert live_script.exists()
        assert not orphan.exists()
        assert (foreign / "unknown").exists()


def test_linked_script_and_altered_marker_are_never_deleted(tmp_path):
    cache = ScriptCache(tmp_path)
    outside = tmp_path / "unrelated-source"
    outside.write_text("preserve")
    with cache.directory("sh") as directory:
        script = directory / "command.sh"
        os.link(outside, script)
    assert script.exists() and outside.read_text() == "preserve"
    with cache.directory("sh") as changed:
        original = write_script(cache, changed)
        marker = changed / "owner.json"
        record = json.loads(marker.read_bytes())
        record["script"] = "../../unrelated-source"
        marker.write_text(json.dumps(record))
    ScriptCache(tmp_path)
    assert original.exists() and outside.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows Job kill-on-close on abrupt worker exit")
def test_abrupt_worker_exit_kills_its_real_descendant_tree(tmp_path):
    pid_file = tmp_path / "child-pid"
    child = tmp_path / "child.py"
    child.write_text(
        "import os,time\nfrom pathlib import Path\n"
        f"Path({str(pid_file)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"
    )
    program = (
        "import asyncio,os,sys,uuid; from pathlib import Path; "
        "from orion_endpoint.commands import CommandProcesses; "
        "from orion_endpoint.command_scripts import ScriptCache\n"
        "async def run():\n"
        " runner=CommandProcesses(); runner._script_cache=ScriptCache(Path(sys.argv[1]))\n"
        " await runner.start({'command_id':uuid.uuid4().hex,'shell':'cmd',"
        f"'command':{('"' + sys.executable + '" "' + str(child) + '"')!r}}})\n"
        " for _ in range(200):\n"
        "  if Path(sys.argv[2]).exists(): os._exit(0)\n"
        "  await asyncio.sleep(.02)\n"
        " raise RuntimeError('child did not start')\n"
        "asyncio.run(run())\n"
    )
    subprocess.run(
        [sys.executable, "-B", "-c", program, str(tmp_path), str(pid_file)],
        capture_output=True,
        timeout=15,
        check=True,
    )
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 5
    while psutil.pid_exists(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not psutil.pid_exists(pid)
    cache = ScriptCache(tmp_path)
    assert list(cache.root.iterdir()) == [cache.root / "owner.json"]
