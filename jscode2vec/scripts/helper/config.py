from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HyperParams:
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


def load_hyperparams() -> HyperParams:
    return HYPER_PARAMS