#!/usr/bin/env python3
from __future__ import annotations

import logging
import sys
from pathlib import Path

from helper.cli_options import CliOptions, parse_vectorization_cli_options
from helper.config import load_hyperparams
from helper.vectorization.javascript_vectorization_pipeline import JavaScriptVectorizationPipeline
from helper.vectorization.source_path_discovery import (
    assert_input_paths_exist,
    collect_child_project_directories,
    collect_javascript_source_files,
)


def _resolve_default_vector_output_path(input_path: Path, mode: str, project_root: Path) -> Path:
    """入力パスと実行モードに応じて規定のベクトル出力先を解決する。

    Args:
        input_path (Path): 入力ファイルまたは入力ディレクトリ。
        mode (str): 実行モード。
        project_root (Path): プロジェクトルート。

    Raises:
        None

    Returns:
        Path: 規定出力先パス。
    """
    # 既定出力は targets セグメントを outputs/vec に置換する
    parts = list(input_path.parts)
    replaced = False
    for idx, part in enumerate(parts):
        if part == "targets":
            parts[idx] = "outputs"
            parts.insert(idx + 1, "vec")
            replaced = True
            break

    if replaced:
        replaced_path = Path(*parts)
        if mode == "single":
            return replaced_path.parent / input_path.stem
        return replaced_path

    # targets が無い場合は outputs/vec/others に退避する
    if mode == "single":
        return project_root / "jscode2vec" / "outputs" / "vec" / "others" / input_path.stem
    return project_root / "jscode2vec" / "outputs" / "vec" / "others" / input_path.name


