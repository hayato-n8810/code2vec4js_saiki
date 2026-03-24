#!/usr/bin/env python3
"""
GitHub vectors と origin_pattern vectors のコサイン類似度を計算するスクリプト。

要件:
- 入力:
  - /code2vec/jscode2vec/outputs/vec/github/id_{id}/{project_name}/{project_name}/vectors/{project_name}_{file_id}.vector
  - /code2vec/jscode2vec/data/origin_pattern/id_{id}/vectors/*.vector
- 出力:
  - /code2vec/jscode2vec/outputs/similarity/github/id_{id}_similarity.json
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
	"""2つのベクトルのコサイン類似度を返す。"""
	norm1 = np.linalg.norm(v1)
	norm2 = np.linalg.norm(v2)
	if norm1 == 0 or norm2 == 0:
		return 0.0
	return float(np.dot(v1, v2) / (norm1 * norm2))


def load_vector(file_path: Path) -> np.ndarray:
	""".vector ファイルを読み込み、numpy配列として返す。"""
	try:
		content = file_path.read_text(encoding="utf-8").strip()
		if not content:
			return np.array([])
		values = [float(v) for v in content.split()]
		return np.array(values, dtype=float)
	except Exception as exc:  # pylint: disable=broad-except
		print(f"[ERROR] Failed to load {file_path}: {exc}", file=sys.stderr)
		return np.array([])


def collect_origin_vectors(origin_vectors_dir: Path) -> Dict[str, np.ndarray]:
	"""origin_pattern 側ベクトルを読み込む。キーはファイル名stem。"""
	vector_files = sorted(origin_vectors_dir.glob("*.vector"))
	vectors: Dict[str, np.ndarray] = {}
	for vf in vector_files:
		vec = load_vector(vf)
		if vec.size > 0:
			vectors[vf.stem] = vec
	return vectors


def collect_github_vector_files(github_base_dir: Path) -> List[Path]:
	"""GitHub 側ベクトルファイルを再帰検索して返す。"""
	# 指定構造の vectors ディレクトリ配下の .vector のみ対象
	return sorted(github_base_dir.glob("**/vectors/*.vector"))


def calculate_for_id(
	id_num: int,
	root_dir: Path,
) -> Dict[str, Any]:
	"""指定 id の類似度計算を実行し、JSON出力用dictを返す。"""
	origin_vectors_dir = root_dir / "data" / "origin_pattern" / f"id_{id_num}" / "vectors"
	github_vectors_base = root_dir / "outputs" / "vec" / "github" / f"id_{id_num}"

	if not origin_vectors_dir.exists():
		raise FileNotFoundError(f"origin vectors directory not found: {origin_vectors_dir}")
	if not github_vectors_base.exists():
		raise FileNotFoundError(f"github vectors directory not found: {github_vectors_base}")

	print(f"[INFO] Loading origin vectors: {origin_vectors_dir}")
	origin_vectors = collect_origin_vectors(origin_vectors_dir)
	if not origin_vectors:
		raise RuntimeError(f"No valid origin vectors found in: {origin_vectors_dir}")

	first_origin_name = next(iter(origin_vectors))
	expected_dim = origin_vectors[first_origin_name].size
	print(f"[INFO] Origin vectors loaded: {len(origin_vectors)}")
	print(f"[INFO] Origin vector dimension: {expected_dim}")

	github_files = collect_github_vector_files(github_vectors_base)
	print(f"[INFO] GitHub target vectors found: {len(github_files)}")

	results: List[Dict[str, Any]] = []
	processed = 0
	skipped = 0

	for gf in github_files:
		target_vector = load_vector(gf)
		if target_vector.size == 0:
			skipped += 1
			continue

		if target_vector.size != expected_dim:
			print(
				f"[WARN] Dimension mismatch: {gf} "
				f"(expected {expected_dim}, got {target_vector.size})",
				file=sys.stderr,
			)
			skipped += 1
			continue

		target_stem = gf.stem
		similarities: Dict[str, float] = {}
		similarity_values: List[float] = []

		for origin_name, origin_vec in origin_vectors.items():
			sim = cos_sim(origin_vec, target_vector)
			similarities[origin_name] = sim
			similarity_values.append(sim)

		if not similarity_values:
			skipped += 1
			continue

		results.append(
			{
				"file": target_stem,
				"cos_similarity": [similarities],
				"mean": float(np.mean(similarity_values)),
				"var": float(np.var(similarity_values)),
			}
		)
		processed += 1

	print(f"[INFO] id_{id_num} processed={processed}, skipped={skipped}")

	results.sort(key=lambda x: x["mean"], reverse=True)
	return {
		"total_count": len(results),
		"results": results,
	}


def save_json(data: Dict[str, Any], output_path: Path) -> None:
	"""計算結果をJSON保存する。"""
	output_path.parent.mkdir(parents=True, exist_ok=True)
	with output_path.open("w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False, indent=2)
	print(f"[SUCCESS] Saved: {output_path}")


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Compute cosine similarity between GitHub vectors and origin_pattern vectors."
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
		default=Path("/code2vec/jscode2vec"),
		help="root directory of jscode2vec (default: /code2vec/jscode2vec)",
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
			output_path = root_dir / "outputs" / "similarity" / "github" / f"id_{id_num}_similarity.json"
			save_json(output_data, output_path)
		except Exception as e:
			print(f"[ERROR] id_{id_num} failed: {e}", file=sys.stderr)