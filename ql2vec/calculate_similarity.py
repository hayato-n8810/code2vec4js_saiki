#!/usr/bin/env python3
"""
コサイン類似度計算プログラム

ql2vec/origin_222/vectors配下の全ベクトルファイルと、
指定されたディレクトリ配下の全ベクトルファイルとのコサイン類似度を計算し、
統計情報を含むJSON形式で出力します。

Usage:
    # resultsフォルダ配下の全プロジェクトを対象
    python3 calculate_similarity.py

    # 特定のディレクトリ配下のプロジェクトを対象
    python3 calculate_similarity.py /path/to/target_dir
    
Output:
    similarity/origin_222_similarity.json
"""

import sys
import os
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple


def cos_sim(v1: np.ndarray, v2: np.ndarray) -> float:
    """
    コサイン類似度を計算
    
    Args:
        v1: ベクトル1
        v2: ベクトル2
    
    Returns:
        コサイン類似度 (-1.0 ~ 1.0)
    """
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    
    # ゼロベクトルの場合は0を返す
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return np.dot(v1, v2) / (norm1 * norm2)


def load_vector(filepath: str) -> np.ndarray:
    """
    ベクトルファイルを読み込む
    
    Args:
        filepath: ベクトルファイルのパス
    
    Returns:
        numpy配列
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return np.array([])
            values = [float(val) for val in content.split()]
            return np.array(values, dtype=float)
    except Exception as e:
        print(f"[ERROR] Failed to load {filepath}: {e}", file=sys.stderr)
        return np.array([])


def find_vector_files(base_dir: str) -> List[str]:
    """
    指定ディレクトリ配下の全.vectorファイルを検索
    
    Args:
        base_dir: 検索対象のベースディレクトリ
    
    Returns:
        .vectorファイルのパスリスト
    """
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"[ERROR] Directory not found: {base_dir}", file=sys.stderr)
        return []
    
    vector_files = []
    
    # Case 1: base_dirがvectorsディレクトリそのものの場合
    if base_path.name == "vectors" and base_path.is_dir():
        for vector_file in base_path.glob("*.vector"):
            vector_files.append(str(vector_file))
    
    # Case 2: base_dirが単一プロジェクトディレクトリの場合
    elif (base_path / "vectors").exists():
        vectors_dir = base_path / "vectors"
        for vector_file in vectors_dir.glob("*.vector"):
            vector_files.append(str(vector_file))
    
    # Case 3: base_dirが複数プロジェクトを含むディレクトリの場合
    else:
        for project_dir in base_path.iterdir():
            if not project_dir.is_dir():
                continue
            
            vectors_dir = project_dir / "vectors"
            if not vectors_dir.exists():
                continue
            
            for vector_file in vectors_dir.glob("*.vector"):
                vector_files.append(str(vector_file))
    
    return sorted(vector_files)


def extract_file_id(filepath: str) -> str:
    """
    ファイルパスからプロジェクト名とIDを抽出
    
    Args:
        filepath: ベクトルファイルのパス（例: results/project1/vectors/project1_123.vector）
    
    Returns:
        プロジェクト名_ID（例: project1_123）
    """
    # ファイル名から.vectorを除去
    filename = Path(filepath).stem
    return filename


def calculate_similarities(
    base_vectors_dir: str,
    target_dir: str
) -> List[Dict[str, any]]:
    """
    複数のベースベクトルと全ターゲットベクトルのコサイン類似度を計算
    
    Args:
        base_vectors_dir: ベースベクトルが格納されたディレクトリ
        target_dir: ターゲットディレクトリ
    
    Returns:
        類似度結果のリスト（平均類似度の降順ソート済み）
    """
    # ベースベクトルディレクトリの存在確認
    base_path = Path(base_vectors_dir)
    if not base_path.exists():
        print(f"[ERROR] Base vectors directory not found: {base_vectors_dir}", file=sys.stderr)
        return []
    
    # ベースベクトルファイルを読み込み
    print(f"[INFO] Loading base vectors from: {base_vectors_dir}")
    base_vector_files = sorted(base_path.glob("*.vector"))
    
    if not base_vector_files:
        print(f"[ERROR] No vector files found in {base_vectors_dir}", file=sys.stderr)
        return []
    
    print(f"[INFO] Found {len(base_vector_files)} base vector file(s)")
    
    # ベースベクトルを読み込み
    base_vectors = {}
    for base_file in base_vector_files:
        vector = load_vector(str(base_file))
        if vector.size > 0:
            base_vectors[base_file.stem] = vector
    
    if not base_vectors:
        print(f"[ERROR] Failed to load any base vectors", file=sys.stderr)
        return []
    
    print(f"[INFO] Loaded {len(base_vectors)} base vector(s)")
    first_key = list(base_vectors.keys())[0]
    print(f"[INFO] Base vector dimension: {base_vectors[first_key].size}")
    
    # ターゲットベクトルファイルを検索
    print(f"[INFO] Searching vector files in: {target_dir}")
    vector_files = find_vector_files(target_dir)
    
    if not vector_files:
        print(f"[WARN] No vector files found in {target_dir}")
        return []
    
    print(f"[INFO] Found {len(vector_files)} target vector file(s)")
    
    # 類似度を計算
    results = []
    processed = 0
    skipped = 0
    
    for vector_file in vector_files:
        target_vector = load_vector(vector_file)
        
        # ベクトルが空の場合はスキップ
        if target_vector.size == 0:
            skipped += 1
            continue
        
        # 次元チェック（最初のベースベクトルと比較）
        expected_dim = base_vectors[first_key].size
        if target_vector.size != expected_dim:
            print(f"[WARN] Dimension mismatch: {vector_file} "
                  f"(expected {expected_dim}, got {target_vector.size})", 
                  file=sys.stderr)
            skipped += 1
            continue
        
        # 各ベースベクトルとのコサイン類似度を計算
        similarities = {}
        similarity_values = []
        
        for base_name, base_vector in base_vectors.items():
            similarity = cos_sim(base_vector, target_vector)
            similarities[base_name] = float(similarity)
            similarity_values.append(similarity)
        
        # 統計情報を計算
        mean_similarity = float(np.mean(similarity_values))
        var_similarity = float(np.var(similarity_values))
        
        # ファイルIDを抽出
        file_id = extract_file_id(vector_file)
        
        results.append({
            "file": file_id,
            "cos_similarity": [similarities],
            "mean": mean_similarity,
            "var": var_similarity,
            "path": vector_file
        })
        
        processed += 1
        
        # 進捗表示（100件ごと）
        if processed % 100 == 0:
            print(f"[PROGRESS] Processed {processed}/{len(vector_files)} files...")
    
    print(f"[INFO] Processed: {processed}, Skipped: {skipped}")
    
    # 平均コサイン類似度の降順でソート
    results.sort(key=lambda x: x["mean"], reverse=True)
    
    return results


def save_results(results: List[Dict], output_path: str):
    """
    結果をJSON形式で保存
    
    Args:
        results: 類似度結果のリスト
        output_path: 出力ファイルパス
    """
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        "total_count": len(results),
        "results": [
            {
                "file": r["file"],
                "cos_similarity": r["cos_similarity"],
                "mean": r["mean"],
                "var": r["var"]
            }
            for r in results
        ]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"[SUCCESS] Results saved to: {output_path}")
    print(f"[INFO] Total results: {len(results)}")
    
    if results:
        print(f"[INFO] Highest mean similarity: {results[0]['mean']:.6f} ({results[0]['file']})")
        print(f"[INFO] Lowest mean similarity: {results[-1]['mean']:.6f} ({results[-1]['file']})")


def main():
    """
    メイン処理
    """
    # スクリプトの実行ディレクトリを取得
    script_dir = Path("/code2vec/ql2vec")
    
    # ベースベクトルディレクトリ（固定）
    base_vectors_dir = script_dir / 'origin_222' / 'vectors'
    
    # ターゲットディレクトリの決定
    if len(sys.argv) >= 2:
        # 引数がある場合: 指定されたディレクトリ
        target_dir = sys.argv[1]
        print(f"[INFO] Target directory (from argument): {target_dir}")
    else:
        # 引数がない場合: resultsフォルダ配下の全プロジェクト
        # スクリプトの親ディレクトリ（プロジェクトルート）から相対パス
        target_dir = str(script_dir.parent / 'results')
        print(f"[INFO] Target directory (default): {target_dir}")
    
    # ベースベクトルディレクトリの存在確認
    if not base_vectors_dir.exists():
        print(f"[ERROR] Base vectors directory not found: {base_vectors_dir}", file=sys.stderr)
        print(f"[INFO] Please ensure the directory exists: {base_vectors_dir}")
        sys.exit(1)
    
    # 類似度を計算
    results = calculate_similarities(str(base_vectors_dir), target_dir)
    
    if not results:
        print(f"[ERROR] No valid results generated", file=sys.stderr)
        sys.exit(1)
    
    # 出力ファイル名を生成（origin_222ベース固定）
    output_dir = script_dir / 'similarity'
    output_path = output_dir / 'result_222_similarity.json'
    
    # 結果を保存
    save_results(results, str(output_path))
    
    # 上位10件を表示
    print(f"\n[TOP 10 SIMILAR FILES (by mean similarity)]")
    for i, result in enumerate(results[:10], 1):
        print(f"  {i:2d}. {result['file']:50s} mean={result['mean']:.6f} var={result['var']:.6f}")


if __name__ == "__main__":
    main()
