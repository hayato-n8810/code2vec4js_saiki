#!/usr/bin/env python3
"""
類似度上位・下位JSファイル抽出プログラム

calculate_similarity.py で生成されたJSONファイルを読み込み、
類似度（mean）の上位100件と下位100件に対応するJSファイルを
それぞれ top100/ と bottom100/ フォルダに複製します。

JSファイルのソースディレクトリ構造:
  ../target/id_{id_num}_toRepo/{プロジェクト名}/{ファイル名}.js

Output:
  similarity/bachelor/id_{id_num}/top100/*.js
  similarity/bachelor/id_{id_num}/bottom100/*.js
"""

import json
import shutil
import sys
from pathlib import Path
from typing import List, Dict

def copy_js_files(entries: List[Dict], src_root: Path, dest_dir: Path, label: str):
    """
    リスト内のエントリに対応するJSファイルをコピーする
    
    Args:
        entries: JSONから抽出した結果リスト
        src_root: JSファイルが格納されているルートディレクトリ (id_{id_num}_toRepo)
        dest_dir: コピー先ディレクトリ
        label: 表示用ラベル (TOP100 or BOTTOM100)
    """
    if not entries:
        print(f"[{label}] No entries to process.")
        return

    # ディレクトリ作成（存在すればそのまま、なければ作成）
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # 既存ファイルをクリアする場合（必要に応じてコメントアウトを外す）
    # for f in dest_dir.glob("*.js"):
    #     f.unlink()

    success_count = 0
    missing_count = 0

    print(f"[{label}] Copying {len(entries)} files to {dest_dir} ...")

    for entry in entries:
        # JSON内の "path" は vectorsファイルのフルパス
        # 例: .../results/id_1_toRepo/ProjectA/vectors/ProjectA_123.vector
        vector_path = Path(entry['path'])
        
        # ディレクトリ構造からプロジェクト名を取得 (vectorsの親ディレクトリ名)
        project_name = vector_path.parent.parent.name
        
        # JSファイル名を構築
        file_stem = entry['file'] # 例: ProjectA_123
        js_filename = f"{file_stem}.js"
        
        # JSファイルのソースパスを構築
        # target/id_X_toRepo/{ProjectA}/{ProjectA_123}.js
        src_js_path = src_root / project_name / js_filename
        
        dest_js_path = dest_dir / js_filename

        try:
            if src_js_path.exists():
                shutil.copy2(src_js_path, dest_js_path)
                success_count += 1
            else:
                # ソースが見つからない場合
                print(f"[WARN] JS file not found: {src_js_path}", file=sys.stderr)
                missing_count += 1
        except Exception as e:
            print(f"[ERROR] Failed to copy {src_js_path}: {e}", file=sys.stderr)
            missing_count += 1

    print(f"[{label}] Completed. Copied: {success_count}, Missing: {missing_count}")


def process_id(id_num: int, script_dir: Path):
    """
    指定されたIDの処理を実行
    """
    # パス設定
    # JSON入力パス: similarity/bachelor/id_X/id_X_similarity.json
    json_dir = script_dir / 'similarity' / 'bachelor' / f'id_{id_num}'
    json_path = json_dir / f'id_{id_num}_similarity.json'
    
    # JS参照元ルートパス: ../target/id_X_toRepo
    # ※要件に従い 'target' ディレクトリを参照
    js_source_root = script_dir.parent / 'target' / f'id_{id_num}_toRepo'
    
    if not json_path.exists():
        print(f"[SKIP] JSON file not found for ID {id_num}: {json_path}", file=sys.stderr)
        return

    if not js_source_root.exists():
        # targetが存在しない場合、resultsをフォールバックとして確認してみる（オプション）
        fallback_root = script_dir.parent / 'results' / f'id_{id_num}_toRepo'
        if fallback_root.exists():
            print(f"[WARN] 'target' dir not found. Using 'results' dir instead: {fallback_root}")
            js_source_root = fallback_root
        else:
            print(f"[ERROR] Source directory not found: {js_source_root}", file=sys.stderr)
            return

    print(f"\n=== Processing ID {id_num} ===")
    print(f"JSON Input: {json_path}")
    print(f"JS Source : {js_source_root}")

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

    # meanの値で降順ソート（念のため再ソート）
    results.sort(key=lambda x: x['mean'], reverse=True)

    total_files = len(results)
    print(f"Total files in JSON: {total_files}")
    
    # データ数が100未満の場合のハンドリング
    limit = 100
    
    # 上位100件
    top_entries = results[:limit]
    top_dir = json_dir / 'top100'
    copy_js_files(top_entries, js_source_root, top_dir, f"TOP {len(top_entries)}")

    # 下位100件 (昇順にするわけではなく、ソート済みリストの後ろから取得)
    # results[-100:] だとリストの末尾100件が取れる（値が小さい順に並んでいる部分）
    bottom_entries = results[-limit:] if total_files >= limit else results
    # 下位ファイルなので、類似度が低い順（昇順）に並べたい場合は reverse するか検討するが、
    # ここでは「下位100件の集合」を渡す。コピー順序は問わない。
    bottom_dir = json_dir / 'bottom100'
    copy_js_files(bottom_entries, js_source_root, bottom_dir, f"BOTTOM {len(bottom_entries)}")


def main():
    # スクリプトの実行ディレクトリ (ql2vec)
    # calculate_similarity.py と同じ場所にあると仮定
    script_dir = Path(__file__).resolve().parent
    
    for id_num in range(1, 7):
        process_id(id_num, script_dir)

if __name__ == "__main__":
    main()