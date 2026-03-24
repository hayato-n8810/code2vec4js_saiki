#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from helper.histogram_cache import preload_histograms


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preload and cache histogram files")
    parser.add_argument("-d", "--dataset", dest="dataset_name", default="js_dataset_min5")
    parser.add_argument("-wvs", "--word_vocab_size", dest="word_vocab_size", type=int, default=1301136)
    parser.add_argument("-pvs", "--path_vocab_size", dest="path_vocab_size", type=int, default=911417)
    parser.add_argument("-tvs", "--target_vocab_size", dest="target_vocab_size", type=int, default=261245)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[2]

    print("=" * 70)
    print("Histogram Preloader")
    print("=" * 70)

    cache_file = preload_histograms(
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
