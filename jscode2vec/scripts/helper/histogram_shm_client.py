from __future__ import annotations

import os
import pickle
import sys
from multiprocessing import shared_memory


def load_histograms_from_shared_memory() -> tuple[dict[str, int], dict[str, int], dict[str, int]] | tuple[None, None, None]:
    """Load histograms from shared memory if available."""
    shm_name = os.environ.get("HISTOGRAM_SHM_NAME")
    shm_size = os.environ.get("HISTOGRAM_SHM_SIZE")

    if not shm_name or not shm_size:
        return None, None, None

    try:
        shm_size_int = int(shm_size)
        print(f"[INFO] Loading histograms from shared memory: {shm_name}", file=sys.stderr)

        shm = shared_memory.SharedMemory(name=shm_name)
        try:
            serialized = bytes(shm.buf[:shm_size_int])
            histogram_data = pickle.loads(serialized)
        finally:
            shm.close()

        word_to_count = histogram_data.get("word_to_count", {})
        path_to_count = histogram_data.get("path_to_count", {})
        target_to_count = histogram_data.get("target_to_count", {})

        print(
            f"[OK] Loaded from shared memory: {len(word_to_count)} words, "
            f"{len(path_to_count)} paths, {len(target_to_count)} targets",
            file=sys.stderr,
        )
        return word_to_count, path_to_count, target_to_count
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Failed to load from shared memory: {exc}", file=sys.stderr)
        print("[WARN] Falling back to disk-based loading", file=sys.stderr)
        return None, None, None


__all__ = ["load_histograms_from_shared_memory"]
