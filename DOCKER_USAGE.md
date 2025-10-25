# Docker環境での実行ガイド

## 更新内容（2025年10月25日）

## 動作環境

### インストールされているソフトウェア
- **TensorFlow**: 2.13.0（GPU対応）
- **Python**: 3.8.10
- **Node.js**: 18.20.8
- **npm**: 10.8.2
- **pandas**: 最新版
- **numpy**: 最新版

### システム要件
- Docker Desktop（macOS/Windows）またはDocker Engine（Linux）
- 推奨: GPU対応の場合はNVIDIA Docker Runtime
- 十分なディスク容量（イメージサイズ: 約3GB）

## 使用方法

### 1. 初回セットアップ

```bash
# リポジトリのルートディレクトリで実行

# Dockerイメージをビルド
docker compose build

# コンテナを起動
docker compose up -d
```

### 2. コンテナに入る

```bash
# インタラクティブシェルを起動
docker compose exec code2vec bash
```

### 3. JSExtractorのビルド（初回のみ、コンテナ内で実行）

```bash
# コンテナ内で実行
cd /code2vec/JSExtractor/JSExtractor
npm run build
cd /code2vec
```

**注意**: Dockerfileですでに`npm install`と`npm run build`が実行されているため、通常はこのステップは不要です。

### 4. JavaScriptファイルから特徴を抽出

#### 単一ファイルの場合
```bash
# コンテナ内で実行
python3 JSExtractor/extract.py \
  --file /path/to/your/file.js \
  --max_path_length 8 \
  --max_path_width 2 > output.c2v
```

#### ディレクトリ全体の場合
```bash
# コンテナ内で実行
python3 JSExtractor/extract.py \
  --dir /path/to/your/directory \
  --max_path_length 8 \
  --max_path_width 2 > output.c2v
```

### 5. データの前処理（モデル学習用）

```bash
# コンテナ内で実行
cd /code2vec

# preprocess.shのパスを確認・編集
# デフォルト設定:
# TRAIN_DIR=/data/sampling/train
# VAL_DIR=/data/sampling/val
# TEST_DIR=/data/sampling/test

# 前処理を実行
bash preprocess.sh
```

### 6. モデルの学習

```bash
# コンテナ内で実行
cd /code2vec
bash train.sh
```

### 7. コードベクトルのエクスポート

```bash
# コンテナ内で実行
python3 code2vec.py \
  --load models/js_dataset_min5/saved_model_iter19.release \
  --test output.c2v \
  --export_code_vectors

# output.c2v.vectorsファイルが生成される
```

## コンテナ外からの実行

コンテナに入らずに、コマンドを直接実行することもできます：

```bash
# 例: TensorFlowのバージョン確認
docker compose exec code2vec python3 -c "import tensorflow as tf; print(tf.__version__)"

# 例: JavaScriptファイルから特徴抽出
docker compose exec code2vec python3 JSExtractor/extract.py \
  --file /code2vec/example.js > output.c2v

# 例: ベクトル化
docker compose exec code2vec python3 code2vec.py \
  --load models/js_dataset_min5/saved_model_iter19.release \
  --test output.c2v \
  --export_code_vectors
```

## GPU対応

GPU（NVIDIA）を使用する場合は、`docker-compose.yml`の以下の行のコメントを解除してください：

```yaml
runtime: nvidia
environment:
  - NVIDIA_VISIBLE_DEVICES=all
```

その後、コンテナを再起動：

```bash
docker compose down
docker compose up -d
```

## データボリュームについて

docker-compose.ymlでは以下のボリュームがマウントされています：

```yaml
volumes:
  - ./:/code2vec/                              # プロジェクト全体
  - /mnt/data1/kazuya-s/dataset/data/jsPerf:/data  # データセット（環境に応じて変更）
```

データセットのパスは環境に応じて変更してください。存在しないパスの場合はコメントアウトするか、適切なパスに変更してください。

## 便利なコマンド

```bash
# コンテナの状態確認
docker compose ps

# コンテナのログ確認
docker compose logs -f code2vec

# コンテナの停止
docker compose stop

# コンテナの停止と削除
docker compose down

# コンテナの再ビルド（強制）
docker compose build --no-cache

# コンテナの再起動
docker compose restart
```

## トラブルシューティング

### ビルドエラーが発生する場合

```bash
# キャッシュをクリアして再ビルド
docker compose down
docker system prune -a
docker compose build --no-cache
```

### パーミッションエラーが発生する場合

```bash
# UID/GIDが正しく設定されているか確認
echo $UID
echo $GID

# 再度設定して起動
export UID=$(id -u)
export GID=$(id -g)
docker compose up -d
```

### データセットのパスが見つからない場合

`docker-compose.yml`を編集して、データセットのマウントポイントをコメントアウトまたは変更：

```yaml
volumes:
  - ./:/code2vec/
  # - /mnt/data1/kazuya-s/dataset/data/jsPerf:/data  # この行をコメントアウト
```

## まとめ

更新されたDocker環境は以下の利点があります：

- ✅ 最新のTensorFlow 2.13.0を使用
- ✅ Node.js 18（LTS）でJavaScriptの処理が高速化
- ✅ すべての依存関係が自動的にインストール
- ✅ 再現可能な環境で一貫した動作
- ✅ GPU対応（オプション）

この環境により、JavaScriptファイルのベクトル化を簡単かつ確実に実行できます。
