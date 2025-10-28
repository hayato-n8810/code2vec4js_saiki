#!/usr/bin/env python3
"""
Shared Memory Histogram Server
===============================

Revolutionary approach to eliminate histogram file contention:
- Load histograms ONCE into shared memory
- All worker processes read from shared memory (zero disk I/O)
- Supports thousands of parallel workers without contention

Architecture:
    Manager Process (this script)
        ↓ Load histograms once
    Shared Memory (mmap)
        ↓ Read-only access
    Worker 1, Worker 2, ..., Worker N

Usage:
    # Start server (run BEFORE parallel processing)
    python3 histogram_server.py --dataset js_dataset_min5 start
    
    # Workers access via environment variable: HISTOGRAM_SHM_NAME
    # Automatic cleanup on server stop
    
    # Stop server (after processing complete)
    python3 histogram_server.py stop
"""

import sys
import os
import pickle
import mmap
import argparse
from multiprocessing import shared_memory
import signal
import time
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, '..'))

import common.common

class HistogramServer:
    def __init__(self, dataset_name, word_vocab_size, path_vocab_size, target_vocab_size):
        self.dataset_name = dataset_name
        self.word_vocab_size = word_vocab_size
        self.path_vocab_size = path_vocab_size
        self.target_vocab_size = target_vocab_size
        self.shm_name = f"code2vec_histograms_{dataset_name}"
        self.metadata_file = f"/tmp/{self.shm_name}_metadata.json"
        
    def load_histograms(self):
        """Load histograms from cache or raw files"""
        data_dir = f"/code2vec/data/{self.dataset_name}"
        cache_file = os.path.join(data_dir, "histogram_cache.pkl")
        
        print(f"[INFO] Loading histograms for dataset: {self.dataset_name}")
        
        # Try cache first
        if os.path.exists(cache_file):
            print(f"[INFO] Loading from cache: {cache_file}")
            try:
                with open(cache_file, 'rb') as f:
                    cache_data = pickle.load(f)
                    word_to_count = cache_data.get('word_to_count', {})
                    path_to_count = cache_data.get('path_to_count', {})
                    target_to_count = cache_data.get('target_to_count', {})
                    
                    if word_to_count and path_to_count and target_to_count:
                        print(f"[OK] Loaded from cache: {len(word_to_count)} words, "
                              f"{len(path_to_count)} paths, {len(target_to_count)} targets")
                        return word_to_count, path_to_count, target_to_count
            except Exception as e:
                print(f"[WARN] Cache load failed: {e}, loading from raw files")
        
        # Load from raw files
        print(f"[INFO] Loading from raw histogram files")
        word_histo = os.path.join(data_dir, f"{self.dataset_name}.histo.ori.c2v")
        path_histo = os.path.join(data_dir, f"{self.dataset_name}.histo.path.c2v")
        target_histo = os.path.join(data_dir, f"{self.dataset_name}.histo.tgt.c2v")
        
        for f in [word_histo, path_histo, target_histo]:
            if not os.path.exists(f):
                raise FileNotFoundError(f"Histogram file not found: {f}")
        
        _, _, _, word_to_count = common.common.load_vocab_from_histogram(
            word_histo, start_from=1, max_size=self.word_vocab_size, return_counts=True
        )
        _, _, _, path_to_count = common.common.load_vocab_from_histogram(
            path_histo, start_from=1, max_size=self.path_vocab_size, return_counts=True
        )
        _, _, _, target_to_count = common.common.load_vocab_from_histogram(
            target_histo, start_from=1, max_size=self.target_vocab_size, return_counts=True
        )
        
        print(f"[OK] Loaded raw histograms: {len(word_to_count)} words, "
              f"{len(path_to_count)} paths, {len(target_to_count)} targets")
        
        return word_to_count, path_to_count, target_to_count
    
    def start_server(self):
        """Start shared memory server"""
        print(f"\n{'='*60}")
        print(f"  Histogram Shared Memory Server")
        print(f"{'='*60}\n")
        
        # Load histograms
        word_to_count, path_to_count, target_to_count = self.load_histograms()
        
        # Serialize data
        print("[INFO] Serializing histograms to pickle...")
        histogram_data = {
            'word_to_count': word_to_count,
            'path_to_count': path_to_count,
            'target_to_count': target_to_count,
        }
        serialized = pickle.dumps(histogram_data)
        data_size = len(serialized)
        
        print(f"[INFO] Serialized size: {data_size / 1024 / 1024:.2f} MB")
        
        # Create shared memory
        print(f"[INFO] Creating shared memory: {self.shm_name}")
        try:
            # Try to cleanup old shared memory first
            try:
                old_shm = shared_memory.SharedMemory(name=self.shm_name)
                old_shm.close()
                old_shm.unlink()
                print("[INFO] Cleaned up old shared memory")
            except:
                pass
            
            shm = shared_memory.SharedMemory(name=self.shm_name, create=True, size=data_size)
            
            # Write data to shared memory
            print("[INFO] Writing data to shared memory...")
            shm.buf[:data_size] = serialized
            
            # Save metadata
            metadata = {
                'shm_name': self.shm_name,
                'size': data_size,
                'dataset': self.dataset_name,
                'pid': os.getpid(),
                'timestamp': time.time(),
            }
            
            with open(self.metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"\n{'='*60}")
            print(f"  ✅ Shared Memory Server Started Successfully!")
            print(f"{'='*60}")
            print(f"  Shared Memory Name: {self.shm_name}")
            print(f"  Memory Size: {data_size / 1024 / 1024:.2f} MB")
            print(f"  Metadata File: {self.metadata_file}")
            print(f"  PID: {os.getpid()}")
            print(f"{'='*60}\n")
            
            print("[INFO] Export this environment variable for workers:")
            print(f"      export HISTOGRAM_SHM_NAME={self.shm_name}")
            print(f"      export HISTOGRAM_SHM_SIZE={data_size}")
            print("")
            print("[INFO] Server is running. Press Ctrl+C to stop...")
            print("")
            
            # Keep server running
            def signal_handler(sig, frame):
                print("\n[INFO] Shutting down server...")
                shm.close()
                shm.unlink()
                if os.path.exists(self.metadata_file):
                    os.remove(self.metadata_file)
                print("[OK] Server stopped")
                sys.exit(0)
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            # Keep process alive
            while True:
                time.sleep(1)
                
        except Exception as e:
            print(f"[ERROR] Failed to start server: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def stop_server(self):
        """Stop shared memory server"""
        print(f"[INFO] Stopping histogram server: {self.shm_name}")
        
        # Read metadata
        if os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'r') as f:
                metadata = json.load(f)
            
            pid = metadata.get('pid')
            if pid:
                print(f"[INFO] Sending SIGTERM to PID {pid}")
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(1)
                except ProcessLookupError:
                    print(f"[WARN] Process {pid} not found (already stopped?)")
        
        # Cleanup shared memory
        try:
            shm = shared_memory.SharedMemory(name=self.shm_name)
            shm.close()
            shm.unlink()
            print(f"[OK] Shared memory cleaned up")
        except FileNotFoundError:
            print(f"[WARN] Shared memory not found (already cleaned?)")
        except Exception as e:
            print(f"[WARN] Failed to cleanup: {e}")
        
        # Remove metadata
        if os.path.exists(self.metadata_file):
            os.remove(self.metadata_file)
        
        print("[OK] Server stopped")
    
    def status(self):
        """Check server status"""
        if os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'r') as f:
                metadata = json.load(f)
            
            print(f"[INFO] Server Status: RUNNING")
            print(f"  Shared Memory: {metadata['shm_name']}")
            print(f"  Size: {metadata['size'] / 1024 / 1024:.2f} MB")
            print(f"  Dataset: {metadata['dataset']}")
            print(f"  PID: {metadata['pid']}")
            print(f"  Started: {time.ctime(metadata['timestamp'])}")
            
            # Check if process is alive
            try:
                os.kill(metadata['pid'], 0)
                print(f"  Process: ALIVE")
            except:
                print(f"  Process: DEAD (stale metadata?)")
        else:
            print(f"[INFO] Server Status: NOT RUNNING")


def main():
    parser = argparse.ArgumentParser(description='Histogram Shared Memory Server')
    parser.add_argument('command', choices=['start', 'stop', 'status'],
                       help='Server command')
    parser.add_argument('--dataset', default='js_dataset_min5',
                       help='Dataset name')
    parser.add_argument('--word_vocab_size', type=int, default=1301136,
                       help='Word vocabulary size')
    parser.add_argument('--path_vocab_size', type=int, default=911417,
                       help='Path vocabulary size')
    parser.add_argument('--target_vocab_size', type=int, default=261245,
                       help='Target vocabulary size')
    
    args = parser.parse_args()
    
    server = HistogramServer(
        args.dataset,
        args.word_vocab_size,
        args.path_vocab_size,
        args.target_vocab_size
    )
    
    if args.command == 'start':
        server.start_server()
    elif args.command == 'stop':
        server.stop_server()
    elif args.command == 'status':
        server.status()


if __name__ == '__main__':
    main()
