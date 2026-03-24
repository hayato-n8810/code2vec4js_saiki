from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# scripts/helper からリポジトリルートのモデル実装を import するために検索パスを補う
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import Config  # noqa: E402


def run_code2vec_vector_export_worker(model_path: Path, c2v_file: Path) -> Path:
    """Code2VecModel を使って単一 c2v 入力からベクトルを書き出す。

    Args:
        model_path (Path): code2vec モデルパス。
        c2v_file (Path): 入力 .c2v ファイルパス。

    Raises:
        None

    Returns:
        Path: 生成される .vectors ファイルパス。
    """
    config = Config(set_defaults=True, load_from_args=False, verify=False)
    config.MODEL_LOAD_PATH = str(model_path)
    config.TEST_DATA_PATH = str(c2v_file)
    config.EXPORT_CODE_VECTORS = True
    config.DL_FRAMEWORK = "tensorflow"

    # code2vec_only.py と同様に実行時にモデル実装を読み込む
    from tensorflow_model import Code2VecModel  # noqa: E402

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


def export_code_vectors_with_subprocess(
    model_path: Path,
    c2v_file: Path,
    project_root: Path,
    timeout_sec: int,
) -> Path:
    """分離プロセスでベクトル出力ワーカーを実行して .vectors を生成する。

    Args:
        model_path (Path): code2vec モデルパス。
        c2v_file (Path): 入力 .c2v ファイルパス。
        project_root (Path): 実行時カレントを合わせるプロジェクトルート。
        timeout_sec (int): タイムアウト秒数。

    Raises:
        RuntimeError: ワーカー実行失敗またはタイムアウト時。

    Returns:
        Path: 生成される .vectors ファイルパス。
    """
    command = [
        sys.executable,
        "-m",
        "jscode2vec.scripts.helper.vectorization.c2v_vector_export_worker",
        "--model_path",
        str(model_path),
        "--c2v_file",
        str(c2v_file),
    ]
    env = os.environ.copy()
    # process_single_file_worker.sh と同様に TensorFlow ログ抑制・GPUメモリ成長を設定する
    env.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    env.setdefault("TF_FORCE_GPU_ALLOW_GROWTH", "true")
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
        if proc.returncode == 124:
            raise RuntimeError(f"vectorize timeout (>{timeout_sec}s)")
        if proc.returncode in {137, 143, -9}:
            raise RuntimeError(f"vectorize killed (OOM or forced kill): code={proc.returncode}")
        raise RuntimeError(f"vectorize failed ({proc.returncode}): {stderr}")

    return Path(f"{c2v_file}.vectors")


def parse_vector_export_worker_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """ベクトル出力ワーカーの CLI 引数を解析する。

    Args:
        argv (list[str] | None): 解析対象のコマンドライン引数。

    Raises:
        None

    Returns:
        argparse.Namespace: 解析済み引数。
    """
    parser = argparse.ArgumentParser(description="code2vec vector export worker")
    parser.add_argument("--model_path", required=True)
    parser.add_argument("--c2v_file", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI 引数を受け取りベクトル出力ワーカー本体を起動する。

    Args:
        argv (list[str] | None): 実行引数。

    Raises:
        None

    Returns:
        int: 正常終了時は 0。
    """
    args = parse_vector_export_worker_arguments(argv)
    run_code2vec_vector_export_worker(model_path=Path(args.model_path), c2v_file=Path(args.c2v_file))
    return 0


if __name__ == "__main__":
    main()
