#!/usr/bin/env python3
"""
テストファイル以外の類似度上位JSファイル抽出プログラム

similarity/bachelor/id_X/id_X_similarity.jsonを読み込み、
outputs/extracted_code/id_X/{プロジェクト名}_code.jsonからfile_pathを取得し、
file_pathに"test"や"spec"が含まれていないファイルについて、
類似度上位100件をsimilarity/bachelor/id_X/notTest/にコピーします。

出力ファイル名形式:
  {順位}_{対応するjsファイル名}.js

Output:
  similarity/bachelor/id_{id_num}/notTest/{rank}_{filename}.js
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional


def load_code_json(code_json_dir: Path, project_name: str) -> Optional[Dict[int, str]]:
    """
    outputs/extracted_code/id_X/{プロジェクト名}_code.jsonを読み込み、
    idをキーとしてfile_pathを値とする辞書を返す
    
    Args:
        code_json_dir: outputs/extracted_code/id_X ディレクトリ
        project_name: プロジェクト名
    
    Returns:
        {id: file_path} の辞書、ファイルが見つからない場合はNone
    """
    code_json_path = code_json_dir / f"{project_name}_code.json"
    
    if not code_json_path.exists():
        return None
    
    try:
        with open(code_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
            # idをキーとしてfile_pathを値とする辞書を作成
            return {item['id']: item['file_path'] for item in results}
    except Exception as e:
        print(f"[WARN] Failed to load {code_json_path}: {e}", file=sys.stderr)
        return None


def is_test_file(file_path: str) -> bool:
    """
    file_pathに"test"または"spec"が含まれているかチェック（大文字小文字無視）
    
    Args:
        file_path: ファイルパス文字列
    
    Returns:
        テストファイルならTrue
    """
    lower_path = file_path.lower()
    return 'test' in lower_path or 'spec' in lower_path


def copy_js_files_not_test(
    entries: List[Dict],
    src_root: Path,
    dest_dir: Path,
    code_json_dir: Path,
    log_file,
    limit: int = 100
):
    """
    テストファイル以外のJSファイルを順位付きでコピーする
    
    Args:
        entries: meanで降順ソート済みの結果リスト
        src_root: JSファイルが格納されているルートディレクトリ
        dest_dir: コピー先ディレクトリ
        code_json_dir: outputs/extracted_code/id_X ディレクトリ
        log_file: ログファイルハンドル
        limit: コピーする最大件数
    """
    def log_print(msg: str):
        """コンソールとログファイル両方に出力"""
        print(msg)
        log_file.write(msg + '\n')
    
    # ディレクトリ作成
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # 既存ファイルをクリア
    for f in dest_dir.glob("*.js"):
        f.unlink()

    # プロジェクトごとのcode.jsonキャッシュ
    code_json_cache: Dict[str, Optional[Dict[int, str]]] = {}
    
    success_count = 0
    skip_test_count = 0
    missing_count = 0
    rank = 0  # 元のリスト内での順位（1始まり）

    log_print(f"[notTest] Finding non-test files (limit: {limit}) ...")

    for entry in entries:
        rank += 1
        
        # file名をパース: {プロジェクト名}_{ファイルID}
        file_stem = entry['file']  # 例: ProjectA_123
        parts = file_stem.rsplit('_', 1)
        
        if len(parts) != 2:
            print(f"[WARN] Invalid file format: {file_stem}", file=sys.stderr)
            missing_count += 1
            continue
        
        project_name = parts[0]
        try:
            file_id = int(parts[1])
        except ValueError:
            print(f"[WARN] Invalid file ID: {file_stem}", file=sys.stderr)
            missing_count += 1
            continue
        
        # code.jsonをキャッシュから取得または読み込み
        if project_name not in code_json_cache:
            code_json_cache[project_name] = load_code_json(code_json_dir, project_name)
        
        id_to_filepath = code_json_cache[project_name]
        
        if id_to_filepath is None:
            # code.jsonが見つからない場合はスキップ
            missing_count += 1
            continue
        
        if file_id not in id_to_filepath:
            # 対応するIDが見つからない
            missing_count += 1
            continue
        
        file_path = id_to_filepath[file_id]
        
        # テストファイルかどうかチェック
        if is_test_file(file_path):
            skip_test_count += 1
            continue
        
        # JSファイルのソースパスを構築
        js_filename = f"{file_stem}.js"
        src_js_path = src_root / project_name / js_filename
        
        # コピー先ファイル名: {順位}_{元のファイル名}.js
        dest_filename = f"{rank}_{file_stem}.js"
        dest_js_path = dest_dir / dest_filename

        try:
            if src_js_path.exists():
                shutil.copy2(src_js_path, dest_js_path)
                success_count += 1
                log_print(f"  [{success_count}/{limit}] Rank {rank}: {dest_filename}")
                log_print(f"      file_path: {file_path}")
                
                if success_count >= limit:
                    break
            else:
                print(f"[WARN] JS file not found: {src_js_path}", file=sys.stderr)
                log_file.write(f"[WARN] JS file not found: {src_js_path}\n")
                missing_count += 1
        except Exception as e:
            print(f"[ERROR] Failed to copy {src_js_path}: {e}", file=sys.stderr)
            log_file.write(f"[ERROR] Failed to copy {src_js_path}: {e}\n")
            missing_count += 1

    log_print(f"[notTest] Completed. Copied: {success_count}, Skipped(test): {skip_test_count}, Missing: {missing_count}")


def process_id(id_num: int, script_dir: Path):
    """
    指定されたIDの処理を実行
    """
    # パス設定
    json_dir = script_dir / 'similarity' / 'bachelor' / f'id_{id_num}'
    json_path = json_dir / f'id_{id_num}_similarity.json'
    
    # JS参照元ルートパス
    js_source_root = script_dir.parent / 'target' / f'id_{id_num}_toRepo'
    
    # outputs/extracted_code/id_X ディレクトリ
    pattern_id = {1: 10, 2: 18, 3: 222, 4: 827, 5: 11, 6: 874}
    pid = pattern_id[id_num]
    code_json_dir = script_dir.parent / 'outputs' / 'extracted_code' / f'id_{pid}'
    
    if not json_path.exists():
        print(f"[SKIP] JSON file not found for ID {id_num}: {json_path}", file=sys.stderr)
        return

    if not js_source_root.exists():
        # targetが存在しない場合、resultsをフォールバック
        fallback_root = script_dir.parent / 'results' / f'id_{id_num}_toRepo'
        if fallback_root.exists():
            print(f"[WARN] 'target' dir not found. Using 'results' dir instead: {fallback_root}")
            js_source_root = fallback_root
        else:
            print(f"[ERROR] Source directory not found: {js_source_root}", file=sys.stderr)
            return

    if not code_json_dir.exists():
        print(f"[SKIP] Code JSON directory not found for ID {id_num}: {code_json_dir}", file=sys.stderr)
        return

    # ログファイルパス
    log_path = json_dir / f'id_{id_num}_notTest.log'

    print(f"\n=== Processing ID {id_num} ===")
    print(f"JSON Input : {json_path}")
    print(f"JS Source  : {js_source_root}")
    print(f"Code JSONs : {code_json_dir}")
    print(f"Log File   : {log_path}")

    # JSON読み込み
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            results = data.get('results', [])
    except Exception as e:
        print(f"[ERROR] Failed to load JSON: {e}", file=sys.stderr)
        return

    if not results:
        print("[WARN] No results found in JSON.")
        return

    # meanの値で降順ソート（類似度が高い順）
    results.sort(key=lambda x: x['mean'], reverse=True)

    total_files = len(results)
    print(f"Total files in JSON: {total_files}")
    
    # notTestディレクトリにコピー（ログファイル付き）
    not_test_dir = json_dir / 'notTest'
    
    with open(log_path, 'w', encoding='utf-8') as log_file:
        log_file.write(f"=== Processing ID {id_num} ===\n")
        log_file.write(f"JSON Input : {json_path}\n")
        log_file.write(f"JS Source  : {js_source_root}\n")
        log_file.write(f"Code JSONs : {code_json_dir}\n")
        log_file.write(f"Total files in JSON: {total_files}\n\n")
        
        copy_js_files_not_test(results, js_source_root, not_test_dir, code_json_dir, log_file, limit=100)


def main():
    script_dir = Path(__file__).resolve().parent
    
    for id_num in range(1, 7):
        process_id(id_num, script_dir)


if __name__ == "__main__":
    main()
