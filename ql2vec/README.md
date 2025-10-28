# ql2vec - Query to Vector Pipeline

このディレクトリには、JavaScriptコードをベクトル化するためのパイプラインスクリプトが含まれています。

## ファイル構成

### メインスクリプト

- **`jscode2vec_parallel.sh`** - 複数プロジェクトを並列処理するメインスクリプト
- **`jscode2vec_one_project.sh`** - 単一プロジェクトを処理するスクリプト
- **`process_project_worker.sh`** - 並列処理のワーカースクリプト（GNU parallelから呼び出される）

### サポートスクリプト

- **`code2vec_only.py`** - code2vecモデルを使用してコードベクトルをエクスポート
- **`preprocess_test.py`** - テストデータを前処理してcode2vec形式に変換
- **`preload_histograms.py`** - ヒストグラムの事前ロード・キャッシュ化
- **`extract_code_snippets.py`** - JSONファイルからコードスニペットを抽出
- **`build_trainHist.sh`** - 学習用ヒストグラムデータを構築
- **`calculate_similarity.py`** - ベースベクトルとの類似度を計算してJSON出力

## Docker環境でのパス構造

```
/code2vec/                      # プロジェクトルート（./がマウント）
├── ql2vec/                     # このディレクトリ
│   ├── jscode2vec_parallel.sh
│   ├── process_project_worker.sh
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
    └── {project_name}/
        ├── c2v/               # .c2vファイル
        ├── vectors/           # .vectorファイル
        └── process.log        # ログファイル

/data/                          # 外部データマウントポイント
└── sampling/train/             # 学習データ（build_trainHist.sh用）

/code2vec/similarity/           # 類似度計算結果
└── {base_filename}_similarity.json
```

## 使用方法

### Docker環境での実行

```bash
# Dockerコンテナ内で実行
docker exec -it code2vec4js bash

# 並列処理（複数プロジェクト）
cd /code2vec/ql2vec
./jscode2vec_parallel.sh /absolute/path/to/target_dir_js [max_parallel_jobs]

# 単一プロジェクト処理
./jscode2vec_one_project.sh /absolute/path/to/project_dir

# ヒストグラムの事前ロード（初回のみ）
python3 /code2vec/ql2vec/preload_histograms.py --dataset js_dataset_min5

# 学習用ヒストグラム構築
./build_trainHist.sh

# 類似度計算
# 全プロジェクトを対象
python3 /code2vec/ql2vec/calculate_similarity.py

# 特定ディレクトリを対象
python3 /code2vec/ql2vec/calculate_similarity.py /path/to/target_dir
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

**出力構造:**
```
/code2vec/results/
  project1/
    c2v/
      project1_0.test.c2v
      project1_1.test.c2v
    vectors/
      project1_0.vector
      project1_1.vector
    process.log
  project2/
    ...
```

## 主要な設定値

以下の設定値は学習済みモデル（`js_dataset_min5`）と整合している必要があります：

```bash
MAX_CONTEXTS=200
WORD_VOCAB_SIZE=1301136
PATH_VOCAB_SIZE=911417
TARGET_VOCAB_SIZE=261245
```

## 依存関係

- Python 3.x
- TensorFlow 2.13.0
- GNU parallel
- Node.js 18.x（JSExtractor用）

## 注意事項

1. **パス指定**: すべてのスクリプトはDocker環境の絶対パス（`/code2vec/...`）を使用
2. **モジュールインポート**: Pythonスクリプトは親ディレクトリ（`/code2vec`）のモジュールを参照
3. **並列実行**: `jscode2vec_parallel.sh`は自動的にCPUコア数を検出し、適切な並列ジョブ数を設定
4. **キャッシュ**: 初回実行時にヒストグラムキャッシュが自動生成され、2回目以降は高速化される

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
python3 /code2vec/ql2vec/preload_histograms.py --dataset js_dataset_min5
```

### 並列処理の調整
```bash
# 並列ジョブ数を手動指定（CPUコア数に応じて調整）
./jscode2vec_parallel.sh /path/to/target 8  # 8並列で実行
```

## 類似度計算

### 基本的な使い方

`ql2vec/origin_222/vectors`配下の全ベクトルファイルと、
指定されたディレクトリ配下の全ベクトルファイルとのコサイン類似度を計算します。
各比較対象ファイルについて、複数のベースベクトルとの類似度、平均値、分散を算出します。

```bash
# Docker環境で実行
cd /code2vec/ql2vec

# 全プロジェクトを対象に類似度計算（resultsフォルダ全体）
python3 calculate_similarity.py

# 特定のディレクトリ配下のみを対象
python3 calculate_similarity.py /path/to/target_dir
```

### 前提条件

類似度計算を実行する前に、`ql2vec/origin_222/vectors`ディレクトリにベースとなる
ベクトルファイルを配置する必要があります。

例: `jsperf_222.vector`, `jsperf_232.vector`, `jsperf_239.vector` など

### 出力形式

結果は`ql2vec/similarity/result_222_similarity.json`に保存されます。

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

ベースベクトルディレクトリを変更する場合は、`calculate_similarity.py`の以下の行を編集：

```python
# main()関数内
base_vectors_dir = script_dir / 'origin_222' / 'vectors'
```

