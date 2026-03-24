# jscode2vec - Query to Vector Pipeline

このディレクトリには、JavaScriptコード（*.js）を code2vec の入力形式に変換し、学習済みモデルで `.vector` を生成するためのパイプラインスクリプトが含まれています。

特徴:

- **Shared Memory (SHM) ヒストグラム**: 学習時ヒストグラムを 1 回だけ RAM にロードし、並列ワーカが共有（ディスクI/O/重複メモリを削減）
- **並列処理**: プロジェクト単位 / ファイル単位の2種類の並列実行スクリプトを提供
- **出力**: `results/` 配下に `.c2v` / `.vector` / ログを保存

## ファイル構成

### メインスクリプト

- **`jscode2vec_parallel.sh`** - 複数プロジェクトを**プロジェクト単位**で並列処理（SHMヒストグラム）
- **`process_project_worker.sh`** - `jscode2vec_parallel.sh` のワーカ（1プロジェクト内の *.js を順次処理）
- **`jscode2vec_file_parallel_shm.sh`** - *.js を**ファイル単位**で並列処理（SHMヒストグラム）
- **`process_single_file_worker.sh`** - `jscode2vec_file_parallel_shm.sh` のワーカ（1ファイル処理）
- **`jscode2vec_one_project.sh`** - 単一ディレクトリ（=1プロジェクト相当）を逐次処理

### サポートスクリプト

- **`code2vec_only.py`** - code2vecモデルを使用してコードベクトルをエクスポート
- **`preprocess_test.py`** - テストデータを前処理してcode2vec形式に変換
- **`preload_histograms.py`** - ヒストグラムの事前ロード・キャッシュ化（`histogram_cache.pkl` を作成）
- **`histogram_server.py`** - ヒストグラムを Shared Memory に載せて共有するサーバ（各並列スクリプトが自動起動/再利用）
- **`extract_code_snippets.py`** - JSONファイルからコードスニペットを抽出
- **`build_trainHist.sh`** - 学習用ヒストグラムデータを構築
- **`calculate_similarity.py`** - ベースベクトルとの類似度（コサイン）を計算してJSON出力（id_1〜id_6 を固定で処理）
- **`similarity_sort_file.py`** - 類似度上位/下位のJSファイルをコピー

## Docker環境でのパス構造

```
/code2vec/                      # プロジェクトルート（./がマウント）
├── jscode2vec/                     # このディレクトリ
│   ├── jscode2vec_parallel.sh
│   ├── jscode2vec_file_parallel_shm.sh
│   ├── process_project_worker.sh
│   ├── process_single_file_worker.sh
│   ├── histogram_server.py
│   ├── code2vec_only.py
│   └── ...
├── data/                       # データディレクトリ
│   └── js_dataset_min5/
│       ├── *.histo.*.c2v      # ヒストグラムファイル
│       └── histogram_cache.pkl # キャッシュファイル
├── models/                     # モデルディレクトリ
│   └── js_dataset_min5/
│       └── saved_model_iter19.release
├── JSExtractor/                # JavaScript抽出器
│   └── extract.py
└── results/                    # 出力ディレクトリ
  ├── {project_name}/
  │   ├── c2v/               # .c2v / .raw / context_count.json
  │   ├── vectors/           # .vector
  │   └── process.log        # ログ
  └── {base_dir_name}/{project_name}/  # ファイル単位並列の出力（後述）

/data/                          # 外部データマウントポイント
└── sampling/train/             # 学習データ（build_trainHist.sh用）

/code2vec/jscode2vec/similarity/    # 類似度計算結果（bachelor配下）
└── bachelor/id_{n}/id_{n}_similarity.json
```

## 使用方法

### Docker環境での実行

```bash
# Dockerコンテナ内で実行
docker exec -it code2vec4js bash

# 並列処理（複数プロジェクト / プロジェクト単位・推奨）
cd /code2vec/jscode2vec
./jscode2vec_parallel.sh /absolute/path/to/target_dir_js [max_parallel_jobs]

# 並列処理（ファイル単位：大量ファイル向け）
./jscode2vec_file_parallel_shm.sh /absolute/path/to/target_dir_js [max_parallel_jobs]

# 単一プロジェクト処理
./jscode2vec_one_project.sh /absolute/path/to/project_dir

# ヒストグラムの事前ロード（任意・初回のみ推奨）
python3 /code2vec/jscode2vec/preload_histograms.py --dataset js_dataset_min5

# 学習用ヒストグラム構築
# /data/sampling/train を入力としてヒストグラムを生成
PYTHON=python3 ./build_trainHist.sh

# 類似度計算
# id_1〜id_6 を固定で処理（詳細は「類似度計算」参照）
python3 /code2vec/jscode2vec/calculate_similarity.py
```

### 入力・出力例

**入力構造:**
```
/path/to/target_dir_js/
  project1/
    project1_0.js
    project1_1.js
  project2/
    project2_0.js
```

**出力構造（プロジェクト単位並列 / 単一プロジェクト）:**
```
/code2vec/results/
  project1/
    c2v/
      project1_0.test.raw.txt
      project1_0.test.c2v
      context_count.json
    vectors/
      project1_0.vector
      project1_1.vector
    process.log
  project2/
    ...
```

**出力構造（ファイル単位並列）:**
`target_dir_js` のベースディレクトリ名（例: `id_222_toRepo`）を `base_dir_name` として、以下の構造で出力します。

```
/code2vec/results/
  {base_dir_name}/
    project1/
      c2v/
      vectors/
      process.log
```

