from __future__ import annotations

import threading
from pathlib import Path
from unittest import mock

from src.agent.conversation_store import ConversationStore


class TestConversationStoreThreadSafety:
    def test_concurrent_add_turn_no_history_loss(self, tmp_path: Path) -> None:
        store = ConversationStore("concurrent-add", store_dir=str(tmp_path))

        n_threads = 10
        turns_per_thread = 20
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _add_turns(tid: int) -> None:
            barrier.wait()
            for i in range(turns_per_thread):
                try:
                    store.add_turn(f"user_{tid}_{i}", f"asst_{tid}_{i}")
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_add_turns, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent add_turn: {errors}"
        history = store.history
        expected_turns = n_threads * turns_per_thread * 2  # user + assistant each
        assert len(history) == expected_turns, (
            f"Expected {expected_turns} messages, got {len(history)}"
        )

    def test_concurrent_history_and_add_turn(self, tmp_path: Path) -> None:
        store = ConversationStore("concurrent-read-write", store_dir=str(tmp_path))

        n_threads = 8
        iterations = 50
        barrier = threading.Barrier(n_threads * 2)
        errors: list[Exception] = []

        def _writer(tid: int) -> None:
            barrier.wait()
            for i in range(iterations):
                try:
                    store.add_turn(f"w{tid}_q{i}", f"w{tid}_a{i}")
                except Exception as e:
                    errors.append(e)

        def _reader(tid: int) -> None:
            barrier.wait()
            for _ in range(iterations):
                try:
                    _ = store.history
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_writer, args=(tid,)) for tid in range(n_threads)
        ] + [threading.Thread(target=_reader, args=(tid,)) for tid in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent read/write: {errors}"

    def test_concurrent_summarize_does_not_lose_turns(self, tmp_path: Path) -> None:
        store = ConversationStore("concurrent-summarize", store_dir=str(tmp_path))

        n_writers = 4
        turns_per_writer = 10
        barrier = threading.Barrier(n_writers + 2)
        errors: list[Exception] = []
        summarize_lock = threading.Lock()
        summarize_calls: list[str] = []

        def _summarize_fn(prompt: str) -> str:
            with summarize_lock:
                summarize_calls.append(prompt)
            return "merged summary"

        store.set_summarize_fn(_summarize_fn)

        def _writer(tid: int) -> None:
            barrier.wait()
            for i in range(turns_per_writer):
                try:
                    store.add_turn(f"q_{tid}_{i}", f"a_{tid}_{i}")
                except Exception as e:
                    errors.append(e)

        def _summarizer() -> None:
            barrier.wait()
            for _ in range(5):
                try:
                    store.summarize()
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_writer, args=(tid,)) for tid in range(n_writers)
        ]
        threads.append(threading.Thread(target=_summarizer))
        threads.append(threading.Thread(target=_summarizer))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent summarize: {errors}"
        assert store.summary == "merged summary"

        summarizer_count = len([s for s in summarize_calls if s])
        assert summarizer_count > 0, "summarize should have been called"

    def test_concurrent_save_load_consistency(self, tmp_path: Path) -> None:
        store = ConversationStore("concurrent-save", store_dir=str(tmp_path))

        n_threads = 10
        turns_per_thread = 10
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _writer(tid: int) -> None:
            barrier.wait()
            for i in range(turns_per_thread):
                try:
                    store.add_turn(f"q_{tid}_{i}", f"a_{tid}_{i}")
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_writer, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent writes: {errors}"

        store2 = ConversationStore("concurrent-save", store_dir=str(tmp_path))
        expected_turns = n_threads * turns_per_thread * 2
        assert len(store2.history) == expected_turns, (
            f"Expected {expected_turns} messages after reload, "
            f"got {len(store2.history)}"
        )

    def test_concurrent_add_classifier_turn(self, tmp_path: Path) -> None:
        store = ConversationStore("concurrent-cls", store_dir=str(tmp_path))

        n_threads = 8
        turns_per_thread = 15
        barrier = threading.Barrier(n_threads)
        errors: list[Exception] = []

        def _writer(tid: int) -> None:
            barrier.wait()
            for i in range(turns_per_thread):
                try:
                    store.add_classifier_turn(f"input_{tid}_{i}", f"label_{tid}_{i}")
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_writer, args=(tid,)) for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent add_classifier_turn: {errors}"
        history = store.history
        expected = n_threads * turns_per_thread * 2
        assert len(history) == expected, (
            f"Expected {expected} messages, got {len(history)}"
        )

    def test_concurrent_set_summary_and_history(self, tmp_path: Path) -> None:
        store = ConversationStore("concurrent-summary", store_dir=str(tmp_path))
        store.add_turn("initial", "ok")

        n_threads = 6
        iterations = 30
        barrier = threading.Barrier(n_threads * 2)
        errors: list[Exception] = []

        def _set_summary(tid: int) -> None:
            barrier.wait()
            for i in range(iterations):
                try:
                    store.set_summary(f"summary_{tid}_{i}")
                except Exception as e:
                    errors.append(e)

        def _read_history(tid: int) -> None:
            barrier.wait()
            for _ in range(iterations):
                try:
                    _ = store.history
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_set_summary, args=(tid,))
            for tid in range(n_threads)
        ] + [
            threading.Thread(target=_read_history, args=(tid,))
            for tid in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent set_summary/history: {errors}"

    def test_concurrent_summarize_with_exception_handling(self, tmp_path: Path) -> None:
        store = ConversationStore("concurrent-exc", store_dir=str(tmp_path))

        n_threads = 6
        turns_per_thread = 5
        barrier = threading.Barrier(n_threads + 2)
        errors: list[Exception] = []
        call_count: int = 0
        call_lock = threading.Lock()

        def _unreliable_fn(prompt: str) -> str:
            with call_lock:
                nonlocal call_count
                call_count += 1
                if call_count % 3 == 0:
                    msg = "LLM temporarily unavailable"
                    raise RuntimeError(msg)
            return "merged result"

        store.set_summarize_fn(_unreliable_fn)

        def _writer(tid: int) -> None:
            barrier.wait()
            for i in range(turns_per_thread):
                try:
                    store.add_turn(f"q_{tid}_{i}", f"a_{tid}_{i}")
                except Exception as e:
                    errors.append(e)

        def _summarizer() -> None:
            barrier.wait()
            for _ in range(10):
                try:
                    store.summarize()
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=_writer, args=(tid,)) for tid in range(n_threads)
        ]
        threads.append(threading.Thread(target=_summarizer))
        threads.append(threading.Thread(target=_summarizer))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (
            f"Errors during concurrent summarize with exceptions: {errors}"
        )

    def test_concurrent_add_turn_save_failure_recovery(self, tmp_path: Path) -> None:
        store = ConversationStore("concurrent-fail", store_dir=str(tmp_path))

        n_threads = 6
        turns_per_thread = 10
        save_attempts: int = 0
        save_lock = threading.Lock()

        original_save = ConversationStore._save

        def _flaky_save(self: ConversationStore) -> None:
            nonlocal save_attempts
            with save_lock:
                save_attempts += 1
                if save_attempts % 4 == 0:
                    raise OSError("disk full")
            original_save(self)

        with mock.patch.object(ConversationStore, "_save", _flaky_save):
            threads = [
                threading.Thread(
                    target=lambda tid=tid: [
                        store.add_turn(f"q_{tid}_{i}", f"a_{tid}_{i}")
                        for i in range(turns_per_thread)
                    ],
                )
                for tid in range(n_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        history = store.history
        expected_min = n_threads * turns_per_thread * 2
        assert len(history) == expected_min, (
            f"Expected {expected_min} messages, got {len(history)}"
        )

    def test_high_contention_determinism(self, tmp_path: Path) -> None:
        runs = 3
        n_threads = 6
        turns_per_thread = 10
        results: list[int] = []

        for run_idx in range(runs):
            store = ConversationStore(
                f"deterministic-{run_idx}", store_dir=str(tmp_path)
            )
            barrier = threading.Barrier(n_threads)
            errors: list[Exception] = []

            def _writer(
                tid: int,
                _store: ConversationStore = store,
                _barrier: threading.Barrier = barrier,
                _errors: list[Exception] = errors,
            ) -> None:
                _barrier.wait()
                for i in range(turns_per_thread):
                    try:
                        _store.add_turn(f"q_{tid}_{i}", f"a_{tid}_{i}")
                    except Exception as e:
                        _errors.append(e)

            threads = [
                threading.Thread(target=_writer, args=(tid,))
                for tid in range(n_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors
            results.append(len(store.history))

        assert all(r == results[0] for r in results), (
            f"Non-deterministic: history lengths differ across runs: {results}"
        )
