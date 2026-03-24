# jscode2vec

このフォルダは，JavaScript 向け code2vec パイプラインの実験・推論・比較評価を行うためのサブプロジェクトです．

---

## プロジェクト全体のディレクトリ構成

リポジトリ全体（要約）:

```text
code2vec4js_saiki/
├── CSharpExtractor/
├── JSExtractor/
├── JavaExtractor/
├── data/
├── models/
├── jscode2vec/
├── Dockerfile
├── docker-compose.yml
├── DOCKER_USAGE.md
└── (学習・推論用の Python スクリプト群)
```

**jscode2vec 配下 （データも含めた完全版はbrain-2にあります）:**

```text
jscode2vec/
├── data/
│   ├── github/
│   ├── microbenchmark/
│   └── origin_pattern/ 
│       └── id{1 ~ 6}/
│           ├── code/ パターン元 slow コード片
│           └── vectors/ codeのcode2vecベクトル
├── targets/ ベクトル化対象
│   ├── github/　codeQLによる検出結果コード片
│   └── microbenchmark/  codeQLによる検出結果コード片
├── outputs/
│   ├── vec/
│   │   ├── github/
│   │   └── microbenchmark/
│   └── similarity/
│       ├── github/
│       └── microbenchmark/
└── scripts/
    ├── build_trainHist.sh
    ├── extract_code_snippets.py
    ├── jscode2vec.py
    ├── preload_histograms.py
    ├── github_similarity.py
    ├── microbenchmark_similarity.py
    └── helper/
```

---

## Docker前提について

このプロジェクトは Docker 環境での実行を前提に設計されています．

- コンテナ作業ディレクトリは `/code2vec` を想定しています．
-  `/code2vec/...` 形式の絶対パスをデフォルト値として使用することを推奨します．
- Docker の手順と環境情報は `DOCKER_USAGE.md`，`docker-compose.yml`，`Dockerfile` に定義されています．

最小セットアップ:

```bash
docker compose build
docker compose up -d
docker compose exec code2vec bash
```

---

## このフォルダでできること

- CodeQL 等で作成した JSON から JavaScript スニペットを抽出する．
- 単一ファイル，単一プロジェクト，複数プロジェクト単位で code2vec を用いてJavaScriptファイルを ベクトル化する．
- origin pattern と GitHub/microbenchmark のベクトル類似度を計算する．
- ヒストグラムを事前キャッシュし，推論の初期ロード時間を短縮する．

---

## 実行フロー

1. JSON からコード抽出
2. 必要に応じてヒストグラム事前キャッシュ作成
3. JS ファイルをベクトル化
4. 類似度計算
5. 出力 JSON を集計・分析

---

## 出力形式

### ベクトル出力

- 拡張子: `.vector`
- 中身: 空白区切り浮動小数点列
- 主な出力先:
  - `jscode2vec/outputs/vec/github/id_{id}/.../vectors/*.vector`
  - `jscode2vec/outputs/vec/microbenchmark/id_{id}/vectors/*.vector`

### 類似度出力 JSON

主なキー:

- `total_count`: 出力件数
- `results`: 類似度結果の配列
  - `file`: 対象ファイル名（拡張子なし stem）
  - `cos_similarity`: origin ごとのコサイン類似度辞書を 1 要素配列で保持
  - `mean`: 類似度平均
  - `var`: 類似度分散

例:

```json
{
  "total_count": 2,
  "results": [
    {
      "file": "slow_10",
      "cos_similarity": [
        {
          "block_slow_1": 0.8123,
          "block_slow_2": 0.7345
        }
      ],
      "mean": 0.7734,
      "var": 0.0015
    }
  ]
}
```

---

## scripts直下のプログラム詳細

### 1)  build_trainHist.sh

処理内容:

- 学習データから AST path を抽出し，語彙ヒストグラムを生成します．
- **卒論では，才木データを利用しているため実行しなくて良い**
- 生成対象:
  - `${DATASET_NAME}.histo.ori.c2v`
  - `${DATASET_NAME}.histo.path.c2v`
  - `${DATASET_NAME}.histo.tgt.c2v`

主な入出力:

