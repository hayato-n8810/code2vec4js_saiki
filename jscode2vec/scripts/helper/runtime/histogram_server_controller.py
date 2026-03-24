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

from .histogram_cache_repository import (
    load_histograms_from_cache_file,
    load_histograms_from_raw_files,
    resolve_histogram_dataset_directory,
)


class HistogramSharedMemoryServerController:
    """ヒストグラム共有メモリサーバーの運用処理を統括する。

    Args:
        dataset_name (str): 対象データセット名。
        word_vocab_size (int): 単語語彙サイズ。
        path_vocab_size (int): パス語彙サイズ。
        target_vocab_size (int): ターゲット語彙サイズ。

    Raises:
        None

    Returns:
        HistogramSharedMemoryServerController: サーバー制御インスタンス。
    """

    def __init__(self, dataset_name: str, word_vocab_size: int, path_vocab_size: int, target_vocab_size: int):
        """サーバー制御に必要なデータセット条件を初期化する。

        Args:
            dataset_name (str): 対象データセット名。
            word_vocab_size (int): 単語語彙サイズ。
            path_vocab_size (int): パス語彙サイズ。
            target_vocab_size (int): ターゲット語彙サイズ。

        Raises:
            None

        Returns:
            None: サーバー制御インスタンスを初期化する。
        """
        self.dataset_name = dataset_name
        self.word_vocab_size = word_vocab_size
        self.path_vocab_size = path_vocab_size
        self.target_vocab_size = target_vocab_size
        self.shm_name = f"code2vec_histograms_{dataset_name}"
        self.metadata_file = Path(f"/tmp/{self.shm_name}_metadata.json")

    def load_histograms_for_server(self) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
        """サーバー公開用のヒストグラム辞書をキャッシュ優先で読み込む。

        Args:
            None

        Raises:
            None

        Returns:
            tuple[dict[str, int], dict[str, int], dict[str, int]]: サーバー公開用ヒストグラム辞書。
        """
        dataset_dir = resolve_histogram_dataset_directory(dataset_name=self.dataset_name)
        cache_file = dataset_dir / "histogram_cache.pkl"

        print(f"[INFO] Loading histograms for dataset: {self.dataset_name}")

        if cache_file.exists():
            print(f"[INFO] Loading from cache: {cache_file}")
            try:
                cached = load_histograms_from_cache_file(cache_file)
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
        word_to_count, path_to_count, target_to_count = load_histograms_from_raw_files(
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
        """共有メモリ領域を作成してヒストグラムサーバーを起動する。

        Args:
            None

        Raises:
            None

        Returns:
            None: 共有メモリサーバーを起動し待機する。
        """
        print(f"\n{'=' * 60}")
        print("  Histogram Shared Memory Server")
        print(f"{'=' * 60}\n")

        word_to_count, path_to_count, target_to_count = self.load_histograms_for_server()
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
        """稼働中の共有メモリサーバーとメタデータを停止・掃除する。

        Args:
            None

        Raises:
            None

        Returns:
            None: 共有メモリサーバー停止処理を実行する。
        """
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

    def print_server_status(self) -> None:
        """メタデータとプロセス状態からサーバー稼働状況を表示する。

        Args:
            None

        Raises:
            None

        Returns:
            None: サーバー稼働状況を標準出力へ表示する。
        """
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


def parse_histogram_server_cli_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """ヒストグラムサーバー操作用の CLI 引数を解析する。

    Args:
        argv (list[str] | None): 解析対象のコマンドライン引数。

    Raises:
        None

    Returns:
        argparse.Namespace: 解析済み引数。
    """
    parser = argparse.ArgumentParser(description="Histogram Shared Memory Server")
    parser.add_argument("command", choices=["start", "stop", "status"], help="Server command")
    parser.add_argument("--dataset", default="js_dataset_min5", help="Dataset name")
    parser.add_argument("--word_vocab_size", type=int, default=1301136, help="Word vocabulary size")
    parser.add_argument("--path_vocab_size", type=int, default=911417, help="Path vocabulary size")
    parser.add_argument("--target_vocab_size", type=int, default=261245, help="Target vocabulary size")
    return parser.parse_args(argv)


def run_histogram_shared_memory_server(argv: list[str] | None = None) -> int:
    """CLI コマンドに応じて共有メモリサーバー処理を実行する。

    Args:
        argv (list[str] | None): 実行引数。

    Raises:
        None

    Returns:
        int: 正常終了時は 0。
    """
    args = parse_histogram_server_cli_arguments(argv)
    server_controller = HistogramSharedMemoryServerController(
        dataset_name=args.dataset,
        word_vocab_size=args.word_vocab_size,
        path_vocab_size=args.path_vocab_size,
        target_vocab_size=args.target_vocab_size,
    )

    if args.command == "start":
        server_controller.start_server()
    elif args.command == "stop":
        server_controller.stop_server()
    else:
        server_controller.print_server_status()

    return 0


if __name__ == "__main__":
    sys.exit(run_histogram_shared_memory_server())
