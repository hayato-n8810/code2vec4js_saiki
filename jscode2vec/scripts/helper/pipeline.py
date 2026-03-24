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
from typing import Iterable

from .config import (
    EXTRACT_TIMEOUT_SEC,
    INFER_TIMEOUT_SEC,
    MIN_FILES_FOR_SHM,
    PREPROCESS_MAX_RETRIES,
    HyperParams,
)
from .preprocess_engine import preprocess_test_data
from .shm_manager import ShmManager
from .vectorize_engine import export_code_vectors

VALID_LINE = re.compile(r"^[a-zA-Z|]+\s")


@dataclass(frozen=True)
class ScopeResult:
    context_count: dict[str, int | dict[str, str]]
    processed: int
    succeeded: int


class VectorizePipeline:
    def __init__(self, project_root: Path, hyperparams: HyperParams, mode: str):
        self.project_root = project_root
        self.hyperparams = hyperparams
        self.mode = mode
        self.extract_script = project_root / "JSExtractor" / "extract.py"

    def run_scope(
        self,
        js_files: list[Path],
        output_base: Path,
        source_root: Path,
        jobs: int,
        logger: logging.Logger,
    ) -> ScopeResult:
        c2v_dir = output_base / "c2v"
        vectors_dir = output_base / "vectors"
        c2v_dir.mkdir(parents=True, exist_ok=True)
        vectors_dir.mkdir(parents=True, exist_ok=True)

        result_map: dict[str, int | dict[str, str]] = {}
        succeeded = 0

        shm_manager: ShmManager | None = None
        shm_env_backup = {
            "HISTOGRAM_SHM_NAME": os.environ.get("HISTOGRAM_SHM_NAME"),
            "HISTOGRAM_SHM_SIZE": os.environ.get("HISTOGRAM_SHM_SIZE"),
        }

        try:
            if self._should_enable_shm(jobs=jobs, file_count=len(js_files)):
                shm_manager = ShmManager(
                    project_root=self.project_root,
                    dataset_name=self.hyperparams.dataset_name,
                    word_vocab_size=self.hyperparams.word_vocab_size,
                    path_vocab_size=self.hyperparams.path_vocab_size,
                    target_vocab_size=self.hyperparams.target_vocab_size,
                )
                shm_manager.start_or_reuse(logger)
                shm_manager.apply_environment()

            if jobs > 1:
                self._apply_parallel_env(jobs=jobs, logger=logger)

            if jobs <= 1 or len(js_files) <= 1:
                for js_file in js_files:
                    key = self._key_for_json(js_file, source_root)
                    result = self._process_file(js_file, key, c2v_dir, vectors_dir, logger)
                    result_map[key] = result
                    if isinstance(result, int):
                        succeeded += 1
            else:
                # CPUバウンドではなく外部プロセス実行が中心のためスレッド並列を使う
                with ThreadPoolExecutor(max_workers=jobs) as executor:
                    futures = {
                        executor.submit(
                            self._process_file,
                            js_file,
                            self._key_for_json(js_file, source_root),
                            c2v_dir,
                            vectors_dir,
                            logger,
                        ): js_file
                        for js_file in js_files
                    }

                    for future in as_completed(futures):
                        js_file = futures[future]
                        key = self._key_for_json(js_file, source_root)
                        try:
                            result = future.result()
                        except Exception as exc:  # noqa: BLE001
                            result = {"error": f"unexpected error: {exc}"}
                            logger.exception("予期しないエラー: %s", js_file)
                        result_map[key] = result
                        if isinstance(result, int):
                            succeeded += 1
        finally:
            self._restore_env(shm_env_backup)
            if shm_manager is not None:
                shm_manager.stop_if_owned(logger)

        self._write_context_count(output_base / "context_count.json", result_map)
        return ScopeResult(context_count=result_map, processed=len(js_files), succeeded=succeeded)

    def run_scopes_balanced(
        self,
        scopes: list[tuple[str, list[Path], Path, Path, logging.Logger]],
        jobs: int,
    ) -> dict[str, ScopeResult]:
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

        shm_manager: ShmManager | None = None
        shm_env_backup = {
            "HISTOGRAM_SHM_NAME": os.environ.get("HISTOGRAM_SHM_NAME"),
            "HISTOGRAM_SHM_SIZE": os.environ.get("HISTOGRAM_SHM_SIZE"),
        }

        try:
            if self._should_enable_shm(jobs=jobs, file_count=len(tasks)):
                first_logger = scopes[0][4] if scopes else logging.getLogger(__name__)
                shm_manager = ShmManager(
                    project_root=self.project_root,
                    dataset_name=self.hyperparams.dataset_name,
                    word_vocab_size=self.hyperparams.word_vocab_size,
                    path_vocab_size=self.hyperparams.path_vocab_size,
                    target_vocab_size=self.hyperparams.target_vocab_size,
                )
                shm_manager.start_or_reuse(first_logger)
                shm_manager.apply_environment()

            if jobs > 1 and scopes:
                self._apply_parallel_env(jobs=jobs, logger=scopes[0][4])

            if jobs <= 1 or len(tasks) <= 1:
                for scope_name, js_file in tasks:
                    self._run_single_task(scope_state, scope_name, js_file)
            else:
                with ThreadPoolExecutor(max_workers=jobs) as executor:
                    futures = {
                        executor.submit(self._run_single_task, scope_state, scope_name, js_file): (scope_name, js_file)
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
                            key = self._key_for_json(js_file, source_root)  # type: ignore[arg-type]
                            result_map = state["result_map"]  # type: ignore[assignment]
                            lock = state["lock"]  # type: ignore[assignment]
                            with lock:  # type: ignore[attr-defined]
                                result_map[key] = {"error": f"unexpected error: {exc}"}
                            logger.exception("予期しないエラー: %s", js_file)
        finally:
            self._restore_env(shm_env_backup)
            if shm_manager is not None:
                stop_logger = scopes[0][4] if scopes else logging.getLogger(__name__)
                shm_manager.stop_if_owned(stop_logger)

        results: dict[str, ScopeResult] = {}
        for scope_name, state in scope_state.items():
            output_base = state["output_base"]
            result_map = state["result_map"]
            processed = state["processed"]
            succeeded = state["succeeded"]
            self._write_context_count(output_base / "context_count.json", result_map)  # type: ignore[arg-type]
            results[scope_name] = ScopeResult(
                context_count=result_map,  # type: ignore[arg-type]
                processed=processed,  # type: ignore[arg-type]
                succeeded=succeeded,  # type: ignore[arg-type]
            )

        return results

    def validate_runtime_inputs(self) -> None:
        missing_files: list[Path] = []

        for required in [self.extract_script]:
            if not required.exists():
                missing_files.append(required)

        for required in [
            self._resolve_runtime_path(self.hyperparams.word_histo),
            self._resolve_runtime_path(self.hyperparams.path_histo),
            self._resolve_runtime_path(self.hyperparams.target_histo),
        ]:
            if not required.exists():
                missing_files.append(required)

        model_meta = Path(str(self._resolve_runtime_path(self.hyperparams.model_path)) + ".meta")
        model_plain = self._resolve_runtime_path(self.hyperparams.model_path)
        if not model_meta.exists() and not model_plain.exists():
            missing_files.append(model_meta)

        if missing_files:
            joined = "\n".join(str(p) for p in missing_files)
            raise FileNotFoundError(f"必要ファイルが存在しません:\n{joined}")

    def _process_file(
        self,
        js_file: Path,
        json_key: str,
        c2v_dir: Path,
        vectors_dir: Path,
        logger: logging.Logger,
    ) -> int | dict[str, str]:
        # サブディレクトリがある場合の同名ファイル衝突を避ける
        base_name = json_key[:-3] if json_key.endswith(".js") else json_key
        base_name = base_name.replace("/", "__")
        raw_file = c2v_dir / f"{base_name}.test.raw.txt"
        c2v_file = c2v_dir / f"{base_name}.test.c2v"
        vectors_tmp = c2v_dir / f"{base_name}.test.c2v.vectors"
        vector_output = vectors_dir / f"{base_name}.vector"

        try:
            if vector_output.exists() and vector_output.stat().st_size > 0:
                cached_count = self._count_contexts_for_skip(raw_file=raw_file, c2v_file=c2v_file)
                logger.info("スキップ(既存ベクトル): %s", json_key)
                if cached_count is not None:
                    return cached_count
                return {"skipped": "existing vector"}

            self._extract(js_file, raw_file)
            context_count = self._validate_and_count(raw_file)
            if context_count <= 0:
                return {"error": "no valid context"}

            self._preprocess(raw_file, c2v_dir / base_name, logger)
            if not c2v_file.exists() or c2v_file.stat().st_size == 0:
                return {"error": "preprocess output is empty"}

            self._vectorize(c2v_file)
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

    def _run_single_task(self, scope_state: dict[str, dict[str, object]], scope_name: str, js_file: Path) -> None:
        state = scope_state[scope_name]
        source_root = state["source_root"]  # type: ignore[assignment]
        c2v_dir = state["c2v_dir"]  # type: ignore[assignment]
        vectors_dir = state["vectors_dir"]  # type: ignore[assignment]
        logger = state["logger"]  # type: ignore[assignment]
        result_map = state["result_map"]  # type: ignore[assignment]
        lock = state["lock"]  # type: ignore[assignment]

        key = self._key_for_json(js_file, source_root)  # type: ignore[arg-type]
        result = self._process_file(
            js_file=js_file,
            json_key=key,
            c2v_dir=c2v_dir,  # type: ignore[arg-type]
            vectors_dir=vectors_dir,  # type: ignore[arg-type]
            logger=logger,  # type: ignore[arg-type]
        )
        with lock:  # type: ignore[attr-defined]
            result_map[key] = result
            if isinstance(result, int):
                state["succeeded"] = int(state["succeeded"]) + 1

    def _extract(self, js_file: Path, raw_file: Path) -> None:
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
        with raw_file.open("w", encoding="utf-8") as out:
            self._run(command, stdout=out, timeout=EXTRACT_TIMEOUT_SEC)

    def _validate_and_count(self, raw_file: Path) -> int:
        if not raw_file.exists():
            raise FileNotFoundError(f"抽出結果がありません: {raw_file}")

        valid_lines: list[str] = []
        context_count = 0

        with raw_file.open("r", encoding="utf-8") as fp:
            for line in fp:
                if not VALID_LINE.search(line):
                    continue
                stripped = line.rstrip("\n")
                parts = stripped.split(" ")
                if len(parts) < 2:
                    continue
                valid_lines.append(stripped)
                context_count += max(len(parts) - 1, 0)

        raw_file.write_text("\n".join(valid_lines) + ("\n" if valid_lines else ""), encoding="utf-8")
        return context_count

    def _preprocess(self, raw_file: Path, output_name_base: Path, logger: logging.Logger) -> None:
        max_attempts = PREPROCESS_MAX_RETRIES + 1
        for attempt in range(1, max_attempts + 1):
            try:
                preprocess_test_data(
                    raw_file=raw_file,
                    output_name_base=output_name_base,
                    max_contexts=self.hyperparams.max_contexts,
                    word_vocab_size=self.hyperparams.word_vocab_size,
                    path_vocab_size=self.hyperparams.path_vocab_size,
                    target_vocab_size=self.hyperparams.target_vocab_size,
                    word_histogram=self._resolve_runtime_path(self.hyperparams.word_histo),
                    path_histogram=self._resolve_runtime_path(self.hyperparams.path_histo),
                    target_histogram=self._resolve_runtime_path(self.hyperparams.target_histo),
                )
                return
            except Exception:  # noqa: BLE001
                if attempt >= max_attempts:
                    raise
                logger.warning("前処理リトライ %s/%s", attempt, PREPROCESS_MAX_RETRIES)
                time.sleep(1)

    def _vectorize(self, c2v_file: Path) -> None:
        export_code_vectors(
            model_path=self._resolve_runtime_path(self.hyperparams.model_path),
            c2v_file=c2v_file,
            project_root=self.project_root,
            timeout_sec=INFER_TIMEOUT_SEC,
        )

    def _run(self, command: list[str], stdout: object | None = None, timeout: int | None = None) -> None:
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

    def _should_enable_shm(self, jobs: int, file_count: int) -> bool:
        if self.mode not in {"project", "all"}:
            return False
        if jobs <= 1:
            return False
        return file_count >= MIN_FILES_FOR_SHM

    @staticmethod
    def _restore_env(env_backup: dict[str, str | None]) -> None:
        for key, value in env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @staticmethod
    def _apply_parallel_env(jobs: int, logger: logging.Logger) -> None:
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
    def _count_contexts_for_skip(raw_file: Path, c2v_file: Path) -> int | None:
        source = c2v_file if c2v_file.exists() and c2v_file.stat().st_size > 0 else raw_file
        if not source.exists() or source.stat().st_size == 0:
            return None

        total = 0
        with source.open("r", encoding="utf-8") as fp:
            for line in fp:
                fields = line.strip().split()
                if len(fields) <= 1:
                    continue
                total += len(fields) - 1
        return total

    def _resolve_runtime_path(self, path_value: str) -> Path:
        candidate = Path(path_value)
        if candidate.exists():
            return candidate

        # Docker向けの/code2vecパスをローカルワークスペースへ変換する
        docker_prefix = "/code2vec/"
        if path_value.startswith(docker_prefix):
            mapped = self.project_root / path_value[len(docker_prefix) :]
            return mapped

        if candidate.is_absolute():
            return candidate

        return self.project_root / candidate

    @staticmethod
    def _key_for_json(js_file: Path, source_root: Path) -> str:
        try:
            return js_file.relative_to(source_root).as_posix()
        except ValueError:
            return js_file.name

    @staticmethod
    def _write_context_count(target_file: Path, data: dict[str, int | dict[str, str]]) -> None:
        target_file.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect_js_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*.js") if p.is_file())


def collect_project_dirs(parent: Path) -> list[Path]:
    return sorted(p for p in parent.iterdir() if p.is_dir())


def ensure_paths_exist(paths: Iterable[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"入力が存在しません: {path}")
