#!/usr/bin/env python3
"""
ヒストグラムの事前ロードとキャッシュ化スクリプト

並列実行時の問題を解決するため、ヒストグラムファイルを1回だけ読み込み、
pickleファイルとして保存します。これにより、各ワーカープロセスは
高速にヒストグラムをロードできます。

Usage:
    python3 preload_histograms.py [dataset_name]
    
Example:
    python3 preload_histograms.py js_dataset_min5
"""

import sys
import os
import pickle
import time
from argparse import ArgumentParser
import common

def preload_histograms(dataset_name, word_vocab_size, path_vocab_size, target_vocab_size):
    """
    ヒストグラムを読み込み、pickleファイルとして保存
    """
    histo_dir = f"data/{dataset_name}"
    word_histo = f"{histo_dir}/{dataset_name}.histo.ori.c2v"
    path_histo = f"{histo_dir}/{dataset_name}.histo.path.c2v"
    target_histo = f"{histo_dir}/{dataset_name}.histo.tgt.c2v"
    cache_file = f"{histo_dir}/histogram_cache.pkl"
    
    # ファイルの存在確認
    for path in [word_histo, path_histo, target_histo]:
        if not os.path.exists(path):
            print(f"[ERROR] Histogram file not found: {path}")
            sys.exit(1)
    
    print(f"[INFO] Loading histograms from {histo_dir}")
    print(f"       Word vocab size: {word_vocab_size}")
    print(f"       Path vocab size: {path_vocab_size}")
    print(f"       Target vocab size: {target_vocab_size}")
    
    # Word histogram
    print(f"\n[1/3] Loading word histogram: {word_histo}")
    start_time = time.time()
    word_histogram_data = common.common.load_vocab_from_histogram(
        word_histo,
        start_from=1,
        max_size=word_vocab_size,
        return_counts=True
    )
    _, _, _, word_to_count = word_histogram_data
    elapsed = time.time() - start_time
    print(f"      Loaded {len(word_to_count)} words in {elapsed:.2f}s")
    
    # Path histogram
    print(f"\n[2/3] Loading path histogram: {path_histo}")
    start_time = time.time()
    _, _, _, path_to_count = common.common.load_vocab_from_histogram(
        path_histo,
        start_from=1,
        max_size=path_vocab_size,
        return_counts=True
    )
    elapsed = time.time() - start_time
    print(f"      Loaded {len(path_to_count)} paths in {elapsed:.2f}s")
    
    # Target histogram
    print(f"\n[3/3] Loading target histogram: {target_histo}")
    start_time = time.time()
    _, _, _, target_to_count = common.common.load_vocab_from_histogram(
        target_histo,
        start_from=1,
        max_size=target_vocab_size,
        return_counts=True
    )
    elapsed = time.time() - start_time
    print(f"      Loaded {len(target_to_count)} targets in {elapsed:.2f}s")
    
    # Pickleファイルとして保存
    print(f"\n[INFO] Saving histogram cache to: {cache_file}")
    start_time = time.time()
    cache_data = {
        'word_to_count': word_to_count,
        'path_to_count': path_to_count,
        'target_to_count': target_to_count,
        'word_vocab_size': word_vocab_size,
        'path_vocab_size': path_vocab_size,
        'target_vocab_size': target_vocab_size,
        'dataset_name': dataset_name
    }
    
    with open(cache_file, 'wb') as f:
        pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    elapsed = time.time() - start_time
    cache_size_mb = os.path.getsize(cache_file) / (1024 * 1024)
    print(f"      Cache saved in {elapsed:.2f}s ({cache_size_mb:.2f} MB)")
    print(f"\n[SUCCESS] Histogram cache created: {cache_file}")
    print(f"\n[INFO] Workers can now use this cache for fast loading")
    print(f"       Expected speedup: 10-50x faster than reading raw histograms")

if __name__ == '__main__':
    parser = ArgumentParser(description="Preload and cache histogram files")
    parser.add_argument("-d", "--dataset", dest="dataset_name", 
                        default="js_dataset_min5",
                        help="Dataset name (default: js_dataset_min5)")
    parser.add_argument("-wvs", "--word_vocab_size", dest="word_vocab_size",
                        type=int, default=1301136,
                        help="Max number of words (default: 1301136)")
    parser.add_argument("-pvs", "--path_vocab_size", dest="path_vocab_size",
                        type=int, default=911417,
                        help="Max number of paths (default: 911417)")
    parser.add_argument("-tvs", "--target_vocab_size", dest="target_vocab_size",
                        type=int, default=261245,
                        help="Max number of targets (default: 261245)")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Histogram Preloader")
    print("=" * 70)
    
    try:
        preload_histograms(
            args.dataset_name,
            args.word_vocab_size,
            args.path_vocab_size,
            args.target_vocab_size
        )
    except Exception as e:
        print(f"\n[ERROR] Failed to preload histograms: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("=" * 70)
