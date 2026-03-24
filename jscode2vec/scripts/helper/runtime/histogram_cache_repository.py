from __future__ import annotations

import fcntl
import os
import pickle
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from common import common  # noqa: E402


def resolve_histogram_dataset_directory(dataset_name: str, project_root: Path | None = None) -> Path:
    """データセット名からヒストグラム格納ディレクトリを解決する。

    Args:
        dataset_name (str): ヒストグラムのデータセット名。
        project_root (Path | None): ローカル解決時のプロジェクトルート。

    Raises:
        None

    Returns:
        Path: データセットディレクトリ。
    """
    docker_dir = Path("/code2vec/data") / dataset_name
    if docker_dir.exists():
        return docker_dir

    base = project_root or _REPO_ROOT
    return base / "data" / dataset_name


@contextmanager
def exclusive_histogram_cache_lock(lock_file_path: Path):
    """ヒストグラムキャッシュ更新時の排他ロックを提供する。

    Args:
        lock_file_path (Path): 排他ロックに利用するロックファイルパス。

    Raises:
        None

    Returns:
        None: コンテキストマネージャとしてロックを提供する。
    """
    lock_fd = None
    try:
        lock_fd = lock_file_path.open("w", encoding="utf-8")
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            finally:
                lock_fd.close()


def load_histograms_from_raw_files(
    dataset_dir: Path,
    dataset_name: str,
    word_vocab_size: int,
    path_vocab_size: int,
    target_vocab_size: int,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """生ヒストグラムファイルを読み込み語彙頻度辞書へ変換する。

    Args:
        dataset_dir (Path): ヒストグラムファイルを保持するディレクトリ。
        dataset_name (str): データセット名。
        word_vocab_size (int): 単語語彙サイズ。
        path_vocab_size (int): パス語彙サイズ。
        target_vocab_size (int): ターゲット語彙サイズ。

    Raises:
        FileNotFoundError: 必須ヒストグラムファイルが不足している場合。

    Returns:
        tuple[dict[str, int], dict[str, int], dict[str, int]]:
            word/path/target のヒストグラム辞書。
    """
    word_histo = dataset_dir / f"{dataset_name}.histo.ori.c2v"
    path_histo = dataset_dir / f"{dataset_name}.histo.path.c2v"
    target_histo = dataset_dir / f"{dataset_name}.histo.tgt.c2v"

    for histogram_file in [word_histo, path_histo, target_histo]:
        if not histogram_file.exists():
            raise FileNotFoundError(f"Histogram file not found: {histogram_file}")

    _, _, _, word_to_count = common.load_vocab_from_histogram(
        str(word_histo),
        start_from=1,
        max_size=word_vocab_size,
        return_counts=True,
    )
    _, _, _, path_to_count = common.load_vocab_from_histogram(
        str(path_histo),
        start_from=1,
        max_size=path_vocab_size,
        return_counts=True,
    )
    _, _, _, target_to_count = common.load_vocab_from_histogram(
        str(target_histo),
        start_from=1,
        max_size=target_vocab_size,
        return_counts=True,
    )

    return word_to_count, path_to_count, target_to_count


def load_histograms_from_cache_file(
    cache_file: Path,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]] | None:
    """ヒストグラムキャッシュファイルから語彙頻度辞書を読み込む。

    Args:
        cache_file (Path): キャッシュファイルパス。

    Raises:
        None

    Returns:
        tuple[dict[str, int], dict[str, int], dict[str, int]] | None:
            キャッシュ読み込み成功時はヒストグラム辞書、失敗時は None。
    """
    if not cache_file.exists():
        return None

    with cache_file.open("rb") as cache_stream:
        cache_data = pickle.load(cache_stream)

    word_to_count = cache_data.get("word_to_count", {})
    path_to_count = cache_data.get("path_to_count", {})
    target_to_count = cache_data.get("target_to_count", {})

    if not word_to_count or not path_to_count or not target_to_count:
        return None

    return word_to_count, path_to_count, target_to_count


def create_or_update_histogram_cache(
    dataset_name: str,
    word_vocab_size: int,
    path_vocab_size: int,
    target_vocab_size: int,
    project_root: Path | None = None,
) -> Path:
    """生ヒストグラムからキャッシュを生成または更新する。

    Args:
        dataset_name (str): データセット名。
        word_vocab_size (int): 単語語彙サイズ。
        path_vocab_size (int): パス語彙サイズ。
        target_vocab_size (int): ターゲット語彙サイズ。
        project_root (Path | None): ローカル解決時のプロジェクトルート。

    Raises:
        FileNotFoundError: データセットディレクトリが存在しない場合。

    Returns:
        Path: 生成したキャッシュファイルパス。
    """
    dataset_dir = resolve_histogram_dataset_directory(dataset_name=dataset_name, project_root=project_root)
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")

    word_to_count, path_to_count, target_to_count = load_histograms_from_raw_files(
        dataset_dir=dataset_dir,
        dataset_name=dataset_name,
        word_vocab_size=word_vocab_size,
        path_vocab_size=path_vocab_size,
        target_vocab_size=target_vocab_size,
    )

    cache_file = dataset_dir / "histogram_cache.pkl"
    lock_file = dataset_dir / "histogram_cache.pkl.lock"

    cache_data = {
        "word_to_count": word_to_count,
        "path_to_count": path_to_count,
        "target_to_count": target_to_count,
        "word_vocab_size": word_vocab_size,
        "path_vocab_size": path_vocab_size,
        "target_vocab_size": target_vocab_size,
        "dataset_name": dataset_name,
        "created_at": time.time(),
    }

    with exclusive_histogram_cache_lock(lock_file):
        fd, temp_file = tempfile.mkstemp(suffix=".pkl", dir=str(dataset_dir))
        temp_path = Path(temp_file)
        try:
            with os.fdopen(fd, "wb") as stream:
                pickle.dump(cache_data, stream, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(temp_path, cache_file)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    return cache_file
