#!/usr/bin/env python3
"""
codeQLにて作成したコードスニペットのJsonファイルからJSファイルを抽出する

Usage:
    # 単一のJSONファイルから抽出
    python3 extract_code_snippets.py <input_json_file> <output_dir>
    # github配下の全プロジェクトから抽出
    python3 extract_code_snippets.py -github
    # microbenchmark配下の全Jsonファイルから抽出
    python3 extract_code_snippets.py -mb
    
Example:
    python3 extract_code_snippets.py ql2vec/data/microbenchmark/id_1_code.json ql2vec/targets/microbenchmark/id_1
    python3 extract_code_snippets.py -github
    python3 extract_code_snippets.py -mb
"""

import argparse
import json
import re
import sys
from pathlib import Path

def json_to_js(json_file: Path, output_dir: Path, name_resolver, log_label: str) -> int:
    """Jsonファイルからコードスニペットを抽出してJSファイルとして保存する

    Args:
        json_file (Path): 入力Jsonファイル
        output_dir (Path): 出力先ディレクトリ
        name_resolver (_type_): resultオブジェクトから出力ファイル名を解決する関数
        log_label (str): ログ出力用のラベル

    Returns:
        int: 保存したファイル数
    """
    
    print(f"\n[PROCESSING] {json_file}")
    print(f"  Target: {log_label}")

    results = []
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON: {json_file.name}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] Failed to read file: {json_file.name}: {e}", file=sys.stderr)

    results = data.get("results", [])
    if not results:
        print(f"  [DONE] No results found in {json_file.name}")
        return 0

    saved_count = 0
    for result in results:
        output_filename = name_resolver(result)
        code_snippet = result.get("code_snippet", "")

        if not output_filename:
            print("  [WARN] Unable to resolve output filename, skipping")
            continue

        if not code_snippet:
            print(f"  [WARN] Empty code_snippet for id={result.get('id')}, skipping")
            continue

        # 最初のスニペットを保存する前にディレクトリを作成する
        if saved_count == 0:
            output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / output_filename

        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(code_snippet)
                f.write("\n")
            saved_count += 1
        except Exception as e:
            print(f"  [ERROR] Failed to write {output_filename}: {e}", file=sys.stderr)
            continue

    # スニペットが1つも保存されなかった場合，作成したディレクトリを削除
    if saved_count == 0 and output_dir.exists():
        output_dir.rmdir()

    print(f"  [DONE] Saved {saved_count} snippet(s) to {output_dir} ({log_label})")
    return saved_count


def single_mode(input_json_file: str, output_dir: str) -> int:
    """単一Jsonファイルを対象とした処理

    Args:
        input_json_file (str): 入力Jsonファイル
        output_dir (str): 出力先フォルダ

    Returns:
        int: 保存ファイル数
    """
    input_path = Path(input_json_file)
    output_path = Path(output_dir)

    if not input_path.exists() or not input_path.is_file():
        print(f"[ERROR] Input JSON file not found: {input_json_file}", file=sys.stderr)
        return 1

    project_name = input_path.stem.replace("_code", "")
    project_output_dir = output_path / project_name

    # 抽出実行
    saved_count = json_to_js(
        input_path,
        project_output_dir,
        lambda result: f"{project_name}_{result.get('id')}.js" if result.get("id") is not None else None,
        project_name,
    )
    print(f"\n[ALL DONE] Extracted {saved_count} code snippets to {project_output_dir}")
    return 0