- 入力ディレクトリ（固定）: `/data/sampling/train`
- 出力先（固定）: `/code2vec/data/${DATASET_NAME}`

オプション:

- CLI オプションはありません．
- 実行時に `PYTHON` 環境変数で Python 実行コマンドが必要です．

実行例:

```bash
cd /code2vec
PYTHON=python3 bash jscode2vec/scripts/build_trainHist.sh
```

### 2) extract_code_snippets.py

処理内容:

- JSON の `results[*].code_snippet` を `.js` として保存します．
- 単体モード／GitHub一括モード／microbenchmark一括モードをサポートします．

実行コマンド:

```bash
python3 jscode2vec/scripts/extract_code_snippets.py [input_json_file] [output_dir] [-github] [-mb]
```

オプション:

- `input_json_file`（位置引数，任意）
  - 単体モードで使用する入力 JSON ファイル
- `output_dir`（位置引数，任意）
  - 単体モードの出力ベースディレクトリ
- `-github`（フラグ）
  - `/code2vec/json2vec/data/github/id_*/` を一括処理
- `-mb`（フラグ）
  - `/code2vec/json2vec/data/microbenchmark/id_*_code.json` を一括処理

注意:

- `-github` と `-mb` は同時指定不可です．
- 一括モードでは位置引数を指定できません．
- 一括モードの固定パスは `json2vec` を参照する実装です．

入出力:

- 入力 JSON 例: `{"results": [{"id": 1, "code_snippet": "..."}]}`
- 単体モード出力: `{output_dir}/{project_name}/{project_name}_{id}.js`
- `-mb` 出力: `file_path` の basename をそのままファイル名に使用

実行例:

```bash
# 単体モード
python3 jscode2vec/scripts/extract_code_snippets.py \
  /code2vec/jscode2vec/data/microbenchmark/id_1_code.json \
  /code2vec/jscode2vec/targets/microbenchmark

# GitHub 一括モード
python3 jscode2vec/scripts/extract_code_snippets.py -github

# microbenchmark 一括モード
python3 jscode2vec/scripts/extract_code_snippets.py -mb
```

**推奨：コード抽出後のフォーマッタの適用**
```bash
# dir配下のすべてのjsファイルが対象
npx prettier --write "{dir}/**/*.js"
```

### 3) preload_histograms.py

処理内容:

- 語彙ヒストグラムを読み込み，実行時キャッシュを生成・更新します．
- 個別に実行する補助スクリプトで，実行は任意

実行コマンド:

```bash
python3 jscode2vec/scripts/preload_histograms.py [options]
```

オプション:

- `-d`, `--dataset`（既定: `js_dataset_min5`）
  - データセット名
- `-wvs`, `--word_vocab_size`（既定: `1301136`）
  - 単語語彙サイズ
- `-pvs`, `--path_vocab_size`（既定: `911417`）
  - パス語彙サイズ
- `-tvs`, `--target_vocab_size`（既定: `261245`）
  - ターゲット語彙サイズ

入出力:

- 入力: `dataset_name` に対応するヒストグラムファイル群
- 出力: ヒストグラムキャッシュファイル（作成先は helper/runtime 実装依存）

実行例:

```bash
python3 jscode2vec/scripts/preload_histograms.py
python3 jscode2vec/scripts/preload_histograms.py -d js_dataset_min5 -wvs 1301136 -pvs 911417 -tvs 261245
```

### 4) **jscode2vec.py**

処理内容:

- JS ファイル群を code2vec 推論にかけ，`.vector` を出力します．
- モード:
  - single（単一ファイル）
  - project（単一ディレクトリ）
  - all（親ディレクトリ配下の子プロジェクト一括）

実行コマンド:

```bash
python3 jscode2vec/scripts/jscode2vec.py (-s FILE | -p DIR | --all DIR) [-o OUT] [-j N]
```

オプション:

- `-s`, `--single`
  - 単一 JS ファイルを指定
- `-p`, `--project`
  - JS ファイルを含む単一フォルダを指定
- `--all`
  - 子プロジェクトを複数含む親フォルダを指定
- `-o`, `--output`
  - 出力先ベースパス（省略時は `targets` を `outputs/vec` に置換）
