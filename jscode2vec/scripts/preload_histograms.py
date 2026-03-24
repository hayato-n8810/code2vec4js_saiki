#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from helper.runtime.histogram_cache_repository import create_or_update_histogram_cache


def parse_preload_histogram_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """ヒストグラム事前キャッシュ作成コマンドの CLI 引数を解析する。

    Args:
        argv (list[str] | None): 解析対象のコマンドライン引数。

    Raises:
        None

    Returns:
        argparse.Namespace: 解析済み引数。
    """
    parser = argparse.ArgumentParser(description="Preload and cache histogram files")
    parser.add_argument("-d", "--dataset", dest="dataset_name", default="js_dataset_min5")
    parser.add_argument("-wvs", "--word_vocab_size", dest="word_vocab_size", type=int, default=1301136)
    parser.add_argument("-pvs", "--path_vocab_size", dest="path_vocab_size", type=int, default=911417)
    parser.add_argument("-tvs", "--target_vocab_size", dest="target_vocab_size", type=int, default=261245)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """指定データセットのヒストグラムキャッシュ生成処理を実行する。

    Args:
        argv (list[str] | None): 実行引数。

    Raises:
        None

    Returns:
        int: 正常終了時は 0。
    """
    args = parse_preload_histogram_arguments(argv)
    project_root = Path(__file__).resolve().parents[2]

    print("=" * 70)
    print("Histogram Preloader")
    print("=" * 70)

    cache_file = create_or_update_histogram_cache(
        dataset_name=args.dataset_name,
        word_vocab_size=args.word_vocab_size,
        path_vocab_size=args.path_vocab_size,
        target_vocab_size=args.target_vocab_size,
        project_root=project_root,
    )

    size_mb = cache_file.stat().st_size / (1024 * 1024)
    print(f"[SUCCESS] Histogram cache created: {cache_file}")
    print(f"[INFO] Cache size: {size_mb:.2f} MB")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Failed to preload histograms: {exc}", file=sys.stderr)
        raise
