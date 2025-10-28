#!/usr/bin/env python3
"""
Preprocess client that uses shared memory histograms
"""

import sys
import os
import pickle
from multiprocessing import shared_memory

def load_histograms_from_shared_memory():
    """
    Load histograms from shared memory instead of disk
    
    Returns:
        tuple: (word_to_count, path_to_count, target_to_count) or (None, None, None)
    """
    shm_name = os.environ.get('HISTOGRAM_SHM_NAME')
    shm_size = os.environ.get('HISTOGRAM_SHM_SIZE')
    
    if not shm_name or not shm_size:
        return None, None, None
    
    try:
        shm_size = int(shm_size)
        
        print(f'[INFO] Loading histograms from shared memory: {shm_name}', file=sys.stderr)
        
        # Attach to existing shared memory
        shm = shared_memory.SharedMemory(name=shm_name)
        
        # Read data
        serialized = bytes(shm.buf[:shm_size])
        histogram_data = pickle.loads(serialized)
        
        word_to_count = histogram_data.get('word_to_count', {})
        path_to_count = histogram_data.get('path_to_count', {})
        target_to_count = histogram_data.get('target_to_count', {})
        
        # Don't close/unlink - shared memory should persist
        # shm.close() is called but NOT shm.unlink()
        shm.close()
        
        print(f'[OK] Loaded from shared memory: {len(word_to_count)} words, '
              f'{len(path_to_count)} paths, {len(target_to_count)} targets', 
              file=sys.stderr)
        
        return word_to_count, path_to_count, target_to_count
        
    except Exception as e:
        print(f'[WARN] Failed to load from shared memory: {e}', file=sys.stderr)
        print(f'[WARN] Falling back to disk-based loading', file=sys.stderr)
        return None, None, None


# This can be imported by preprocess_test.py
__all__ = ['load_histograms_from_shared_memory']
