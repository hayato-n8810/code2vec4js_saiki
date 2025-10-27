# code2vec (JS) ベクトル化専用パイプライン

このドキュメントは、既に学習済みの JavaScript 向け code2vec モデルを使って、任意の JS プログラムを「ベクトル化のみ」行うための、最小かつ堅牢な手順をまとめたものです。プロジェクトの `preprocess.sh` および `preprocess.py`/`preprocess_test.py` の方針に準拠し、モデルが期待する MAX_CONTEXTS に必ず合わせる前処理を推奨します。

## 前提条件

- **Docker環境**: このパイプラインはDockerコンテナ内で実行されることを前提としています
- **学習済みモデル**:
  - `/code2vec/models/js_dataset_min5/saved_model_iter19.release`
  - 併せて、学習時に生成されたヒストグラム（辞書作成に使用）
    - `/code2vec/data/js_dataset_min5/js_dataset_min5.histo.ori.c2v`
    - `/code2vec/data/js_dataset_min5/js_dataset_min5.histo.path.c2v`
    - `/code2vec/data/js_dataset_min5/js_dataset_min5.histo.tgt.c2v`
- **モデル設定値**（`js_dataset_min5`）:
  - `MAX_CONTEXTS=200`
  - `WORD_VOCAB_SIZE=1301136`
  - `PATH_VOCAB_SIZE=911417`
  - `TARGET_VOCAB_SIZE=261245`
- **実行環境**: Python3, Node.js, TensorFlow 2.13.0

## なぜ前処理が必要か（要点）

- `path_context_reader.py` は、入力 1 行を「1 つの target + ちょうど MAX_CONTEXTS 個の context」として厳密にパースします。
- 行内の context 数が不足/過多だと、`Expect N fields but have M` のエラーになります。
- 学習時と同じロジック（`preprocess_test.py`）で、MAX_CONTEXTS に合わせてトリム/パディングするのが最も安全です。

## Docker環境でのパス構造

```
/code2vec/                           # プロジェクトルート
├── ql2vec/                          # ベクトル化パイプライン（このディレクトリ）
│   ├── code2vec_only.py            # ベクトル化専用スクリプト
│   ├── preprocess_test.py          # 前処理スクリプト
│   ├── preload_histograms.py       # ヒストグラムキャッシュ
│   ├── jscode2vec_one_project.sh   # 単一プロジェクト処理
│   └── jscode2vec_parallel.sh      # 並列処理
├── JSExtractor/                     # パス抽出器
│   └── extract.py
├── data/js_dataset_min5/           # ヒストグラムデータ
│   ├── js_dataset_min5.histo.ori.c2v
│   ├── js_dataset_min5.histo.path.c2v
│   ├── js_dataset_min5.histo.tgt.c2v
│   └── histogram_cache.pkl         # キャッシュファイル（自動生成）
├── models/js_dataset_min5/         # 学習済みモデル
│   └── saved_model_iter19.release
└── results/                         # 出力ディレクトリ
    └── {project_name}/
        ├── c2v/                    # 中間ファイル
        └── vectors/                # 最終出力
```

## 推奨パイプライン（手順）

以下は「JS → パス抽出（raw）→ 前処理（MAX_CONTEXTS に合わせる）→ ベクトル化」の 3 ステップです。

### 方法A: 自動パイプライン（推奨）

最も簡単な方法は、提供されているシェルスクリプトを使用することです。

#### 単一プロジェクト処理

```bash
# Dockerコンテナ内で実行
docker exec -it code2vec4js bash
cd /code2vec/ql2vec

# プロジェクトディレクトリを指定して実行
./jscode2vec_one_project.sh /path/to/project_dir
```

**入力**: `/path/to/project_dir/*.js`（複数のJSファイル）
**出力**: 
- `/code2vec/results/{project_name}/c2v/*.test.c2v`（中間ファイル）
- `/code2vec/results/{project_name}/vectors/*.vector`（最終ベクトル）

#### 複数プロジェクトの並列処理

