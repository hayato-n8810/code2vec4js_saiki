from __future__ import annotations

from pathlib import Path
from typing import Iterable


def collect_javascript_source_files(source_directory: Path) -> list[Path]:
    """指定ディレクトリ配下から JavaScript ソースファイルを再帰収集する。

    Args:
        source_directory (Path): JavaScript ファイルを再帰探索する基点ディレクトリ。

    Raises:
        None

    Returns:
        list[Path]: 発見した JavaScript ファイル一覧。
    """
    return sorted(path for path in source_directory.rglob("*.js") if path.is_file())


def collect_child_project_directories(parent_directory: Path) -> list[Path]:
    """親ディレクトリ直下の子プロジェクトディレクトリを収集する。

    Args:
        parent_directory (Path): 子プロジェクトを探索する親ディレクトリ。

    Raises:
        None

    Returns:
        list[Path]: 直下の子ディレクトリ一覧。
    """
    return sorted(path for path in parent_directory.iterdir() if path.is_dir())


def assert_input_paths_exist(required_paths: Iterable[Path]) -> None:
    """入力に必要な全パスの存在を検証する。

    Args:
        required_paths (Iterable[Path]): 存在確認対象のパス群。

    Raises:
        FileNotFoundError: いずれかの入力パスが存在しない場合。

    Returns:
        None: 入力パスがすべて存在する場合。
    """
    for path in required_paths:
        if not path.exists():
            raise FileNotFoundError(f"入力が存在しません: {path}")
