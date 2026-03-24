from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from ..config import (
    EXTRACT_TIMEOUT_SEC,
    INFER_TIMEOUT_SEC,
    MIN_FILES_FOR_SHM,
    PREPROCESS_MAX_RETRIES,
    HyperParams,
)
from ..runtime.histogram_server_session import HistogramServerSessionManager
from .c2v_preprocess_transformer import preprocess_raw_contexts_to_c2v_test_data
from .c2v_vector_export_worker import export_code_vectors_with_subprocess

VALID_CONTEXT_LINE_PATTERN = re.compile(r"^[a-zA-Z|]+\s")


@dataclass(frozen=True)
class ScopeExecutionResult:
    """スコープ単位のベクトル化実行結果を保持する。

    Args:
        context_count (dict[str, int | dict[str, str]]): ファイル別 context 数またはエラー内容。
        processed (int): 処理対象ファイル数。
        succeeded (int): 成功ファイル数。

    Raises:
        None

    Returns:
        ScopeExecutionResult: スコープ実行結果。
    """
    context_count: dict[str, int | dict[str, str]]
    processed: int
    succeeded: int


class JavaScriptVectorizationPipeline:
    """JS 抽出・前処理・推論・集計を統合実行するパイプライン。

    Args:
        project_root (Path): プロジェクトルート。
        hyperparams (HyperParams): code2vec 関連ハイパーパラメータ。
        mode (str): 実行モード。

    Raises:
        None

    Returns:
        JavaScriptVectorizationPipeline: JS ベクトル化実行パイプライン。
    """

    def __init__(self, project_root: Path, hyperparams: HyperParams, mode: str):
        """実行ルート・ハイパーパラメータ・モードを保持して初期化する。

        Args:
            project_root (Path): プロジェクトルート。
            hyperparams (HyperParams): code2vec 関連ハイパーパラメータ。
            mode (str): 実行モード。

        Raises:
            None

        Returns:
            None: パイプラインを初期化する。
        """
        self.project_root = project_root
        self.hyperparams = hyperparams
        self.mode = mode
        self.extract_script = project_root / "JSExtractor" / "extract.py"

    def run_for_single_scope(
        self,
        js_files: list[Path],
        output_base: Path,
        source_root: Path,
        jobs: int,
        logger: logging.Logger,
    ) -> ScopeExecutionResult:
        """単一スコープの JS ファイル群をベクトル化して結果を返す。

        Args:
            js_files (list[Path]): 処理対象 JS ファイル。
            output_base (Path): 出力ベースディレクトリ。
            source_root (Path): context_count.json 用の相対基準ディレクトリ。
            jobs (int): 並列度。
            logger (logging.Logger): ロガー。

        Raises:
            None

        Returns:
            ScopeExecutionResult: スコープ実行結果。
        """
        c2v_dir = output_base / "c2v"
        vectors_dir = output_base / "vectors"
        c2v_dir.mkdir(parents=True, exist_ok=True)
        vectors_dir.mkdir(parents=True, exist_ok=True)

        result_map: dict[str, int | dict[str, str]] = {}
        succeeded = 0

        shm_manager: HistogramServerSessionManager | None = None
        shared_memory_env_backup = {
            "HISTOGRAM_SHM_NAME": os.environ.get("HISTOGRAM_SHM_NAME"),
            "HISTOGRAM_SHM_SIZE": os.environ.get("HISTOGRAM_SHM_SIZE"),
        }

        try:
            if self._can_enable_shared_histogram_memory(jobs=jobs, file_count=len(js_files)):
                shm_manager = HistogramServerSessionManager(
                    project_root=self.project_root,
                    dataset_name=self.hyperparams.dataset_name,
                    word_vocab_size=self.hyperparams.word_vocab_size,
                    path_vocab_size=self.hyperparams.path_vocab_size,
                    target_vocab_size=self.hyperparams.target_vocab_size,
                )
                shm_manager.start_or_reuse_server_session(logger)
                shm_manager.apply_session_environment_variables()

            if jobs > 1:
                self._apply_parallel_inference_environment(jobs=jobs, logger=logger)

            if jobs <= 1 or len(js_files) <= 1:
                for js_file in js_files:
                    json_key = self._build_context_count_key(js_file, source_root)
                    result = self._process_single_javascript_file(js_file, json_key, c2v_dir, vectors_dir, logger)
                    result_map[json_key] = result
                    if isinstance(result, int):
                        succeeded += 1
            else:
                # CPU バウンドではなく外部プロセス実行が中心のためスレッド並列を使う
                with ThreadPoolExecutor(max_workers=jobs) as executor:
                    futures = {
                        executor.submit(
                            self._process_single_javascript_file,
                            js_file,
                            self._build_context_count_key(js_file, source_root),
                            c2v_dir,
                            vectors_dir,
                            logger,
                        ): js_file
                        for js_file in js_files
                    }

                    for future in as_completed(futures):
                        js_file = futures[future]
                        json_key = self._build_context_count_key(js_file, source_root)
                        try:
                            result = future.result()
                        except Exception as exc:  # noqa: BLE001
                            result = {"error": f"unexpected error: {exc}"}
                            logger.exception("予期しないエラー: %s", js_file)
                        result_map[json_key] = result
                        if isinstance(result, int):
                            succeeded += 1
        finally:
            self._restore_environment_variables(shared_memory_env_backup)
            if shm_manager is not None:
                shm_manager.stop_server_if_owner(logger)

        self._write_context_count_json(output_base / "context_count.json", result_map)
        return ScopeExecutionResult(context_count=result_map, processed=len(js_files), succeeded=succeeded)

    def run_for_balanced_multi_scope(
        self,
        scopes: list[tuple[str, list[Path], Path, Path, logging.Logger]],
        jobs: int,
    ) -> dict[str, ScopeExecutionResult]:
        """複数スコープのタスクを平準化して並列ベクトル化を実行する。

        Args:
            scopes (list[tuple[str, list[Path], Path, Path, logging.Logger]]):
                (scope_name, js_files, output_base, source_root, logger) の一覧。
            jobs (int): 並列度。

        Raises:
            None

        Returns:
            dict[str, ScopeExecutionResult]: scope 名ごとの実行結果。
        """
        scope_state: dict[str, dict[str, object]] = {}
        tasks: list[tuple[str, Path]] = []

        for scope_name, js_files, output_base, source_root, logger in scopes:
            c2v_dir = output_base / "c2v"
            vectors_dir = output_base / "vectors"
            c2v_dir.mkdir(parents=True, exist_ok=True)
            vectors_dir.mkdir(parents=True, exist_ok=True)

            scope_state[scope_name] = {
                "result_map": {},
                "processed": len(js_files),
                "succeeded": 0,
                "lock": threading.Lock(),
                "output_base": output_base,
                "source_root": source_root,
                "c2v_dir": c2v_dir,
                "vectors_dir": vectors_dir,
                "logger": logger,
            }
            for js_file in js_files:
                tasks.append((scope_name, js_file))

        shm_manager: HistogramServerSessionManager | None = None
        shared_memory_env_backup = {
            "HISTOGRAM_SHM_NAME": os.environ.get("HISTOGRAM_SHM_NAME"),
            "HISTOGRAM_SHM_SIZE": os.environ.get("HISTOGRAM_SHM_SIZE"),
        }

        try:
            if self._can_enable_shared_histogram_memory(jobs=jobs, file_count=len(tasks)):
                first_logger = scopes[0][4] if scopes else logging.getLogger(__name__)
                shm_manager = HistogramServerSessionManager(
                    project_root=self.project_root,
                    dataset_name=self.hyperparams.dataset_name,
                    word_vocab_size=self.hyperparams.word_vocab_size,
                    path_vocab_size=self.hyperparams.path_vocab_size,
                    target_vocab_size=self.hyperparams.target_vocab_size,
                )
                shm_manager.start_or_reuse_server_session(first_logger)
                shm_manager.apply_session_environment_variables()

            if jobs > 1 and scopes:
                self._apply_parallel_inference_environment(jobs=jobs, logger=scopes[0][4])

            if jobs <= 1 or len(tasks) <= 1:
                for scope_name, js_file in tasks:
                    self._run_single_balanced_scope_task(scope_state, scope_name, js_file)
            else:
                with ThreadPoolExecutor(max_workers=jobs) as executor:
                    futures = {
                        executor.submit(
                            self._run_single_balanced_scope_task,
                            scope_state,
                            scope_name,
                            js_file,
                        ): (scope_name, js_file)
                        for scope_name, js_file in tasks
                    }
                    for future in as_completed(futures):
                        scope_name, js_file = futures[future]
                        try:
                            future.result()
                        except Exception as exc:  # noqa: BLE001
                            state = scope_state[scope_name]
                            source_root = state["source_root"]
                            logger = state["logger"]
                            json_key = self._build_context_count_key(js_file, source_root)  # type: ignore[arg-type]
                            result_map = state["result_map"]  # type: ignore[assignment]
                            lock = state["lock"]  # type: ignore[assignment]
                            with lock:  # type: ignore[attr-defined]
                                result_map[json_key] = {"error": f"unexpected error: {exc}"}
                            logger.exception("予期しないエラー: %s", js_file)
        finally:
            self._restore_environment_variables(shared_memory_env_backup)
            if shm_manager is not None:
                stop_logger = scopes[0][4] if scopes else logging.getLogger(__name__)
                shm_manager.stop_server_if_owner(stop_logger)

        results: dict[str, ScopeExecutionResult] = {}
        for scope_name, state in scope_state.items():
            output_base = state["output_base"]
            result_map = state["result_map"]
            processed = state["processed"]
            succeeded = state["succeeded"]
            self._write_context_count_json(output_base / "context_count.json", result_map)  # type: ignore[arg-type]
            results[scope_name] = ScopeExecutionResult(
                context_count=result_map,  # type: ignore[arg-type]
                processed=processed,  # type: ignore[arg-type]
                succeeded=succeeded,  # type: ignore[arg-type]
            )

        return results

    def validate_required_runtime_files(self) -> None:
        """実行前に抽出器・ヒストグラム・モデルの存在を検証する。

        Args:
            None

        Raises:
            FileNotFoundError: 実行に必要なファイルが不足している場合。

        Returns:
            None: 必須ファイルの存在を検証する。
        """
        missing_files: list[Path] = []

        for required in [self.extract_script]:
            if not required.exists():
                missing_files.append(required)

        for required in [
            self._resolve_runtime_resource_path(self.hyperparams.word_histo),
            self._resolve_runtime_resource_path(self.hyperparams.path_histo),
            self._resolve_runtime_resource_path(self.hyperparams.target_histo),
        ]:
            if not required.exists():
                missing_files.append(required)

        model_meta = Path(str(self._resolve_runtime_resource_path(self.hyperparams.model_path)) + ".meta")
        model_plain = self._resolve_runtime_resource_path(self.hyperparams.model_path)
        if not model_meta.exists() and not model_plain.exists():
            missing_files.append(model_meta)

        if missing_files:
            joined = "\n".join(str(path) for path in missing_files)
            raise FileNotFoundError(f"必要ファイルが存在しません:\n{joined}")

    def _process_single_javascript_file(
        self,
        js_file: Path,
        json_key: str,
        c2v_dir: Path,
        vectors_dir: Path,
        logger: logging.Logger,
    ) -> int | dict[str, str]:
        """単一 JS ファイルに対して抽出からベクトル保存までを実行する。

        Args:
            js_file (Path): 処理対象 JS ファイル。
            json_key (str): context_count.json 用キー。
            c2v_dir (Path): c2v 中間生成ディレクトリ。
            vectors_dir (Path): 最終ベクトル出力ディレクトリ。
            logger (logging.Logger): ロガー。

        Raises:
            None

        Returns:
            int | dict[str, str]: 成功時は context 数、失敗時はエラー情報。
        """
        # サブディレクトリがある場合の同名ファイル衝突を避ける
        base_name = json_key[:-3] if json_key.endswith(".js") else json_key
        base_name = base_name.replace("/", "__")
        raw_file = c2v_dir / f"{base_name}.test.raw.txt"
        c2v_file = c2v_dir / f"{base_name}.test.c2v"
        vectors_tmp = c2v_dir / f"{base_name}.test.c2v.vectors"
        vector_output = vectors_dir / f"{base_name}.vector"

        try:
            if vector_output.exists() and vector_output.stat().st_size > 0:
                cached_count = self._count_contexts_for_skip_case(raw_file=raw_file, c2v_file=c2v_file)
                logger.info("スキップ(既存ベクトル): %s", json_key)
                if cached_count is not None:
                    return cached_count
                return {"skipped": "existing vector"}

            self._extract_raw_contexts_from_javascript(js_file, raw_file)
            context_count = self._normalize_raw_contexts_and_count(raw_file)
            if context_count <= 0:
                return {"error": "no valid context"}

            self._preprocess_raw_contexts_with_retry(raw_file, c2v_dir / base_name, logger)
            if not c2v_file.exists() or c2v_file.stat().st_size == 0:
                return {"error": "preprocess output is empty"}

            self._export_vector_from_c2v_file(c2v_file)
            if not vectors_tmp.exists() or vectors_tmp.stat().st_size == 0:
                return {"error": "vector export failed"}

            shutil.move(str(vectors_tmp), str(vector_output))
            logger.info("完了: %s", json_key)
            return context_count
        except Exception as exc:  # noqa: BLE001
            logger.error("失敗: %s: %s", json_key, exc)
            return {"error": str(exc)}
        finally:
            if raw_file.exists():
                raw_file.unlink()
            if vectors_tmp.exists():
                vectors_tmp.unlink()

    def _run_single_balanced_scope_task(
        self,
        scope_state: dict[str, dict[str, object]],
        scope_name: str,
        js_file: Path,
    ) -> None:
        """balanced 実行用の1タスクを実行してスコープ状態へ反映する。

        Args:
            scope_state (dict[str, dict[str, object]]): スコープ実行中状態。
            scope_name (str): 対象スコープ名。
            js_file (Path): 処理対象 JS ファイル。

        Raises:
            None

        Returns:
            None: 実行結果を scope_state へ反映する。
        """
        state = scope_state[scope_name]
        source_root = state["source_root"]  # type: ignore[assignment]
        c2v_dir = state["c2v_dir"]  # type: ignore[assignment]
        vectors_dir = state["vectors_dir"]  # type: ignore[assignment]
        logger = state["logger"]  # type: ignore[assignment]
        result_map = state["result_map"]  # type: ignore[assignment]
        lock = state["lock"]  # type: ignore[assignment]

        json_key = self._build_context_count_key(js_file, source_root)  # type: ignore[arg-type]
        result = self._process_single_javascript_file(
            js_file=js_file,
            json_key=json_key,
            c2v_dir=c2v_dir,  # type: ignore[arg-type]
            vectors_dir=vectors_dir,  # type: ignore[arg-type]
            logger=logger,  # type: ignore[arg-type]
        )
        with lock:  # type: ignore[attr-defined]
            result_map[json_key] = result
            if isinstance(result, int):
                state["succeeded"] = int(state["succeeded"]) + 1

    def _extract_raw_contexts_from_javascript(self, js_file: Path, raw_file: Path) -> None:
        """JSExtractor を実行して raw context ファイルを生成する。

        Args:
            js_file (Path): 処理対象 JS ファイル。
            raw_file (Path): 抽出結果を書き込む raw ファイル。

        Raises:
            RuntimeError: 抽出コマンドが失敗した場合。

        Returns:
            None: JSExtractor 実行結果を raw_file に書き込む。
        """
        command = [
            "python3",
            str(self.extract_script),
            "--file",
            str(js_file),
            "--whole_file",
            "--max_path_length",
            str(self.hyperparams.max_path_length),
            "--max_path_width",
            str(self.hyperparams.max_path_width),
        ]
        with raw_file.open("w", encoding="utf-8") as stream:
            self._execute_subprocess(command, stdout=stream, timeout=EXTRACT_TIMEOUT_SEC)

    def _normalize_raw_contexts_and_count(self, raw_file: Path) -> int:
        """raw context の有効行だけを残して context 数を集計する。

        Args:
            raw_file (Path): 抽出済み raw ファイル。

        Raises:
            FileNotFoundError: raw ファイルが存在しない場合。

        Returns:
            int: 有効 context の合計数。
        """
        if not raw_file.exists():
            raise FileNotFoundError(f"抽出結果がありません: {raw_file}")

        valid_lines: list[str] = []
        context_count = 0

        with raw_file.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not VALID_CONTEXT_LINE_PATTERN.search(line):
                    continue
                stripped = line.rstrip("\n")
                parts = stripped.split(" ")
                if len(parts) < 2:
                    continue
                valid_lines.append(stripped)
                context_count += max(len(parts) - 1, 0)

        raw_file.write_text("\n".join(valid_lines) + ("\n" if valid_lines else ""), encoding="utf-8")
        return context_count

    def _preprocess_raw_contexts_with_retry(self, raw_file: Path, output_name_base: Path, logger: logging.Logger) -> None:
        """raw context 前処理をリトライ制御付きで実行する。

        Args:
            raw_file (Path): 抽出済み raw ファイル。
            output_name_base (Path): 前処理出力ベース名。
            logger (logging.Logger): ロガー。

        Raises:
            Exception: リトライ回数超過後も前処理が失敗した場合。

        Returns:
            None: 前処理成功時に戻る。
        """
        max_attempts = PREPROCESS_MAX_RETRIES + 1
        for attempt in range(1, max_attempts + 1):
            try:
                preprocess_raw_contexts_to_c2v_test_data(
                    raw_file=raw_file,
                    output_name_base=output_name_base,
                    max_contexts=self.hyperparams.max_contexts,
                    word_vocab_size=self.hyperparams.word_vocab_size,
                    path_vocab_size=self.hyperparams.path_vocab_size,
                    target_vocab_size=self.hyperparams.target_vocab_size,
                    word_histogram=self._resolve_runtime_resource_path(self.hyperparams.word_histo),
                    path_histogram=self._resolve_runtime_resource_path(self.hyperparams.path_histo),
                    target_histogram=self._resolve_runtime_resource_path(self.hyperparams.target_histo),
                )
                return
            except Exception:  # noqa: BLE001
                if attempt >= max_attempts:
                    raise
                logger.warning("前処理リトライ %s/%s", attempt, PREPROCESS_MAX_RETRIES)
                time.sleep(1)

    def _export_vector_from_c2v_file(self, c2v_file: Path) -> None:
        """.c2v ファイルから code2vec ベクトル出力を実行する。

        Args:
            c2v_file (Path): 前処理済み .c2v ファイル。

        Raises:
            RuntimeError: ベクトルエクスポート失敗時。

        Returns:
            None: ベクトルファイルを生成する。
        """
        export_code_vectors_with_subprocess(
            model_path=self._resolve_runtime_resource_path(self.hyperparams.model_path),
            c2v_file=c2v_file,
            project_root=self.project_root,
            timeout_sec=INFER_TIMEOUT_SEC,
        )

    def _execute_subprocess(self, command: list[str], stdout: object | None = None, timeout: int | None = None) -> None:
        """サブプロセスを実行し失敗時は例外に変換する。

        Args:
            command (list[str]): 実行コマンド。
            stdout (object | None): 標準出力の転送先。
            timeout (int | None): タイムアウト秒数。

        Raises:
            RuntimeError: タイムアウトまたは非ゼロ終了時。

        Returns:
            None: コマンド成功時に戻る。
        """
        try:
            proc = subprocess.run(
                command,
                cwd=self.project_root,
                stdout=stdout if stdout is not None else subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            timeout_text = timeout if timeout is not None else "unknown"
            raise RuntimeError(f"command timeout ({timeout_text}s): {' '.join(command)}") from exc

        if proc.returncode != 0:
            stderr = proc.stderr.strip() if proc.stderr else ""
            raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(command)}\n{stderr}")

    def _can_enable_shared_histogram_memory(self, jobs: int, file_count: int) -> bool:
        """実行条件に基づいて SHM ヒストグラム最適化の有効可否を判定する。

        Args:
            jobs (int): 並列度。
            file_count (int): 処理対象ファイル数。

        Raises:
            None

        Returns:
            bool: SHM 最適化を有効化するかどうか。
        """
        if self.mode not in {"project", "all"}:
            return False
        if jobs <= 1:
            return False
        return file_count >= MIN_FILES_FOR_SHM

    @staticmethod
    def _restore_environment_variables(env_backup: dict[str, str | None]) -> None:
        """バックアップ済み環境変数を元の値へ復元する。

        Args:
            env_backup (dict[str, str | None]): 復元対象環境変数のバックアップ。

        Raises:
            None

        Returns:
            None: 環境変数を復元する。
        """
        for key, value in env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @staticmethod
    def _apply_parallel_inference_environment(jobs: int, logger: logging.Logger) -> None:
        """並列実行時の BLAS 系スレッド環境変数を調整する。

        Args:
            jobs (int): 並列度。
            logger (logging.Logger): ロガー。

        Raises:
            None

        Returns:
            None: BLAS 系のスレッド数を調整する。
        """
        available = os.cpu_count() or 1
        threads_per_process = max(1, available // max(jobs, 1))
        os.environ["OMP_NUM_THREADS"] = str(threads_per_process)
        os.environ["MKL_NUM_THREADS"] = str(threads_per_process)
        os.environ["OPENBLAS_NUM_THREADS"] = str(threads_per_process)
        logger.info(
            "並列最適化: jobs=%s cpu=%s threads_per_process=%s",
            jobs,
            available,
            threads_per_process,
        )

    @staticmethod
    def _count_contexts_for_skip_case(raw_file: Path, c2v_file: Path) -> int | None:
        """既存成果物スキップ時に context 数を再計算する。

        Args:
            raw_file (Path): raw ファイル。
            c2v_file (Path): c2v ファイル。

        Raises:
            None

        Returns:
            int | None: 既存ファイルから数えた context 数。取得できない場合は None。
        """
        source = c2v_file if c2v_file.exists() and c2v_file.stat().st_size > 0 else raw_file
        if not source.exists() or source.stat().st_size == 0:
            return None

        total = 0
        with source.open("r", encoding="utf-8") as stream:
            for line in stream:
                fields = line.strip().split()
                if len(fields) <= 1:
                    continue
                total += len(fields) - 1
        return total

    def _resolve_runtime_resource_path(self, path_value: str) -> Path:
        """設定パスを実行環境で利用可能な実体パスへ解決する。

        Args:
            path_value (str): 設定ファイルのパス文字列。

        Raises:
            None

        Returns:
            Path: 実行環境で利用可能な実体パス。
        """
        candidate = Path(path_value)
        if candidate.exists():
            return candidate

        # Docker 向け /code2vec パスをローカルワークスペースへ変換する
        docker_prefix = "/code2vec/"
        if path_value.startswith(docker_prefix):
            mapped = self.project_root / path_value[len(docker_prefix) :]
            return mapped

        if candidate.is_absolute():
            return candidate

        return self.project_root / candidate

    @staticmethod
    def _build_context_count_key(js_file: Path, source_root: Path) -> str:
        """context_count.json へ保存する相対キーを生成する。

        Args:
            js_file (Path): 対象 JS ファイル。
            source_root (Path): 相対パス基準。

        Raises:
            None

        Returns:
            str: context_count.json へ保存するキー。
        """
        try:
            return js_file.relative_to(source_root).as_posix()
        except ValueError:
            return js_file.name

    @staticmethod
    def _write_context_count_json(target_file: Path, data: dict[str, int | dict[str, str]]) -> None:
        """context 数とエラー情報を JSON ファイルへ書き出す。

        Args:
            target_file (Path): 出力先 JSON ファイル。
            data (dict[str, int | dict[str, str]]): 保存データ。

        Raises:
            None

        Returns:
            None: context_count.json を書き出す。
        """
        target_file.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
