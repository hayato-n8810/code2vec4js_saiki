from __future__ import annotations

import fcntl
import pickle
import random
import sys
from contextlib import contextmanager
from pathlib import Path

# jscode2vec 直下のモジュールを scripts 実行時にも解決できるようにする
_JSCODE2VEC_ROOT = Path(__file__).resolve().parents[2]
if str(_JSCODE2VEC_ROOT) not in sys.path:
    sys.path.insert(0, str(_JSCODE2VEC_ROOT))

from histogram_shm_client import load_histograms_from_shared_memory  # noqa: E402

from common import common  # noqa: E402


@contextmanager
def shared_lock(lock_file_path: Path):
    lock_fd = None
    try:
        lock_fd = lock_file_path.open("w", encoding="utf-8")
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_SH)
        yield
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            finally:
                lock_fd.close()


def _load_histograms_from_cache(cache_file: Path) -> tuple[dict[str, int], dict[str, int], dict[str, int]] | None:
    if not cache_file.exists():
        return None

    lock_file = Path(f"{cache_file}.lock")
    with shared_lock(lock_file):
        with cache_file.open("rb") as fp:
            cache_data = pickle.load(fp)
            word_to_count = cache_data.get("word_to_count", {})
            path_to_count = cache_data.get("path_to_count", {})
            target_to_count = cache_data.get("target_to_count", {})

    if not word_to_count or not path_to_count or not target_to_count:
        return None

    return word_to_count, path_to_count, target_to_count


def _context_full_found(context_parts: list[str], word_to_count: dict[str, int], path_to_count: dict[str, int]) -> bool:
    return (
        len(context_parts) == 3
        and context_parts[0] in word_to_count
        and context_parts[1] in path_to_count
        and context_parts[2] in word_to_count
    )


def _context_partial_found(context_parts: list[str], word_to_count: dict[str, int], path_to_count: dict[str, int]) -> bool:
    return (
        len(context_parts) == 3
        and (
            context_parts[0] in word_to_count
            or context_parts[1] in path_to_count
            or context_parts[2] in word_to_count
        )
    )


def _load_histograms(
    word_histogram: Path,
    path_histogram: Path,
    target_histogram: Path,
    word_vocab_size: int,
    path_vocab_size: int,
    target_vocab_size: int,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    word_to_count, path_to_count, target_to_count = load_histograms_from_shared_memory()

    if word_to_count is not None and path_to_count is not None and target_to_count is not None:
        return word_to_count, path_to_count, target_to_count

    cache_file = word_histogram.parent / "histogram_cache.pkl"
    try:
        cached = _load_histograms_from_cache(cache_file)
    except Exception:  # noqa: BLE001
        cached = None
    if cached is not None:
        return cached

    _, _, _, word_to_count = common.load_vocab_from_histogram(
        str(word_histogram),
        start_from=1,
        max_size=word_vocab_size,
        return_counts=True,
    )
    _, _, _, path_to_count = common.load_vocab_from_histogram(
        str(path_histogram),
        start_from=1,
        max_size=path_vocab_size,
        return_counts=True,
    )
    _, _, _, target_to_count = common.load_vocab_from_histogram(
        str(target_histogram),
        start_from=1,
        max_size=target_vocab_size,
        return_counts=True,
    )

    return word_to_count, path_to_count, target_to_count


def _process_line(
    line: str,
    max_contexts: int,
    word_to_count: dict[str, int],
    path_to_count: dict[str, int],
) -> str | None:
    parts = line.rstrip("\n").split(" ")
    if len(parts) < 2:
        return None

    target_name = parts[0]
    contexts = parts[1:]

    if len(contexts) > max_contexts:
        context_parts = [c.split(",") for c in contexts]
        full_found_contexts = [
            c
            for i, c in enumerate(contexts)
            if _context_full_found(context_parts[i], word_to_count, path_to_count)
        ]
        partial_found_contexts = [
            c
            for i, c in enumerate(contexts)
            if _context_partial_found(context_parts[i], word_to_count, path_to_count)
            and not _context_full_found(context_parts[i], word_to_count, path_to_count)
        ]

        if len(full_found_contexts) > max_contexts:
            contexts = random.sample(full_found_contexts, max_contexts)
        elif len(full_found_contexts) + len(partial_found_contexts) > max_contexts:
            contexts = full_found_contexts + random.sample(
                partial_found_contexts,
                max_contexts - len(full_found_contexts),
            )
        else:
            contexts = full_found_contexts + partial_found_contexts

    if len(contexts) == 0:
        return None

    csv_padding = " " * (max_contexts - len(contexts))
    return target_name + " " + " ".join(contexts) + csv_padding


def preprocess_test_data(
    raw_file: Path,
    output_name_base: Path,
    max_contexts: int,
    word_vocab_size: int,
    path_vocab_size: int,
    target_vocab_size: int,
    word_histogram: Path,
    path_histogram: Path,
    target_histogram: Path,
) -> Path:
    if not raw_file.exists():
        raise FileNotFoundError(f"テストデータが存在しません: {raw_file}")

    if not word_histogram.exists() or not path_histogram.exists() or not target_histogram.exists():
        raise FileNotFoundError("ヒストグラムファイルが存在しません")

    word_to_count, path_to_count, _ = _load_histograms(
        word_histogram=word_histogram,
        path_histogram=path_histogram,
        target_histogram=target_histogram,
        word_vocab_size=word_vocab_size,
        path_vocab_size=path_vocab_size,
        target_vocab_size=target_vocab_size,
    )

    output_path = Path(f"{output_name_base}.test.c2v")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with raw_file.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8") as dst:
        for line in src:
            processed = _process_line(
                line=line,
                max_contexts=max_contexts,
                word_to_count=word_to_count,
                path_to_count=path_to_count,
            )
            if processed is None:
                continue
            dst.write(processed + "\n")

    return output_path
