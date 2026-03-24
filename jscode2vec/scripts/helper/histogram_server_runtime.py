from __future__ import annotations

import argparse
import json
import os
import pickle
import signal
import sys
import time
from multiprocessing import shared_memory
from pathlib import Path

from .histogram_cache import load_histograms_from_cache, load_histograms_from_raw, resolve_dataset_dir


class HistogramServer:
    def __init__(self, dataset_name: str, word_vocab_size: int, path_vocab_size: int, target_vocab_size: int):
        self.dataset_name = dataset_name
        self.word_vocab_size = word_vocab_size
        self.path_vocab_size = path_vocab_size
        self.target_vocab_size = target_vocab_size
        self.shm_name = f"code2vec_histograms_{dataset_name}"
        self.metadata_file = Path(f"/tmp/{self.shm_name}_metadata.json")

    def load_histograms(self) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
        dataset_dir = resolve_dataset_dir(dataset_name=self.dataset_name)
        cache_file = dataset_dir / "histogram_cache.pkl"

        print(f"[INFO] Loading histograms for dataset: {self.dataset_name}")

        if cache_file.exists():
            print(f"[INFO] Loading from cache: {cache_file}")
            try:
                cached = load_histograms_from_cache(cache_file)
                if cached is not None:
                    word_to_count, path_to_count, target_to_count = cached
                    print(
                        f"[OK] Loaded from cache: {len(word_to_count)} words, "
                        f"{len(path_to_count)} paths, {len(target_to_count)} targets"
                    )
                    return cached
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] Cache load failed: {exc}, loading from raw files")

        print("[INFO] Loading from raw histogram files")
        word_to_count, path_to_count, target_to_count = load_histograms_from_raw(
            dataset_dir=dataset_dir,
            dataset_name=self.dataset_name,
            word_vocab_size=self.word_vocab_size,
            path_vocab_size=self.path_vocab_size,
            target_vocab_size=self.target_vocab_size,
        )
        print(
            f"[OK] Loaded raw histograms: {len(word_to_count)} words, "
            f"{len(path_to_count)} paths, {len(target_to_count)} targets"
        )
        return word_to_count, path_to_count, target_to_count

    def start_server(self) -> None:
        print(f"\n{'=' * 60}")
        print("  Histogram Shared Memory Server")
        print(f"{'=' * 60}\n")

        word_to_count, path_to_count, target_to_count = self.load_histograms()
        histogram_data = {
            "word_to_count": word_to_count,
            "path_to_count": path_to_count,
            "target_to_count": target_to_count,
        }
        serialized = pickle.dumps(histogram_data)
        data_size = len(serialized)

        print(f"[INFO] Serialized size: {data_size / 1024 / 1024:.2f} MB")
        print(f"[INFO] Creating shared memory: {self.shm_name}")

        try:
            try:
                old_shm = shared_memory.SharedMemory(name=self.shm_name)
                old_shm.close()
                old_shm.unlink()
                print("[INFO] Cleaned up old shared memory")
            except FileNotFoundError:
                pass
            except Exception:
                pass

            shm = shared_memory.SharedMemory(name=self.shm_name, create=True, size=data_size)
            shm.buf[:data_size] = serialized

            metadata = {
                "shm_name": self.shm_name,
                "size": data_size,
                "dataset": self.dataset_name,
                "pid": os.getpid(),
                "timestamp": time.time(),
            }
            self.metadata_file.write_text(json.dumps(metadata, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

            print(f"\n{'=' * 60}")
            print("  Shared Memory Server Started Successfully")
            print(f"{'=' * 60}")
            print(f"  Shared Memory Name: {self.shm_name}")
            print(f"  Memory Size: {data_size / 1024 / 1024:.2f} MB")
            print(f"  Metadata File: {self.metadata_file}")
            print(f"  PID: {os.getpid()}")
            print(f"{'=' * 60}\n")
            print(f"[INFO] export HISTOGRAM_SHM_NAME={self.shm_name}")
            print(f"[INFO] export HISTOGRAM_SHM_SIZE={data_size}")

            def signal_handler(sig, frame):
                _ = sig, frame
                print("\n[INFO] Shutting down server...")
                try:
                    shm.close()
                finally:
                    try:
                        shm.unlink()
                    except Exception:
                        pass
                if self.metadata_file.exists():
                    self.metadata_file.unlink()
                print("[OK] Server stopped")
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            while True:
                time.sleep(1)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] Failed to start server: {exc}")
            raise

    def stop_server(self) -> None:
        print(f"[INFO] Stopping histogram server: {self.shm_name}")

        if self.metadata_file.exists():
            metadata = json.loads(self.metadata_file.read_text(encoding="utf-8"))
            pid = metadata.get("pid")
            if pid:
                print(f"[INFO] Sending SIGTERM to PID {pid}")
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(1)
                except ProcessLookupError:
                    print(f"[WARN] Process {pid} not found (already stopped?)")

        try:
            shm = shared_memory.SharedMemory(name=self.shm_name)
            shm.close()
            shm.unlink()
            print("[OK] Shared memory cleaned up")
        except FileNotFoundError:
            print("[WARN] Shared memory not found (already cleaned?)")
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Failed to cleanup: {exc}")

        if self.metadata_file.exists():
            self.metadata_file.unlink()

        print("[OK] Server stopped")

    def status(self) -> None:
        if not self.metadata_file.exists():
            print("[INFO] Server Status: NOT RUNNING")
            return

        metadata = json.loads(self.metadata_file.read_text(encoding="utf-8"))
        print("[INFO] Server Status: RUNNING")
        print(f"  Shared Memory: {metadata['shm_name']}")
        print(f"  Size: {metadata['size'] / 1024 / 1024:.2f} MB")
        print(f"  Dataset: {metadata['dataset']}")
        print(f"  PID: {metadata['pid']}")
        print(f"  Started: {time.ctime(metadata['timestamp'])}")

        try:
            os.kill(metadata["pid"], 0)
            print("  Process: ALIVE")
        except Exception:
            print("  Process: DEAD (stale metadata?)")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Histogram Shared Memory Server")
    parser.add_argument("command", choices=["start", "stop", "status"], help="Server command")
    parser.add_argument("--dataset", default="js_dataset_min5", help="Dataset name")
    parser.add_argument("--word_vocab_size", type=int, default=1301136, help="Word vocabulary size")
    parser.add_argument("--path_vocab_size", type=int, default=911417, help="Path vocabulary size")
    parser.add_argument("--target_vocab_size", type=int, default=261245, help="Target vocabulary size")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    server = HistogramServer(
        dataset_name=args.dataset,
        word_vocab_size=args.word_vocab_size,
        path_vocab_size=args.path_vocab_size,
        target_vocab_size=args.target_vocab_size,
    )

    if args.command == "start":
        server.start_server()
    elif args.command == "stop":
        server.stop_server()
    else:
        server.status()

    return 0
