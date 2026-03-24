#!/usr/bin/env python3
from __future__ import annotations

import logging
import sys
from pathlib import Path

from helper.cli_options import CliOptions, parse_cli
from helper.config import load_hyperparams
from helper.pipeline import VectorizePipeline, collect_js_files, collect_project_dirs, ensure_paths_exist


def _resolve_default_output_path(input_path: Path, mode: str, project_root: Path) -> Path:
    # 既定出力は target セグメントを outputs/vec に置換する
    parts = list(input_path.parts)
    replaced = False
    for idx, part in enumerate(parts):
        if part == "target":
            parts[idx] = "outputs"
            parts.insert(idx + 1, "vec")
            replaced = True
            break

    if replaced:
        replaced_path = Path(*parts)
        if mode == "single":
            return replaced_path.parent / input_path.stem
        return replaced_path

    # target が無い場合は outputs/vec/others に退避する
    if mode == "single":
        return project_root / "jscode2vec" / "outputs" / "vec" / "others" / input_path.stem
    return project_root / "jscode2vec" / "outputs" / "vec" / "others" / input_path.name


def _build_logger(log_path: Path) -> logging.Logger:
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


def _run_single(options: CliOptions, pipeline: VectorizePipeline, project_root: Path) -> int:
    input_file = options.input_path
    ensure_paths_exist([input_file])
    if not input_file.is_file() or input_file.suffix != ".js":
        raise ValueError(f"-s/--single はJSファイルを指定してください: {input_file}")

    output_base = options.output or _resolve_default_output_path(input_file, "single", project_root)
    output_base.mkdir(parents=True, exist_ok=True)

    logger = _build_logger(output_base / "process.log")
    logger.info("開始(single): %s", input_file)

    result = pipeline.run_scope(
        js_files=[input_file],
        output_base=output_base,
        source_root=input_file.parent,
        jobs=1,
        logger=logger,
    )

    logger.info("終了(single): success=%s/%s", result.succeeded, result.processed)
    return 0 if result.succeeded == result.processed else 1


def _run_project(options: CliOptions, pipeline: VectorizePipeline, project_root: Path) -> int:
    project_dir = options.input_path
    ensure_paths_exist([project_dir])
    if not project_dir.is_dir():
        raise ValueError(f"-p/--project はフォルダを指定してください: {project_dir}")

    js_files = collect_js_files(project_dir)
    if not js_files:
        raise ValueError(f"JSファイルが見つかりません: {project_dir}")

    output_base = options.output or _resolve_default_output_path(project_dir, "project", project_root)
    output_base.mkdir(parents=True, exist_ok=True)

    logger = _build_logger(output_base / "process.log")
    logger.info("開始(project): %s", project_dir)

    result = pipeline.run_scope(
        js_files=js_files,
        output_base=output_base,
        source_root=project_dir,
        jobs=options.jobs,
        logger=logger,
    )

    logger.info("終了(project): success=%s/%s", result.succeeded, result.processed)
    return 0 if result.succeeded == result.processed else 1


def _run_all(options: CliOptions, pipeline: VectorizePipeline, project_root: Path) -> int:
    parent_dir = options.input_path
    ensure_paths_exist([parent_dir])
    if not parent_dir.is_dir():
        raise ValueError(f"--all はフォルダを指定してください: {parent_dir}")

    project_dirs = collect_project_dirs(parent_dir)
    if not project_dirs:
        raise ValueError(f"プロジェクトフォルダが見つかりません: {parent_dir}")

    base_output = options.output or _resolve_default_output_path(parent_dir, "all", project_root)
    base_output.mkdir(parents=True, exist_ok=True)

    scope_specs: list[tuple[str, list[Path], Path, Path, logging.Logger]] = []
    for project_dir in project_dirs:
        js_files = collect_js_files(project_dir)
        if not js_files:
            continue

        output_base = base_output / project_dir.name
        output_base.mkdir(parents=True, exist_ok=True)

        logger = _build_logger(output_base / "process.log")
        logger.info("開始(all): %s", project_dir)

        scope_specs.append((project_dir.name, js_files, output_base, project_dir, logger))

    if not scope_specs:
        raise ValueError(f"JSファイルが見つかりません: {parent_dir}")

    results = pipeline.run_scopes_balanced(scope_specs=scope_specs, jobs=options.jobs)
    overall_success = True
    for project_name, _, _, _, logger in scope_specs:
        result = results[project_name]
        logger.info("終了(all): %s success=%s/%s", project_name, result.succeeded, result.processed)
        if result.succeeded != result.processed:
            overall_success = False

    return 0 if overall_success else 1


def main(argv: list[str] | None = None) -> int:
    options = parse_cli(argv)
    project_root = Path(__file__).resolve().parents[2]

    hyperparams = load_hyperparams()
    pipeline = VectorizePipeline(project_root=project_root, hyperparams=hyperparams, mode=options.mode)
    pipeline.validate_runtime_inputs()

    if options.mode == "single":
        return _run_single(options, pipeline, project_root)
    if options.mode == "project":
        return _run_project(options, pipeline, project_root)
    return _run_all(options, pipeline, project_root)


if __name__ == "__main__":
    sys.exit(main())
