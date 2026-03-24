from __future__ import annotations

import fcntl
import random
import sys
from contextlib import contextmanager
from pathlib import Path

from ..runtime.histogram_cache_repository import load_histograms_from_cache_file
from ..runtime.histogram_shared_memory_loader import load_histograms_from_configured_shared_memory

# scripts 経由実行時でもリポジトリルートの common.py を解決できるようにする
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from common import common  # noqa: E402


@contextmanager
def shared_histogram_cache_lock(lock_file_path: Path):
    """ヒストグラムキャッシュ読込時の共有ロックを提供する。

    Args:
        lock_file_path (Path): 共有ロック対象ファイルパス。

    Raises:
        None

    Returns:
        None: コンテキストマネージャとして共有ロックを提供する。
    """
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


def _load_histograms_from_locked_cache_file(
    cache_file: Path,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]] | None:
    """ロック下でヒストグラムキャッシュを読み込む。

    Args:
        cache_file (Path): キャッシュファイルパス。

    Raises:
        None

    Returns:
        tuple[dict[str, int], dict[str, int], dict[str, int]] | None:
            読み込み成功時はヒストグラム辞書、失敗時は None。
    """
    if not cache_file.exists():
        return None

    lock_file = Path(f"{cache_file}.lock")
    with shared_histogram_cache_lock(lock_file):
        return load_histograms_from_cache_file(cache_file)


def _is_context_fully_in_vocabulary(
    context_parts: list[str],
    word_to_count: dict[str, int],
    path_to_count: dict[str, int],
) -> bool:
    """context の3要素がすべて語彙内か判定する。

    Args:
        context_parts (list[str]): context をカンマ分割した 3 要素。
        word_to_count (dict[str, int]): 単語ヒストグラム辞書。
        path_to_count (dict[str, int]): パスヒストグラム辞書。

    Raises:
        None

    Returns:
        bool: word,path,word の 3 要素が全て語彙内に存在する場合 True。
    """
    return (
        len(context_parts) == 3
        and context_parts[0] in word_to_count
        and context_parts[1] in path_to_count
        and context_parts[2] in word_to_count
    )


def _is_context_partially_in_vocabulary(
    context_parts: list[str],
    word_to_count: dict[str, int],
    path_to_count: dict[str, int],
) -> bool:
    """context の3要素のうち少なくとも1要素が語彙内か判定する。

    Args:
        context_parts (list[str]): context をカンマ分割した 3 要素。
        word_to_count (dict[str, int]): 単語ヒストグラム辞書。
        path_to_count (dict[str, int]): パスヒストグラム辞書。

    Raises:
        None

    Returns:
        bool: 3 要素のうち少なくとも 1 要素が語彙内に存在する場合 True。
    """
    return (
        len(context_parts) == 3
        and (
            context_parts[0] in word_to_count
            or context_parts[1] in path_to_count
            or context_parts[2] in word_to_count
        )
    )


def _load_histogram_dictionaries(
    word_histogram: Path,
    path_histogram: Path,
    target_histogram: Path,
    word_vocab_size: int,
    path_vocab_size: int,
    target_vocab_size: int,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """共有メモリ・キャッシュ・生ファイルの順でヒストグラム辞書を取得する。

    Args:
        word_histogram (Path): 単語ヒストグラムファイル。
        path_histogram (Path): パスヒストグラムファイル。
        target_histogram (Path): ターゲットヒストグラムファイル。
        word_vocab_size (int): 単語語彙サイズ。
        path_vocab_size (int): パス語彙サイズ。
        target_vocab_size (int): ターゲット語彙サイズ。

    Raises:
        None

    Returns:
        tuple[dict[str, int], dict[str, int], dict[str, int]]: word/path/target のヒストグラム辞書。
    """
    word_to_count, path_to_count, target_to_count = load_histograms_from_configured_shared_memory()

    if word_to_count is not None and path_to_count is not None and target_to_count is not None:
        return word_to_count, path_to_count, target_to_count

    cache_file = word_histogram.parent / "histogram_cache.pkl"
    try:
        cached = _load_histograms_from_locked_cache_file(cache_file)
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


def _transform_single_raw_line(
    line: str,
    max_contexts: int,
    word_to_count: dict[str, int],
    path_to_count: dict[str, int],
) -> str | None:
    """抽出済み raw 1 行を c2v 形式に整形し必要に応じて context を間引く。

    Args:
        line (str): 抽出済み raw 1 行。
        max_contexts (int): 許容する最大 context 数。
        word_to_count (dict[str, int]): 単語ヒストグラム辞書。
        path_to_count (dict[str, int]): パスヒストグラム辞書。

    Raises:
        None

    Returns:
        str | None: 変換済み c2v 1 行。無効行は None。
    """
    parts = line.rstrip("\n").split(" ")
    if len(parts) < 2:
        return None

    target_name = parts[0]
    contexts = parts[1:]

    if len(contexts) > max_contexts:
        context_parts = [context.split(",") for context in contexts]
        full_found_contexts = [
            context
            for index, context in enumerate(contexts)
            if _is_context_fully_in_vocabulary(context_parts[index], word_to_count, path_to_count)
        ]
        partial_found_contexts = [
            context
            for index, context in enumerate(contexts)
            if _is_context_partially_in_vocabulary(context_parts[index], word_to_count, path_to_count)
            and not _is_context_fully_in_vocabulary(context_parts[index], word_to_count, path_to_count)
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


def preprocess_raw_contexts_to_c2v_test_data(
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
    """raw context ファイルを code2vec 推論用の .test.c2v へ変換する。

    Args:
        raw_file (Path): 抽出 raw ファイル。
        output_name_base (Path): 出力ベース名。
        max_contexts (int): 許容する最大 context 数。
        word_vocab_size (int): 単語語彙サイズ。
        path_vocab_size (int): パス語彙サイズ。
        target_vocab_size (int): ターゲット語彙サイズ。
        word_histogram (Path): 単語ヒストグラムファイル。
        path_histogram (Path): パスヒストグラムファイル。
        target_histogram (Path): ターゲットヒストグラムファイル。

    Raises:
        FileNotFoundError: 入力 raw またはヒストグラムファイルが存在しない場合。

    Returns:
        Path: 生成された .test.c2v ファイルパス。
    """
    if not raw_file.exists():
        raise FileNotFoundError(f"テストデータが存在しません: {raw_file}")

    if not word_histogram.exists() or not path_histogram.exists() or not target_histogram.exists():
        raise FileNotFoundError("ヒストグラムファイルが存在しません")

    word_to_count, path_to_count, _ = _load_histogram_dictionaries(
        word_histogram=word_histogram,
        path_histogram=path_histogram,
        target_histogram=target_histogram,
        word_vocab_size=word_vocab_size,
        path_vocab_size=path_vocab_size,
        target_vocab_size=target_vocab_size,
    )

    output_path = Path(f"{output_name_base}.test.c2v")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with raw_file.open("r", encoding="utf-8") as source_stream, output_path.open("w", encoding="utf-8") as output_stream:
        for line in source_stream:
            transformed_line = _transform_single_raw_line(
                line=line,
                max_contexts=max_contexts,
                word_to_count=word_to_count,
                path_to_count=path_to_count,
            )
            if transformed_line is None:
                continue
            output_stream.write(transformed_line + "\n")

    return output_path
