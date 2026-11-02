"""Headless runtime and lexical/data paths work without semantic dependencies."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_core_lexical_backup_startup_without_semantic_packages(tmp_path):
    source = Path(__file__).parents[1] / "src"
    code = r"""
import importlib.abc
import sys
from pathlib import Path

class BlockSemantic(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'fastembed', 'onnxruntime', 'numpy', 'tokenizers'}:
            raise ModuleNotFoundError('Optional semantic package is absent', name=fullname)

sys.meta_path.insert(0, BlockSemantic())
from orion.bootstrap import build_application
from orion.contracts import AssistantMessage, ModelTurn, ModelTurnCompleted, RuntimeScope
from orion.models.backend import ModelBackend
from orion.persistence.backup import export_bundle, import_bundle

class Backend(ModelBackend):
    async def stream(self, messages, tools, settings, cancellation):
        yield ModelTurnCompleted(turn=ModelTurn(assistant=AssistantMessage(content='fixture')))

root = Path.cwd()
data = root / 'data'
application = build_application(data / 'orion.db', backend=Backend(),
                                seed_model_from_environment=False)
try:
    session = application.store.create_session()
    uploaded = application.knowledge.attach(session, 'fact.txt', b'Unique lexical marker cedar')
    scope = RuntimeScope(principal_id='local', workspace_id='local', session_id=session,
                         attachment_ids=(uploaded.attachment_id,))
    assert application.knowledge.search(scope, 'cedar', 3)
finally:
    application.store.close()
backups = root / 'backups'
backups.mkdir()
bundle = export_bundle(data / 'orion.db', backups)
assert import_bundle(bundle, root / 'restored').is_file()
assert not {'fastembed', 'onnxruntime', 'numpy', 'tokenizers'} & sys.modules.keys()
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONPATH": str(source),
            "ORION_KNOWLEDGE_SEMANTIC_SEARCH": "off",
            "ORION_DATA_DIR": str(tmp_path / "isolated"),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
