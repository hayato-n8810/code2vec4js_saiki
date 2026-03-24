from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ShmSession:
    name: str
    size: int
    owner: bool


class ShmManager:
    def __init__(
        self,
        project_root: Path,
        dataset_name: str,
        word_vocab_size: int,
        path_vocab_size: int,
        target_vocab_size: int,
        startup_timeout_sec: int = 30,
    ):
        self.project_root = project_root
        self.dataset_name = dataset_name
        self.word_vocab_size = word_vocab_size
        self.path_vocab_size = path_vocab_size
        self.target_vocab_size = target_vocab_size
        self.startup_timeout_sec = startup_timeout_sec
        self.server_script = self.project_root / "jscode2vec" / "scripts" / "histogram_server.py"
        self.metadata_file = Path(f"/tmp/code2vec_histograms_{dataset_name}_metadata.json")
        self.server_process: subprocess.Popen[str] | None = None
        self.session: ShmSession | None = None

    def start_or_reuse(self, logger) -> ShmSession:
        reused = self._try_reuse_existing(logger)
        if reused is not None:
            self.session = reused
            return reused

        command = [
            sys.executable,
            str(self.server_script),
            "--dataset",
            self.dataset_name,
            "--word_vocab_size",
            str(self.word_vocab_size),
            "--path_vocab_size",
            str(self.path_vocab_size),
            "--target_vocab_size",
            str(self.target_vocab_size),
            "start",
        ]
        self.server_process = subprocess.Popen(
            command,
            cwd=self.project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        started = self._wait_metadata(owner=True, logger=logger)
        self.session = started
        return started

    def stop_if_owned(self, logger) -> None:
        if self.session is None or not self.session.owner:
            return

        command = [
            sys.executable,
            str(self.server_script),
            "--dataset",
            self.dataset_name,
            "stop",
        ]
        subprocess.run(
            command,
            cwd=self.project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )

        if self.server_process is not None:
            try:
                self.server_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
            finally:
                self.server_process = None

        logger.info("SHMサーバー停止: owner session closed")

    def _try_reuse_existing(self, logger) -> ShmSession | None:
        if not self.metadata_file.exists():
            return None

        command = [
            sys.executable,
            str(self.server_script),
            "--dataset",
            self.dataset_name,
            "status",
        ]
        result = subprocess.run(
            command,
            cwd=self.project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )

        if result.returncode != 0 or "Server Status: RUNNING" not in result.stdout:
            return None

        try:
            metadata = json.loads(self.metadata_file.read_text(encoding="utf-8"))
            shm_name = str(metadata["shm_name"])
            shm_size = int(metadata["size"])
        except Exception:  # noqa: BLE001
            return None

        logger.info("SHMサーバー再利用: name=%s size=%s", shm_name, shm_size)
        return ShmSession(name=shm_name, size=shm_size, owner=False)

    def _wait_metadata(self, owner: bool, logger) -> ShmSession:
        start = time.time()
        while time.time() - start < self.startup_timeout_sec:
            if self.metadata_file.exists():
                try:
                    metadata = json.loads(self.metadata_file.read_text(encoding="utf-8"))
                    shm_name = str(metadata["shm_name"])
                    shm_size = int(metadata["size"])
                    logger.info("SHMサーバー起動完了: name=%s size=%s", shm_name, shm_size)
                    return ShmSession(name=shm_name, size=shm_size, owner=owner)
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(1)

        raise RuntimeError("SHMサーバーの起動待機がタイムアウトしました")

    def apply_environment(self) -> None:
        if self.session is None:
            return
        os.environ["HISTOGRAM_SHM_NAME"] = self.session.name
        os.environ["HISTOGRAM_SHM_SIZE"] = str(self.session.size)
