#!/usr/bin/env python3
"""
Microbenchmark vectors と origin_pattern vectors のコサイン類似度を計算するスクリプト。

要件:
- 入力:
  - /code2vec/ql2vec/outputs/vec/microbenchmark/id_{id}/{project_name}/vectors/slow_{file_id}.vector
  - /code2vec/ql2vec/data/origin_pattern/id_{id}/vectors/*.vector
- 例外条件:
  - 入力 file_id と origin の block_slow_{file_id}.vector の file_id が一致する組み合わせは除外
- 出力:
  - /code2vec/ql2vec/outputs/similarity/microbenchmark/id_{id}_similarity.json
- 出力JSON:
  - total_count
  - results[]: file, cos_similarity, mean, var
  - mean の降順でソート
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


def cos_sim(v1: np.ndarray, v2: np.ndarray) -> float:
    """2つのベクトルのコサイン類似度を返す

    Args:
        v1 (np.ndarray): ベクトル(numpy配列)
        v2 (np.ndarray): ベクトル(numpy配列)

    Returns:
        float: コサイン類似度
    """
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


def load_vector(file_path: Path) -> np.ndarray:
    """.vector ファイルを読み込み，numpy配列として返す

    Args:
        file_path (Path): vectorファイルパス

    Returns:
        np.ndarray: numpy配列
    """
    try:
        content = file_path.read_text(encoding="utf-8").strip()
        if not content:
            return np.array([])
        values = [float(v) for v in content.split()]
        return np.array(values, dtype=float)
    except Exception as e:
        print(f"[ERROR] Failed to load {file_path}: {e}", file=sys.stderr)
        return np.array([])


def calculate_for_id(id_num: int, root_dir: Path) -> Dict[str, Any]:
    """指定した id の類似度計算を実行し，JSON出力用 dict を返す

    Args:
        id_num (int): クエリIDの指定
        root_dir (Path): ルートパス

    Raises:
        FileNotFoundError:
        RuntimeError:

    Returns:
        Dict[str, Any]: 出力用統計情報Dict
    """
    origin_vectors_dir = root_dir / "data" / "origin_pattern" / f"id_{id_num}" / "vectors"
    microbenchmark_vectors_base = root_dir / "outputs" / "vec" / "microbenchmark" / f"id_{id_num}" / "vectors"

    # origin_pattern 側の*.vector を再帰検索して返す
    if not origin_vectors_dir.exists():
        raise FileNotFoundError(f"origin vectors directory not found: {origin_vectors_dir}")
    origin_vectors = sorted(origin_vectors_dir.glob("*.vector"))
    if not origin_vectors:
        raise RuntimeError(f"No valid origin vectors found in: {origin_vectors_dir}")

    # 検出結果側の *.vector を再帰検索して返す
    if not microbenchmark_vectors_base.exists():
        raise FileNotFoundError(f"microbenchmark vectors directory not found: {microbenchmark_vectors_base}")
    microbenchmark_files = sorted(microbenchmark_vectors_base.glob("*.vector"))
    print(f"[INFO] Microbenchmark target vectors found: {len(microbenchmark_files)}")

    # 次元数確認
    expected_dim = load_vector(origin_vectors[0]).size
    print(f"[INFO] Origin vectors loaded: {len(origin_vectors)}")
    print(f"[INFO] Origin vector dimension: {expected_dim}")

    results: List[Dict[str, Any]] = []
    processed = 0
    skipped = 0
    excluded_pairs = 0

    for mf in microbenchmark_files:
        target_file = mf.stem
        target_file_id = target_file.split("_")[-1]

        target_vector = load_vector(mf)
        if target_vector.size == 0:
            skipped += 1
            continue

        if target_vector.size != expected_dim:
            print(f"[WARN] Dimension mismatch: {mf} - {target_vector.size}", file=sys.stderr,)
            skipped += 1
            continue

        similarities: Dict[str, float] = {}
        similarity_values: List[float] = []

        for ov in origin_vectors:
            origin_file = ov.stem
            origin_file_id = origin_file.split("_")[-1]

            origin_vector = load_vector(ov)
            if origin_vector.size == 0:
                skipped += 1
                continue
            # target file_id と origin block_slow file_id が一致する組み合わせは除外
            if (
                target_file_id is not None
                and origin_file_id is not None
                and target_file_id == origin_file_id
            ):
                excluded_pairs += 1
                continue

            sim = cos_sim(origin_vector, target_vector)
            similarities[origin_file] = sim
            similarity_values.append(sim)

        if not similarity_values:
            skipped += 1
            continue

        results.append(
            {
                "file": target_file,
                "cos_similarity": [similarities],
                "mean": float(np.mean(similarity_values)),
                "var": float(np.var(similarity_values)),
            }
        )
        processed += 1

    print(
        f"[INFO] id_{id_num} processed={processed}, skipped={skipped}, excluded_pairs={excluded_pairs}"
    )

    results.sort(key=lambda x: x["mean"], reverse=True)
    return {
        "total_count": len(results),
        "results": results,
    }

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute cosine similarity between microbenchmark vectors and origin_pattern vectors."
        )
    )
    parser.add_argument(
        "--id",
        dest="id_num",
        type=int,
        help="target id number (e.g., 5 for id_5). If omitted, process ids 1..6.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/code2vec/ql2vec"),
        help="root directory of ql2vec (default: /code2vec/ql2vec)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    root_dir: Path = args.root

    id_list = [args.id_num] if args.id_num is not None else list(range(1, 7))

    for id_num in id_list:
        try:
            print(f"\n[INFO] Processing id_{id_num}")
            output_data = calculate_for_id(id_num=id_num, root_dir=root_dir)
            output_path = (
                root_dir / "outputs" / "similarity" / "microbenchmark" / f"id_{id_num}_similarity.json"
            )

            # 保存
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            print(f"[SUCCESS] Saved: {output_path}")
        except Exception as e:
            print(f"[ERROR] id_{id_num} failed: {e}", file=sys.stderr)