def _build_process_logger(log_path: Path) -> logging.Logger:
    """標準出力とログファイルへ同時出力する処理ロガーを生成する。

    Args:
        log_path (Path): ログファイルパス。

    Raises:
        None

    Returns:
        logging.Logger: 標準出力とファイルへ出力するロガー。
    """
    logger = logging.getLogger(f"jscode2vec-experiments-{log_path}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def _prepare_output_directory_and_logger(output_base: Path) -> logging.Logger:
    """出力ディレクトリを作成し対応する処理ロガーを返す。

    Args:
        output_base (Path): モードごとの出力ベースディレクトリ。

    Raises:
        None

    Returns:
        logging.Logger: 該当出力先に紐づくロガー。
    """
    output_base.mkdir(parents=True, exist_ok=True)
    return _build_process_logger(output_base / "process.log")


def _run_single_file_mode(options: CliOptions, pipeline: JavaScriptVectorizationPipeline, project_root: Path) -> int:
    """単一 JS ファイルを対象にベクトル化処理を実行する。

    Args:
        options (CliOptions): CLI オプション。
        pipeline (JavaScriptVectorizationPipeline): ベクトル化実行パイプライン。
        project_root (Path): プロジェクトルート。

    Raises:
        ValueError: 入力が JS ファイルでない場合。

    Returns:
        int: 全ファイル成功時 0、失敗を含む場合 1。
    """
    input_file = options.input_path
    assert_input_paths_exist([input_file])
    if not input_file.is_file() or input_file.suffix != ".js":
        raise ValueError(f"-s/--single はJSファイルを指定してください: {input_file}")

    output_base = options.output or _resolve_default_vector_output_path(input_file, "single", project_root)

    logger = _prepare_output_directory_and_logger(output_base)
    logger.info("開始(single): %s", input_file)

    result = pipeline.run_for_single_scope(
        js_files=[input_file],
        output_base=output_base,
        source_root=input_file.parent,
        jobs=1,
        logger=logger,
    )

    logger.info("終了(single): success=%s/%s", result.succeeded, result.processed)
    return 0 if result.succeeded == result.processed else 1


def _run_project_directory_mode(options: CliOptions, pipeline: JavaScriptVectorizationPipeline, project_root: Path) -> int:
    """単一プロジェクト配下の JS ファイル群をベクトル化する。

    Args:
        options (CliOptions): CLI オプション。
        pipeline (JavaScriptVectorizationPipeline): ベクトル化実行パイプライン。
        project_root (Path): プロジェクトルート。

    Raises:
        ValueError: 入力がディレクトリでない場合。
        ValueError: JS ファイルが見つからない場合。

    Returns:
        int: 全ファイル成功時 0、失敗を含む場合 1。
    """
    project_dir = options.input_path
    assert_input_paths_exist([project_dir])
    if not project_dir.is_dir():
        raise ValueError(f"-p/--project はフォルダを指定してください: {project_dir}")

    js_files = collect_javascript_source_files(project_dir)
    if not js_files:
        raise ValueError(f"JSファイルが見つかりません: {project_dir}")

    output_base = options.output or _resolve_default_vector_output_path(project_dir, "project", project_root)

    logger = _prepare_output_directory_and_logger(output_base)
    logger.info("開始(project): %s", project_dir)

    result = pipeline.run_for_single_scope(
        js_files=js_files,
        output_base=output_base,
        source_root=project_dir,
        jobs=options.jobs,
        logger=logger,
    )

    logger.info("終了(project): success=%s/%s", result.succeeded, result.processed)
    return 0 if result.succeeded == result.processed else 1


def _run_all_project_directories_mode(
    options: CliOptions,
    pipeline: JavaScriptVectorizationPipeline,
    project_root: Path,
) -> int:
    """複数プロジェクト配下の JS ファイル群を均等処理でベクトル化する。

    Args:
        options (CliOptions): CLI オプション。
        pipeline (JavaScriptVectorizationPipeline): ベクトル化実行パイプライン。
        project_root (Path): プロジェクトルート。

    Raises:
        ValueError: 入力がディレクトリでない場合。
        ValueError: 子プロジェクトディレクトリが見つからない場合。
        ValueError: 全プロジェクトから JS ファイルが見つからない場合。

    Returns:
        int: 全ファイル成功時 0、失敗を含む場合 1。
    """
    parent_dir = options.input_path
    assert_input_paths_exist([parent_dir])
    if not parent_dir.is_dir():
        raise ValueError(f"--all はフォルダを指定してください: {parent_dir}")

    project_dirs = collect_child_project_directories(parent_dir)
    if not project_dirs:
        raise ValueError(f"プロジェクトフォルダが見つかりません: {parent_dir}")

    base_output = options.output or _resolve_default_vector_output_path(parent_dir, "all", project_root)
    base_output.mkdir(parents=True, exist_ok=True)

    scope_specs: list[tuple[str, list[Path], Path, Path, logging.Logger]] = []
    for project_dir in project_dirs:
        js_files = collect_javascript_source_files(project_dir)
        if not js_files:
            continue

        output_base = base_output / project_dir.name
        logger = _prepare_output_directory_and_logger(output_base)
        logger.info("開始(all): %s", project_dir)

        scope_specs.append((project_dir.name, js_files, output_base, project_dir, logger))

    if not scope_specs:
        raise ValueError(f"JSファイルが見つかりません: {parent_dir}")

    results = pipeline.run_for_balanced_multi_scope(scopes=scope_specs, jobs=options.jobs)
    overall_success = True
    for project_name, _, _, _, logger in scope_specs:
        result = results[project_name]
        logger.info("終了(all): %s success=%s/%s", project_name, result.succeeded, result.processed)
        if result.succeeded != result.processed:
            overall_success = False

    return 0 if overall_success else 1


def main(argv: list[str] | None = None) -> int:
    """CLI 引数を解釈して実行モードに応じたベクトル化処理を起動する。

    Args:
        argv (list[str] | None): 実行引数。

    Raises:
        None

    Returns:
        int: 実行結果コード。
    """
    options = parse_vectorization_cli_options(argv)
    project_root = Path(__file__).resolve().parents[2]

    hyperparams = load_hyperparams()
    pipeline = JavaScriptVectorizationPipeline(project_root=project_root, hyperparams=hyperparams, mode=options.mode)
    pipeline.validate_required_runtime_files()

    if options.mode == "single":
        return _run_single_file_mode(options, pipeline, project_root)
    if options.mode == "project":
        return _run_project_directory_mode(options, pipeline, project_root)
    return _run_all_project_directories_mode(options, pipeline, project_root)


if __name__ == "__main__":
    sys.exit(main())
