from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HyperParams:
    """JS ベクトル化処理で参照する code2vec ハイパーパラメータを表現する。

    Args:
        max_contexts (int): 1 サンプルあたりの最大 context 数。
        word_vocab_size (int): 単語語彙サイズ。
        path_vocab_size (int): パス語彙サイズ。
        target_vocab_size (int): ターゲット語彙サイズ。
        max_path_length (int): 抽出パス最大長。
        max_path_width (int): 抽出パス最大幅。
        dataset_name (str): データセット名。
        model_path (str): 推論モデルパス。
        word_histo (str): 単語ヒストグラムパス。
        path_histo (str): パスヒストグラムパス。
        target_histo (str): ターゲットヒストグラムパス。

    Raises:
        None

    Returns:
        HyperParams: code2vec 実行パラメータ。
    """
    max_contexts: int
    word_vocab_size: int
    path_vocab_size: int
    target_vocab_size: int
    max_path_length: int
    max_path_width: int
    dataset_name: str
    model_path: str
    word_histo: str
    path_histo: str
    target_histo: str


# JSファイルのベクトル化処理で利用するハイパーパラメータはこのファイルのみを参照する
HYPER_PARAMS = HyperParams(
    max_contexts=200,
    word_vocab_size=1301136,
    path_vocab_size=911417,
    target_vocab_size=261245,
    max_path_length=8,
    max_path_width=2,
    dataset_name="js_dataset_min5",
    model_path="/code2vec/models/js_dataset_min5/saved_model_iter19.release",
    word_histo="/code2vec/data/js_dataset_min5/js_dataset_min5.histo.ori.c2v",
    path_histo="/code2vec/data/js_dataset_min5/js_dataset_min5.histo.path.c2v",
    target_histo="/code2vec/data/js_dataset_min5/js_dataset_min5.histo.tgt.c2v",
)


# 運用制御パラメータ
EXTRACT_TIMEOUT_SEC = 480
INFER_TIMEOUT_SEC = 900
PREPROCESS_MAX_RETRIES = 2
MIN_FILES_FOR_SHM = 2
MAX_INFER_PARALLELISM = 16


def load_hyperparams() -> HyperParams:
    """固定定義された JS ベクトル化用ハイパーパラメータを返す。

    Args:
        None

    Raises:
        None

    Returns:
        HyperParams: JS ベクトル化で利用する固定ハイパーパラメータ。
    """
    return HYPER_PARAMS