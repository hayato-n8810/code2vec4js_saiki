from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# scripts/helper からリポジトリルートのモデル実装を import するために検索パスを補う
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import Config  # noqa: E402
from tensorflow_model import Code2VecModel  # noqa: E402


def _run_vectorize_worker(model_path: Path, c2v_file: Path) -> Path:
    config = Config(set_defaults=True, load_from_args=False, verify=False)
    config.MODEL_LOAD_PATH = str(model_path)
    config.TEST_DATA_PATH = str(c2v_file)
    config.EXPORT_CODE_VECTORS = True
    config.DL_FRAMEWORK = "tensorflow"

    model = Code2VecModel(config)
    try:
        # code2vec_only.py と同じ evaluate() 経由で .vectors を生成する
        try:
            model.evaluate()
        except ZeroDivisionError:
            # OOV による評価指標計算エラーは既存実装どおりベクトル出力成功扱いにする
            pass
    finally:
        model.close_session()

    return Path(f"{c2v_file}.vectors")


def export_code_vectors(model_path: Path, c2v_file: Path, project_root: Path, timeout_sec: int) -> Path:
    command = [
        sys.executable,
        "-m",
        "jscode2vec.scripts.helper.vectorize_engine",
        "--model_path",
        str(model_path),
        "--c2v_file",
        str(c2v_file),
    ]
    env = os.environ.copy()
    try:
        proc = subprocess.run(
            command,
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_sec,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"vectorize timeout after {timeout_sec}s") from exc

    if proc.returncode != 0:
        stderr = proc.stderr.strip() if proc.stderr else ""
        raise RuntimeError(f"vectorize failed ({proc.returncode}): {stderr}")

    return Path(f"{c2v_file}.vectors")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="code2vec vector export worker")
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--c2v_file", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _run_vectorize_worker(model_path=Path(args.model_path), c2v_file=Path(args.c2v_file))
    return 0


if __name__ == "__main__":
    main()