- `-j`, `--jobs`（既定: `1`）
  - 並列処理数（project/all で有効）

入出力:

- 入力: `.js` ファイル
- 出力:
  - `.vector` ファイル群
  - `process.log`（各スコープ出力ディレクトリ配下）

実行例:

```bash
# single
python3 jscode2vec/scripts/jscode2vec.py \
  -s /code2vec/jscode2vec/targets/microbenchmark/id_1/slow_10.js

# project
python3 jscode2vec/scripts/jscode2vec.py \
  -p /code2vec/jscode2vec/targets/microbenchmark/id_1 \
  -j 4

# all
python3 jscode2vec/scripts/jscode2vec.py \
  --all /code2vec/jscode2vec/targets/github/id_3 \
  -j 4
```

### 5) github_similarity.py

処理内容:

- GitHub 側ベクトルと origin pattern ベクトルのコサイン類似度を計算します．
- 結果は `mean` 降順でソートして保存します．

実行コマンド:

```bash
python3 jscode2vec/scripts/github_similarity.py [options]
```

オプション:

- `--id`（任意）
  - 対象 ID（例: `1`）
  - 省略時は `1..6` を順に処理
- `--root`（既定: `/code2vec/jscode2vec`）
  - jscode2vec ルートディレクトリ

入出力:

- 入力:
  - `{root}/outputs/vec/github/id_{id}/**/vectors/*.vector`
  - `{root}/data/origin_pattern/id_{id}/vectors/*.vector`
- 出力:
  - `{root}/outputs/similarity/github/id_{id}_similarity.json`

実行例:

```bash
# IDを1つだけ計算
python3 jscode2vec/scripts/github_similarity.py --id 1 --root /code2vec/jscode2vec

# ID 1..6 をまとめて計算
python3 jscode2vec/scripts/github_similarity.py --root /code2vec/jscode2vec
```

### 6) microbenchmark_similarity.py

処理内容:

- microbenchmark 側ベクトルと origin pattern ベクトルのコサイン類似度を計算します．
- 同じ file_id の組み合わせ（`slow_x` と `block_slow_x`）は除外します．

実行コマンド:

```bash
python3 jscode2vec/scripts/microbenchmark_similarity.py [options]
```

オプション:

- `--id`（任意）
  - 対象 ID（例: `1`）
  - 省略時は `1..6` を順に処理
- `--root`（既定: `/code2vec/jscode2vec`）
  - jscode2vec ルートディレクトリ

入出力:

- 入力:
  - `{root}/outputs/vec/microbenchmark/id_{id}/vectors/*.vector`
  - `{root}/data/origin_pattern/id_{id}/vectors/*.vector`
- 出力:
  - `{root}/outputs/similarity/microbenchmark/id_{id}_similarity.json`

実行例:

```bash
# IDを1つだけ計算
python3 jscode2vec/scripts/microbenchmark_similarity.py --id 1 --root /code2vec/jscode2vec

# ID 1..6 をまとめて計算
python3 jscode2vec/scripts/microbenchmark_similarity.py --root /code2vec/jscode2vec
```

## helper/config.py の説明

`jscode2vec/scripts/helper/config.py` は，JS ベクトル化パイプラインの実行時定数を一元管理する設定ファイルです．

### 定義されている主な内容

- `HyperParams` データクラス
  - `max_contexts`, `max_path_length`, `max_path_width`
  - `word_vocab_size`, `path_vocab_size`, `target_vocab_size`
  - `dataset_name`
  - `model_path`, `word_histo`, `path_histo`, `target_histo`
- `HYPER_PARAMS`
  - 実際に利用する既定値セット
- 運用制御パラメータ
  - `EXTRACT_TIMEOUT_SEC`
  - `INFER_TIMEOUT_SEC`
  - `PREPROCESS_MAX_RETRIES`
  - `MIN_FILES_FOR_SHM`
- `load_hyperparams()`
  - `HYPER_PARAMS` を返す関数

### 注意点

- 既定のモデル・ヒストグラムパスは `/code2vec/...` を前提にしています．
- Docker 外で実行する場合はこのファイルのパス定義を環境に合わせて変更してください．