```bash
# 複数プロジェクトを含むディレクトリを指定
./jscode2vec_parallel.sh /path/to/target_dir [max_parallel_jobs]

# 例: 8並列で実行
./jscode2vec_parallel.sh /data/projects 8
```

**入力構造**:
```
/path/to/target_dir/
  project1/
    file1.js
    file2.js
  project2/
    file1.js
```

**出力**: 各プロジェクトごとに`results/{project_name}/`配下に生成

### 方法B: 手動パイプライン（詳細制御）

より細かい制御が必要な場合は、手動で各ステップを実行できます。

#### 1) JS からパス抽出（raw 行の作成）

```bash
# ディレクトリ内のすべてのJSファイルを抽出
python3 /code2vec/JSExtractor/extract.py \
  --dir /path/to/js_dir \
  --max_path_length 8 \
  --max_path_width 2 \
  > mydata.test.raw.txt

# または単一ファイルを抽出
python3 /code2vec/JSExtractor/extract.py \
  --file /path/to/file.js \
  --whole_file \
  --max_path_length 8 \
  --max_path_width 2 \
  > mydata.test.raw.txt

# 妥当性フィルタ（学習時と同じ）
grep -E "^[a-zA-Z|]+\s" mydata.test.raw.txt > mydata.test.raw.txt.tmp
mv mydata.test.raw.txt.tmp mydata.test.raw.txt
```

**出力形式** (`mydata.test.raw.txt`):
```
<target> <token1,path,token2> <token1,path,token2> ...
```

#### 2) 前処理（MAX_CONTEXTS に合わせて整形）

```bash
# 学習時と同じ辞書ヒストグラムを使用
python3 /code2vec/ql2vec/preprocess_test.py \
  --test_data mydata.test.raw.txt \
  --max_contexts 200 \
  --word_vocab_size 1301136 \
  --path_vocab_size 911417 \
  --target_vocab_size 261245 \
  --word_histogram /code2vec/data/js_dataset_min5/js_dataset_min5.histo.ori.c2v \
  --path_histogram /code2vec/data/js_dataset_min5/js_dataset_min5.histo.path.c2v \
  --target_histogram /code2vec/data/js_dataset_min5/js_dataset_min5.histo.tgt.c2v \
  --output_name mydata
```

**重要**: `--max_contexts 200` は必ず「モデル学習時の値」と同じにしてください。

**出力**: `mydata.test.c2v`（各行が「target + ちょうど200個の context」）

#### 3) ベクトル化（code2vec 実行）

```bash
# ベクトル化のみ実行
python3 /code2vec/ql2vec/code2vec_only.py \
  --load /code2vec/models/js_dataset_min5/saved_model_iter19.release \
  --test mydata.test.c2v \
  --export_code_vectors
```

**出力**: `mydata.test.c2v.vectors`
- 各行が 1 メソッドのコードベクトル（384次元）
- フォーマット: スペース区切りの浮動小数点数

## トラブルシューティング

### 1. `InvalidArgumentError: Expect N fields but have M`

**原因**: 入力 `.c2v` のフィールド数が「1 + MAX_CONTEXTS」に一致していない

**対処**:
```bash
# c2vファイルのフィールド数を確認
head -1 mydata.test.c2v | tr ' ' '\n' | wc -l
# 期待値: 201 (1 target + 200 contexts)

# MAX_CONTEXTSを正しく設定して再前処理
python3 /code2vec/ql2vec/preprocess_test.py \
  --test_data mydata.test.raw.txt \
  --max_contexts 200 \
  ...（以下同じ）
```

### 2. `.vectors` が空 / 生成されない

**原因例**:
- MAX_CONTEXTS 不一致
- 入力が空行のみ
- パス抽出失敗

**対処**:
```bash
# raw ファイルの行数確認
wc -l mydata.test.raw.txt

# c2v ファイルの内容確認
head -5 mydata.test.c2v

# 有効なコンテキストがあるか確認
grep -v "^[a-zA-Z|]*\s*$" mydata.test.raw.txt | wc -l
```

