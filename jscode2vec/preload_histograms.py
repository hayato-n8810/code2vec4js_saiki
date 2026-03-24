#!/usr/bin/env python3
"""
ヒストグラムの事前ロードとキャッシュ化スクリプト

並列実行時の問題を解決するため、ヒストグラムファイルを1回だけ読み込み、
pickleファイルとして保存します。これにより、各ワーカープロセスは
高速にヒストグラムをロードできます。

Thread-safe: Uses exclusive file locking (fcntl.LOCK_EX) to prevent concurrent writes.

Usage:
    python3 preload_histograms.py [dataset_name]
    
Example:
    python3 preload_histograms.py js_dataset_min5
"""

import sys
import os

# Add parent directory to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pickle
import time
import fcntl
import tempfile
from argparse import ArgumentParser
from contextlib import contextmanager
import common

@contextmanager
def exclusive_lock(lock_file_path):
    """
    Exclusive file lock context manager for safe cache writing.
    
    Prevents multiple processes from writing to the cache simultaneously.
    Also blocks shared lock readers during cache generation.
    
    Args:
        lock_file_path: Path to the lock file
    """
    lock_fd = None
    try:
        # Create lock file if it doesn't exist
        lock_fd = open(lock_file_path, 'w')
        
        # Acquire exclusive lock (wait if necessary)
        print(f'[INFO] Acquiring exclusive lock for cache generation...', file=sys.stderr)
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        print(f'[INFO] Exclusive lock acquired', file=sys.stderr)
        
        yield lock_fd
        
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
                print(f'[INFO] Exclusive lock released', file=sys.stderr)
            except:
                pass

def preload_histograms(dataset_name, word_vocab_size, path_vocab_size, target_vocab_size):
    """
    ヒストグラムを読み込み、pickleファイルとして保存
    """
    histo_dir = f"/code2vec/data/{dataset_name}"
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
    
    # Pickleファイルとして保存（アトミック書き込み + 排他ロック）
    print(f"\n[INFO] Saving histogram cache to: {cache_file}")
    lock_file = cache_file + '.lock'
    
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
    
    # Use exclusive lock + atomic write for maximum safety
    cache_dir = os.path.dirname(cache_file)
    with exclusive_lock(lock_file):
        # Write to temporary file first
        temp_fd, temp_path = tempfile.mkstemp(suffix='.pkl', dir=cache_dir)
        try:
            with os.fdopen(temp_fd, 'wb') as f:
                pickle.dump(cache_data, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            # Atomic rename
            os.replace(temp_path, cache_file)
            
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    elapsed = time.time() - start_time
    cache_size_mb = os.path.getsize(cache_file) / (1024 * 1024)
    print(f"      Cache saved in {elapsed:.2f}s ({cache_size_mb:.2f} MB)")
    print(f"\n[SUCCESS] Histogram cache created: {cache_file}")
    print(f"\n[INFO] Workers can now use this cache for fast loading")
    print(f"       Expected speedup: 10-50x faster than reading raw histograms")
    print(f"       Thread-safe: Concurrent reads are safe with shared locks")

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