def github_mode() -> int:
    """/ql2vec/data/github 配下のJsonファイル全てを対象とした処理

    Returns:
        int: 保存ファイル数
    """
    input_base = Path("/code2vec/ql2vec/data/github")
    output_base = Path("/code2vec/ql2vec/targets/github")

    if not input_base.exists():
        print(f"[ERROR] GitHub input directory not found: {input_base}", file=sys.stderr)
        return 1

    pattern_dirs = sorted(p for p in input_base.glob("id_*") if p.is_dir())
    if not pattern_dirs:
        print(f"[WARN] No pattern directories found under {input_base}")
        return 0

    total_projects = 0
    total_snippets = 0

    for pattern_dir in pattern_dirs:
        pattern_id = pattern_dir.name
        json_files = sorted(pattern_dir.glob("*_code.json"))

        if not json_files:
            print(f"[WARN] No *_code.json in {pattern_dir}")
            continue

        print(f"\n[INFO] Pattern: {pattern_id}, Files: {len(json_files)}")

        for json_file in json_files:
            project_name = json_file.stem.replace("_code", "")
            project_output_dir = output_base / pattern_id / project_name
            # 抽出実行
            saved_count = json_to_js(
                json_file,
                project_output_dir,
                lambda result, pn=project_name: f"{pn}_{result.get('id')}.js" if result.get("id") is not None else None,
                f"{pattern_id}/{project_name}",
            )

            if saved_count > 0:
                total_projects += 1
                total_snippets += saved_count

    print(
        f"\n[ALL DONE] Extracted {total_snippets} code snippets "
        f"across {total_projects} project(s) into {output_base}"
    )
    return 0

def microbenchmark_mode() -> int:
    """/ql2vec/data/microbenchmark 配下のJsonファイル全てを対象とした処理

    Returns:
        int: 保存ファイル数
    """
    input_base = Path("/code2vec/ql2vec/data/microbenchmark")
    output_base = Path("/code2vec/ql2vec/targets/microbenchmark")

    if not input_base.exists():
        print(f"[ERROR] Microbenchmark input directory not found: {input_base}", file=sys.stderr)
        return 1

    json_files = sorted(input_base.glob("id_*_code.json"))
    if not json_files:
        print(f"[WARN] No id_*_code.json found under {input_base}")
        return 0

    total_snippets = 0

    print(f"\n[INFO] Microbenchmark files: {len(json_files)}")

    for json_file in json_files:
        match = re.match(r"^(id_\d+)_code$", json_file.stem)
        if not match:
            print(f"[WARN] Skip unexpected file name: {json_file.name}")
            continue

        pattern_id = match.group(1)
        target_dir = output_base / pattern_id
        saved_count = json_to_js(
            json_file,
            target_dir,
            lambda result: Path(result.get("file_path", "")).name if result.get("file_path") else None,
            pattern_id,
        )
        total_snippets += saved_count

    print(
        f"\n[ALL DONE] Extracted {total_snippets} code snippets "
        f"into {output_base}"
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract JS snippets from *_code JSON files"
    )
    parser.add_argument(
        "input_json_file",
        nargs="?",
        help="Path to {project_name}_code.json or compatible JSON file",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        help="Output base directory",
    )
    parser.add_argument(
        "-github",
        action="store_true",
        help=(
            "Process all files under /code2vec/ql2vec/data/github/id_*/ and output to "
            "/code2vec/targets/github/id_*/"
        ),
    )
    parser.add_argument(
        "-mb",
        action="store_true",
        help=(
            "Process /code2vec/ql2vec/data/microbenchmark/id_{id}_code.json and output to "
            "/code2vec/ql2vec/targets/microbenchmark/id_{id}/ as {file_path}.js"
        ),
    )

    args = parser.parse_args()

    selected_mode_count = sum([args.github, args.mb])
    if selected_mode_count > 1:
        print("[ERROR] Specify only one mode flag: -github or -mb", file=sys.stderr)
        sys.exit(1)

    if args.github:
        if args.input_json_file or args.output_dir:
            print("[ERROR] -github mode does not accept positional arguments", file=sys.stderr)
            sys.exit(1)
        sys.exit(github_mode())

    if args.mb:
        if args.input_json_file or args.output_dir:
            print("[ERROR] -mb mode does not accept positional arguments", file=sys.stderr)
            sys.exit(1)
        sys.exit(microbenchmark_mode())

    if not args.input_json_file or not args.output_dir:
        parser.print_usage(sys.stderr)
        print(
            "[ERROR] Either provide <input_json_file> <output_dir> or use -github/-mb",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(single_mode(args.input_json_file, args.output_dir))