※ジョブログ:

- プロジェクト単位並列: `/code2vec/results/parallel_projects_shm.log`
- ファイル単位並列: `/code2vec/results/parallel_jobs_shm.log`

## 主要な設定値

以下の設定値は学習済みモデル（`js_dataset_min5`）と整合している必要があります：

```bash
MAX_CONTEXTS=200
WORD_VOCAB_SIZE=1301136
PATH_VOCAB_SIZE=911417
TARGET_VOCAB_SIZE=261245
```

各スクリプトは上記を環境変数として上書き可能です（例: `MAX_CONTEXTS=100 ./jscode2vec_parallel.sh ...`）。

追加でよく使う環境変数:

```bash
PYTHON_BIN=python3
MODEL_PATH=/code2vec/models/js_dataset_min5/saved_model_iter19.release
```

## 依存関係

- Python 3.x
- TensorFlow 2.13.0
- GNU parallel
- GNU coreutils（`timeout` コマンド）
- `bc`（SHMサーバ起動時のMB表示に使用）
- Node.js 18.x（JSExtractor用）

## 注意事項

1. **パス指定**: すべてのスクリプトはDocker環境の絶対パス（`/code2vec/...`）を使用
2. **モジュールインポート**: Pythonスクリプトは親ディレクトリ（`/code2vec`）のモジュールを参照
3. **並列実行**: `jscode2vec_parallel.sh` / `jscode2vec_file_parallel_shm.sh` はCPUコア数を検出し、並列ジョブ数を自動決定します（引数で上書き可能）
4. **SHMサーバ**: 並列スクリプトは `histogram_server.py` を自動起動し、既に起動済みなら再利用します（`/tmp/code2vec_histograms_*_metadata.json` を参照）
5. **キャッシュ**: `preload_histograms.py` により `histogram_cache.pkl` を作成すると、SHMサーバの起動が高速化されます

## トラブルシューティング

### モジュールが見つからないエラー
```bash
# sys.path.insert()により自動的に親ディレクトリが追加されます
# 手動でPYTHONPATHを設定する場合:
export PYTHONPATH=/code2vec:$PYTHONPATH
```

### ヒストグラムキャッシュの再生成
```bash
# キャッシュファイルを削除して再生成
rm /code2vec/data/js_dataset_min5/histogram_cache.pkl*
python3 /code2vec/jscode2vec/preload_histograms.py --dataset js_dataset_min5
```

### `timeout` が見つからない
Docker外（macOSホストなど）で直接実行すると `timeout` が無い場合があります。基本はDockerコンテナ内で実行してください。

### 並列処理の調整
```bash
# 並列ジョブ数を手動指定（CPUコア数に応じて調整）
./jscode2vec_parallel.sh /path/to/target 8  # 8並列で実行
```

## 類似度計算

### 基本的な使い方

`jscode2vec/origin_pattern/id_{n}/vectors` 配下のベースベクトル（複数）と、
`results/id_{n}_toRepo` 配下のターゲットベクトル（複数）とのコサイン類似度を計算します。
各ターゲットファイルについて、複数のベースベクトルとの類似度・平均値・分散を算出し、`mean` の降順でソートして保存します。

```bash
# Docker環境で実行
cd /code2vec/jscode2vec

# id_1〜id_6 を順に処理してJSONを出力
python3 calculate_similarity.py
```

### 前提条件

類似度計算を実行する前に、以下のディレクトリにベースとなる `.vector` を配置してください。

- `/code2vec/jscode2vec/origin_pattern/id_1/vectors/*.vector`
- `/code2vec/jscode2vec/origin_pattern/id_2/vectors/*.vector`
- ...
- `/code2vec/jscode2vec/origin_pattern/id_6/vectors/*.vector`

ターゲット側はデフォルトで次を参照します（スクリプト内で固定）:

- `/code2vec/results/id_1_toRepo/**/vectors/*.vector`
- ...
- `/code2vec/results/id_6_toRepo/**/vectors/*.vector`

### 出力形式

結果は次の場所に保存されます。

- `/code2vec/jscode2vec/similarity/bachelor/id_{n}/id_{n}_similarity.json`

```json
{
  "total_count": 1523,
  "results": [
    {
      "file": "project1_123",
      "cos_similarity": [
        {
          "jsperf_222": 0.9876,
          "jsperf_232": 0.9854,
          "jsperf_239": 0.9901
        }
      ],
      "mean": 0.9877,
      "var": 0.0000456
    },
    {
      "file": "project2_456",
      "cos_similarity": [
        {
          "jsperf_222": 0.9543,
          "jsperf_232": 0.9521,
          "jsperf_239": 0.9567
        }
      ],
      "mean": 0.9544,
      "var": 0.0000432
    }
  ]
}
```

- `file`: プロジェクト名_ID（例: `wuchangming-spy-debugger_0`）
- `cos_similarity`: 各ベースベクトルとのコサイン類似度の辞書
- `mean`: コサイン類似度の平均値
- `var`: コサイン類似度の分散
- 結果は`mean`の降順でソート済み

### カスタマイズ

ベース/ターゲットのディレクトリを変更する場合は、`calculate_similarity.py` の `main()` 内の以下を編集してください（現状、コマンドライン引数は参照しません）。

```python
# main()関数内
base_vectors_dir = script_dir / 'origin_pattern' / f'id_{id_num}' / 'vectors'
target_dir = str(script_dir.parent / 'results' / f'id_{id_num}_toRepo')
```

