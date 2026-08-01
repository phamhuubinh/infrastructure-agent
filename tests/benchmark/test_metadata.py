from __future__ import annotations

from benchmark.metadata import collect_benchmark_metadata


class TestCollectBenchmarkMetadata:
    def test_default_metadata(self) -> None:
        meta = collect_benchmark_metadata()
        assert meta["server"] == ""
        assert meta["model"] == "mock"
        assert meta["benchmark_version"] == "1.0"
        assert isinstance(meta["timestamp"], int)
        assert meta["timestamp"] > 0
        assert "captured_at" in meta
        assert "git_commit" in meta

    def test_with_server_and_model(self) -> None:
        meta = collect_benchmark_metadata(server_name="sv1", model="gpt-4")
        assert meta["server"] == "sv1"
        assert meta["model"] == "gpt-4"

    def test_unknown_server_without_model_uses_mock_label(self) -> None:
        meta = collect_benchmark_metadata(server_name="not-configured")
        assert meta["server"] == "not-configured"
        assert meta["model"] == "mock"

    def test_timestamp_is_int(self) -> None:
        meta = collect_benchmark_metadata()
        assert isinstance(meta["timestamp"], int)
