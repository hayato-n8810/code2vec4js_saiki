from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HistogramSharedMemorySession:
    """共有メモリセッションの接続情報を保持する。

    Args:
        name (str): 共有メモリ名。
        size (int): 共有メモリサイズ。
        owner (bool): このプロセスが起動オーナーかどうか。

    Raises:
        None

    Returns:
        HistogramSharedMemorySession: 共有メモリセッション情報。
    """
    name: str
    size: int
    owner: bool


class HistogramServerSessionManager:
    """共有メモリヒストグラムサーバーの起動・再利用・停止を管理する。

    Args:
        project_root (Path): プロジェクトルート。
        dataset_name (str): 対象データセット名。
        word_vocab_size (int): 単語語彙サイズ。
        path_vocab_size (int): パス語彙サイズ。
        target_vocab_size (int): ターゲット語彙サイズ。
        startup_timeout_sec (int): サーバー起動待機秒数。

    Raises:
        None

    Returns:
        HistogramServerSessionManager: SHM サーバーセッション制御インスタンス。
    """

    def __init__(
        self,
        project_root: Path,
        dataset_name: str,
        word_vocab_size: int,
        path_vocab_size: int,
        target_vocab_size: int,
        startup_timeout_sec: int = 30,
    ):
        """サーバーセッション管理に必要な実行パラメータを初期化する。

        Args:
            project_root (Path): プロジェクトルート。
            dataset_name (str): 対象データセット名。
            word_vocab_size (int): 単語語彙サイズ。
            path_vocab_size (int): パス語彙サイズ。
            target_vocab_size (int): ターゲット語彙サイズ。
            startup_timeout_sec (int): サーバー起動待機秒数。

        Raises:
            None

        Returns:
            None: セッションマネージャを初期化する。
        """
        self.project_root = project_root
        self.dataset_name = dataset_name
        self.word_vocab_size = word_vocab_size
        self.path_vocab_size = path_vocab_size
        self.target_vocab_size = target_vocab_size
        self.startup_timeout_sec = startup_timeout_sec
        self.scripts_root = self.project_root / "jscode2vec" / "scripts"
        self.server_module = "helper.runtime.histogram_server_controller"
        self.metadata_file = Path(f"/tmp/code2vec_histograms_{dataset_name}_metadata.json")
        self.server_process: subprocess.Popen[str] | None = None
        self.session: HistogramSharedMemorySession | None = None

    def start_or_reuse_server_session(self, logger) -> HistogramSharedMemorySession:
        """既存サーバーを再利用するか新規起動してセッションを確立する。

        Args:
            logger: 状態ログ出力先。

        Raises:
            RuntimeError: サーバー起動待機がタイムアウトした場合。

        Returns:
            HistogramSharedMemorySession: 再利用または新規起動したセッション情報。
        """
        reused = self._try_reuse_running_server(logger)
        if reused is not None:
            self.session = reused
            return reused

        command = [
            sys.executable,
            "-m",
            self.server_module,
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
            cwd=self.scripts_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        started = self._wait_for_metadata_file(owner=True, logger=logger)
        self.session = started
        return started

    def stop_server_if_owner(self, logger) -> None:
        """現在プロセスがオーナーの場合のみ共有メモリサーバーを停止する。

        Args:
            logger: 状態ログ出力先。

        Raises:
            None

        Returns:
            None: オーナー時のみサーバー停止を行う。
        """
        if self.session is None or not self.session.owner:
            return

        command = [
            sys.executable,
            "-m",
            self.server_module,
            "--dataset",
            self.dataset_name,
            "stop",
        ]
        subprocess.run(
            command,
            cwd=self.scripts_root,
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

    def apply_session_environment_variables(self) -> None:
        """確立済みセッション情報を環境変数へ反映する。

        Args:
            None

        Raises:
            None

        Returns:
            None: HISTOGRAM_SHM_* 環境変数を設定する。
        """
        if self.session is None:
            return
        os.environ["HISTOGRAM_SHM_NAME"] = self.session.name
        os.environ["HISTOGRAM_SHM_SIZE"] = str(self.session.size)

    def _try_reuse_running_server(self, logger) -> HistogramSharedMemorySession | None:
        """稼働中サーバーの状態を確認し再利用可能なセッションを取得する。

        Args:
            logger: 状態ログ出力先。

        Raises:
            None

        Returns:
            HistogramSharedMemorySession | None: 利用可能な既存サーバーがあればセッション、無ければ None。
        """
        if not self.metadata_file.exists():
            return None

        command = [
            sys.executable,
            "-m",
            self.server_module,
            "--dataset",
            self.dataset_name,
            "status",
        ]
        result = subprocess.run(
            command,
            cwd=self.scripts_root,
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
        return HistogramSharedMemorySession(name=shm_name, size=shm_size, owner=False)

    def _wait_for_metadata_file(self, owner: bool, logger) -> HistogramSharedMemorySession:
        """メタデータファイル出現を待機して起動済みセッション情報を取得する。

        Args:
            owner (bool): この起動がオーナー起動かどうか。
            logger: 状態ログ出力先。

        Raises:
            RuntimeError: 起動待機がタイムアウトした場合。

        Returns:
            HistogramSharedMemorySession: 起動完了したセッション情報。
        """
        start = time.time()
        while time.time() - start < self.startup_timeout_sec:
            if self.metadata_file.exists():
                try:
                    metadata = json.loads(self.metadata_file.read_text(encoding="utf-8"))
                    shm_name = str(metadata["shm_name"])
                    shm_size = int(metadata["size"])
                    logger.info("SHMサーバー起動完了: name=%s size=%s", shm_name, shm_size)
                    return HistogramSharedMemorySession(name=shm_name, size=shm_size, owner=owner)
                except Exception:  # noqa: BLE001
                    pass
            time.sleep(1)

        raise RuntimeError("SHMサーバーの起動待機がタイムアウトしました")