### 3. ヒストグラム読み込みが遅い（並列処理時）

**原因**: ヒストグラムファイルが毎回読み込まれる

**対処**: ヒストグラムキャッシュを事前生成
```bash
# 初回のみ実行（10-50倍高速化）
python3 /code2vec/ql2vec/preload_histograms.py \
  --dataset js_dataset_min5 \
  --word_vocab_size 1301136 \
  --path_vocab_size 911417 \
  --target_vocab_size 261245

# キャッシュファイルが生成されたことを確認
ls -lh /code2vec/data/js_dataset_min5/histogram_cache.pkl
```

### 4. OOV (Out-of-Vocabulary) 警告

**症状**: ターゲット名が語彙に存在しない警告が表示される

**対処**: 
- `--whole_file` オプションを使用してファイル全体を1つのメソッドとして扱う
- `code2vec_only.py`を使用（評価メトリクスをスキップ）
- 警告は無視してもベクトルは正常に出力される

## 期待される成果物

**手動パイプライン実行時**:
- `mydata.test.raw.txt` … パス抽出の生データ
- `mydata.test.c2v` … MAX_CONTEXTS=200 に整形済みの入力
- `mydata.test.c2v.vectors` … ベクトル（1 行 1 メソッド、384次元）

**自動パイプライン実行時**:
```
/code2vec/results/{project_name}/
├── c2v/
│   ├── {filename}.test.raw.txt      # 生データ
│   └── {filename}.test.c2v          # 整形済み
├── vectors/
│   └── {filename}.vector            # 最終ベクトル
└── process.log                       # 処理ログ
```

## パフォーマンス最適化

### 並列処理の推奨設定

```bash
# CPU コア数に応じて自動調整（推奨）
./jscode2vec_parallel.sh /path/to/target_dir

# 手動指定（利用可能コア数の60%程度が安全）
# 例: 48コアの場合 → 28並列
./jscode2vec_parallel.sh /path/to/target_dir 28
```

### TensorFlow設定（環境変数）

Dockerfileで設定済みですが、手動実行時は以下を設定:
```bash
export OMP_NUM_THREADS=3
export TF_NUM_INTRAOP_THREADS=3
export TF_NUM_INTEROP_THREADS=1
export TF_FORCE_GPU_ALLOW_GROWTH=true
```

## ベクトル次元と構成

- **デフォルト次元**: 384次元
  - 128次元 (source tokens)
  - 128次元 (path)
  - 128次元 (target tokens)
- **設定箇所**: `/code2vec/config.py` の `DEFAULT_EMBEDDINGS_SIZE=128`

## 重要な注意事項

1. **MAX_CONTEXTS は絶対に変更しない**: モデル側ではなく、必ず**データ側を合わせる**
2. **Docker環境のパスを使用**: すべてのパスは `/code2vec/` から始まる絶対パス
3. **ヒストグラムキャッシュを活用**: 並列処理前に必ず事前生成
4. **タイムアウト設定**: 単一ファイルの処理は15分でタイムアウト（`process_project_worker.sh`）

## 関連ドキュメント

- `README.md` - ql2vecパイプラインの概要
- `/code2vec/DOCKER_USAGE.md` - Docker環境の使用方法
- `/code2vec/preprocess.sh` - 学習データの前処理（参考）

## サンプルワークフロー

```bash
# 1. Dockerコンテナに入る
docker exec -it code2vec4js bash

# 2. ql2vecディレクトリに移動
cd /code2vec/ql2vec

# 3. ヒストグラムキャッシュを生成（初回のみ）
python3 preload_histograms.py --dataset js_dataset_min5

# 4. 単一プロジェクトをベクトル化
./jscode2vec_one_project.sh /data/my_project

# 5. 結果を確認
ls -lh /code2vec/results/my_project/vectors/
cat /code2vec/results/my_project/vectors/file1.vector

# 6. 複数プロジェクトを並列処理（必要に応じて）
./jscode2vec_parallel.sh /data/all_projects 16
```
