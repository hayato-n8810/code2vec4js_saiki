#!/usr/bin/env bash

# Vectorize-only pipeline for JS files under a directory.
# For each *.js file under target_dir_js, this script:
#  1) Extracts path contexts (raw)
#  2) Preprocesses to match the model's MAX_CONTEXTS using training histograms
#  3) Runs code2vec inference and writes {filename}.vector next to the source
#
# Usage:
#   ./jscode2vec_only.sh /absolute/path/to/target_dir_js
#
# Requirements (project-conformant):
# - Use the pre-trained model at /model/js_dataset_min5 (mounted/accessible)
# - Use histograms from data/js_dataset_min5/*.histo.*.c2v
# - MAX_CONTEXTS, vocab sizes, and extractor params align with preprocess.sh

set -u
set -o pipefail

if [ $# -ne 1 ]; then
  echo "[ERROR] target_dir_js path is required." >&2
  echo "Usage: $0 /absolute/path/to/target_dir_js" >&2
  exit 1
fi

TARGET_DIR_JS="$1"
if [ ! -d "$TARGET_DIR_JS" ]; then
  echo "[ERROR] Directory not found: $TARGET_DIR_JS" >&2
  exit 1
fi

# ---------- Configuration (must match the trained model) ----------
PYTHON_BIN=${PYTHON_BIN:-python3}

# From preprocess.sh for js_dataset_min5
MAX_CONTEXTS=${MAX_CONTEXTS:-200}
WORD_VOCAB_SIZE=${WORD_VOCAB_SIZE:-1301136}
PATH_VOCAB_SIZE=${PATH_VOCAB_SIZE:-911417}
TARGET_VOCAB_SIZE=${TARGET_VOCAB_SIZE:-261245}

DATASET_NAME=js_dataset_min5
HISTO_DIR="/code2vec/data/${DATASET_NAME}"
WORD_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.ori.c2v"
PATH_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.path.c2v"
TARGET_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.tgt.c2v"

MODEL_DIR="/code2vec/models/${DATASET_NAME}"

# 学習で用いた語彙データの存在を検証
for f in "$WORD_HISTO" "$PATH_HISTO" "$TARGET_HISTO"; do
  if [ ! -f "$f" ]; then
    echo "[ERROR] Histogram not found: $f" >&2
    echo "        Ensure training histograms exist: data/${DATASET_NAME}/${DATASET_NAME}.histo.*.c2v" >&2
    exit 1
  fi
done

# ---------- Output directory setup ----------
# Extract project name from target directory (e.g., /path/to/target_dir_js -> target_dir_js)
PROJECT_NAME=$(basename "$TARGET_DIR_JS")
OUTPUT_BASE_DIR="results/${PROJECT_NAME}"
C2V_OUTPUT_DIR="${OUTPUT_BASE_DIR}/c2v"
VECTOR_OUTPUT_DIR="${OUTPUT_BASE_DIR}/vectors"

mkdir -p "$C2V_OUTPUT_DIR"
mkdir -p "$VECTOR_OUTPUT_DIR"

echo "[INFO] Project: $PROJECT_NAME"
echo "[INFO] C2V output: $C2V_OUTPUT_DIR"
echo "[INFO] Vector output: $VECTOR_OUTPUT_DIR"

# ---------- Per-file processing ----------

# Find .js files recursively
mapfile -t JS_FILES < <(find "$TARGET_DIR_JS" -type f -name "*.js" | sort)

if [ ${#JS_FILES[@]} -eq 0 ]; then
  echo "[WARN] No .js files found under $TARGET_DIR_JS"
  exit 0
fi

for jsf in "${JS_FILES[@]}"; do
  # Extract filename without extension (e.g., target_dir_js_123.js -> target_dir_js_123)
  base_name=$(basename "$jsf" .js)
  
  # Output paths in results directory
  raw_file="${C2V_OUTPUT_DIR}/${base_name}.test.raw.txt"
  c2v_file="${C2V_OUTPUT_DIR}/${base_name}.test.c2v"
  vectors_file="${C2V_OUTPUT_DIR}/${base_name}.test.c2v.vectors"
  out_vector="${VECTOR_OUTPUT_DIR}/${base_name}.vector"

  # Output paths in results directory
  raw_file="${C2V_OUTPUT_DIR}/${base_name}.test.raw.txt"
  c2v_file="${C2V_OUTPUT_DIR}/${base_name}.test.c2v"
  vectors_file="${C2V_OUTPUT_DIR}/${base_name}.test.c2v.vectors"
  out_vector="${VECTOR_OUTPUT_DIR}/${base_name}.vector"

  # Skip if vector already exists
  if [ -f "$out_vector" ]; then
    echo "[SKIP] $out_vector already exists; skipping $jsf"
    continue
  fi

  echo "[STEP] Extracting paths: $base_name"
  # Extract per-file features
  if ! $PYTHON_BIN /code2vec/JSExtractor/extract.py \
      --file "$jsf" \
      --whole_file \
      --max_path_length 8 \
      --max_path_width 2 \
      > "$raw_file"; then
    echo "[ERROR] Extraction failed for: $jsf" >&2
    rm -f "$raw_file"
    continue
  fi

  # Validate lines (same as preprocess.sh)
  # Remove invalid lines; if none remain, skip
  if ! grep -E "^[a-zA-Z|]+\s" "$raw_file" > "${raw_file}.tmp"; then
    rm -f "$raw_file" "${raw_file}.tmp"
    echo "[WARN] No valid lines after validation: $jsf (skipping)"
    continue
  fi
  mv -f "${raw_file}.tmp" "$raw_file"
  if [ ! -s "$raw_file" ]; then
    rm -f "$raw_file"
    echo "[WARN] Empty after validation: $jsf (skipping)"
    continue
  fi

  echo "[STEP] Preprocessing to MAX_CONTEXTS=$MAX_CONTEXTS"
  # Use base_name without extension for output_name
  # ベクトル化するために，code2vecの入力形式に合わせたデータに変換
  if ! $PYTHON_BIN /code2vec/ql2vec/preprocess_test.py \
      --test_data "$raw_file" \
      --max_contexts "$MAX_CONTEXTS" \
      --word_vocab_size "$WORD_VOCAB_SIZE" \
      --path_vocab_size "$PATH_VOCAB_SIZE" \
      --target_vocab_size "$TARGET_VOCAB_SIZE" \
      --word_histogram "$WORD_HISTO" \
      --path_histogram "$PATH_HISTO" \
      --target_histogram "$TARGET_HISTO" \
      --output_name "${C2V_OUTPUT_DIR}/${base_name}"; then
    echo "[ERROR] Preprocess failed for: $jsf" >&2
    rm -f "$raw_file"
    continue
  fi

  # If no c2v produced or empty, skip
  if [ ! -s "$c2v_file" ]; then
    echo "[WARN] No contexts produced for: $base_name (skipping)" >&2
    rm -f "$raw_file" "$c2v_file"
    continue
  fi

  echo "[STEP] Exporting vectors"
  if ! $PYTHON_BIN /code2vec/ql2vec/code2vec_only.py \
      --load /code2vec/models/js_dataset_min5/saved_model_iter19.release \
      --test "$c2v_file" \
      --export_code_vectors; then
    echo "[ERROR] code2vec inference failed for: $base_name" >&2
    # Still attempt to collect vectors if they were written
  fi

  if [ -s "$vectors_file" ]; then
    mv -f "$vectors_file" "$out_vector"
    echo "[DONE] Wrote vectors: $out_vector"
  else
    echo "[WARN] Vectors not generated: $base_name" >&2
  fi

  # Cleanup intermediates (keep c2v for inspection, remove raw and temp vectors)
  rm -f "$raw_file" "$vectors_file"
done

echo "[ALL DONE] Processed ${#JS_FILES[@]} JS files under: $TARGET_DIR_JS"
echo "[OUTPUT] C2V files: $C2V_OUTPUT_DIR"
echo "[OUTPUT] Vectors: $VECTOR_OUTPUT_DIR"
