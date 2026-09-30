from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from orion.bootstrap import build_application
from orion.contracts import RuntimeScope
from orion.knowledge import local_embeddings as local


def test_missing_and_corrupt_model_never_provision_at_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(local, "urlopen", lambda *_args, **_kwargs: pytest.fail("network call"))
    assert local.model_status(tmp_path / "missing") == "missing"
    with pytest.raises(RuntimeError, match="missing"):
        local.LocalE5Embeddings(tmp_path / "missing")
    corrupt = tmp_path / "corrupt"
    corrupt.mkdir()
    (corrupt / ".complete").write_text(local.PROFILE.profile_id)
    (corrupt / "model.onnx").write_bytes(b"wrong")
    assert local.model_status(corrupt) == "corrupt"
    with pytest.raises(RuntimeError, match="corrupt"):
        local.LocalE5Embeddings(corrupt)


def test_missing_model_keeps_startup_search_and_read_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ORION_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(local, "urlopen", lambda *_args, **_kwargs: pytest.fail("network call"))
    application = build_application(tmp_path / "orion.db")
    try:
        session = application.store.create_session()
        upload = application.knowledge.attach(session, "offline.txt", b"offline knowledge fact")
        scope = RuntimeScope(
            session_id=session,
            attachment_ids=(upload.attachment_id,),
            project_id=None,
            principal_id="local",
            workspace_id="local",
        )
        assert application.knowledge.search(scope, "knowledge", 5)
        assert application.knowledge.read(scope, upload.document.document_id).segments
        assert local.model_status() == "missing"
    finally:
        application.store.close()


def test_interrupted_install_does_not_publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(local, "urlopen", fail)
    target = tmp_path / "model"
    with pytest.raises(RuntimeError, match="interrupted"):
        local.install_model(target)
    assert local.model_status(target) == "missing"
    assert list(tmp_path.iterdir()) == []


def test_model_load_failure_is_clear(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(local, "model_status", lambda *_args: "installed")

    def fail_import(_name: str) -> None:
        raise OSError("bad ONNX runtime")

    monkeypatch.setattr(local.importlib, "import_module", fail_import)
    with pytest.raises(RuntimeError, match="bad ONNX runtime"):
        local.LocalE5Embeddings(tmp_path)


def test_wrong_download_digest_does_not_publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(local, "FILES", {"model.onnx": "0" * 64})
    monkeypatch.setattr(local, "urlopen", lambda *_args, **_kwargs: BytesIO(b"wrong"))
    target = tmp_path / "model"
    with pytest.raises(RuntimeError, match="digest mismatch"):
        local.install_model(target)
    assert local.model_status(target) == "missing"


class _Tokenizer:
    def encode(self, text: str, *, add_special_tokens: bool) -> SimpleNamespace:
        words = text.split()
        return SimpleNamespace(ids=([0] if add_special_tokens else []) + words)

    def decode(self, ids: list[str], *, skip_special_tokens: bool) -> str:
        return " ".join(ids)


def test_token_windows_boundaries_and_determinism() -> None:
    adapter = object.__new__(local.LocalE5Embeddings)
    adapter._tokenizer = _Tokenizer()
    capacity = 512 - 1 - 1
    exact = " ".join(f"word{i}" for i in range(capacity))
    assert adapter.passage_windows(exact) == (exact,)
    long_text = " ".join(f"word{i}" for i in range(capacity + 1))
    windows = adapter.passage_windows(long_text)
    assert len(windows) == 2
    assert windows == adapter.passage_windows(long_text)
    assert windows[0] == exact
    assert windows[1].split()[0] == f"word{capacity - 32}"
    assert adapter.passage_windows("   ") == ("",)
    assert adapter.passage_windows("separate") == ("separate",)


class _Model:
    def __init__(self, output: object) -> None:
        self.output = output
        self.inputs: list[str] = []

    def embed(self, texts: object, *, batch_size: int) -> object:
        self.inputs = list(texts)  # type: ignore[arg-type]
        if isinstance(self.output, Exception):
            raise self.output
        return iter(self.output)  # type: ignore[arg-type]


def test_adapter_prefix_and_output_contracts() -> None:
    adapter = object.__new__(local.LocalE5Embeddings)
    unit = (1.0,) + (0.0,) * 383
    model = _Model([unit])
    adapter._model = model
    assert adapter.embed_queries(("hello",)) == (unit,)
    assert model.inputs == ["query: hello"]
    assert adapter.embed_passages(("world",)) == (unit,)
    assert model.inputs == ["passage: world"]
    for output, message in (
        ([], "count"),
        ([(1.0,)], "dimension"),
        ([(math.nan,) + (0.0,) * 383], "finite"),
        ([(2.0,) + (0.0,) * 383], "normalization"),
    ):
        adapter._model = _Model(output)
        with pytest.raises(ValueError, match=message):
            adapter.embed_queries(("hello",))
    adapter._model = _Model(RuntimeError("broken inference"))
    with pytest.raises(RuntimeError, match="broken inference"):
        adapter.embed_queries(("hello",))


def test_provisioned_model_loads_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    if local.model_status() != "installed":
        pytest.skip("Operator has not provisioned the optional E5 model")
    import fastembed.common.model_management as model_management

    monkeypatch.setattr(local, "urlopen", lambda *_args, **_kwargs: pytest.fail("network call"))
    monkeypatch.setattr(
        model_management,
        "snapshot_download",
        lambda *_args, **_kwargs: pytest.fail("HuggingFace download call"),
    )
    assert local.install_model() == "installed"
    adapter = local.LocalE5Embeddings()
    assert len(adapter.embed_queries(("offline",))[0]) == 384
    windows = adapter.passage_windows("hello " * 700)
    assert len(windows) > 1
    assert all(
        len(adapter._tokenizer.encode("passage: " + window).ids) <= 512 for window in windows
    )
