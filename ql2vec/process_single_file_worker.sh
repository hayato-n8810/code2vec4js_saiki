#!/usr/bin/env bash
# Simple worker for processing a single JS file with shared memory histograms
# Called by jscode2vec_file_parallel_shm.sh

set -u
set -o pipefail

js_file="$1"

if [ ! -f "$js_file" ]; then
  echo "[ERROR] File not found: $js_file" >&2
  exit 1
fi

# Extract project info
project_name=$(basename "$(dirname "$js_file")")
file_name=$(basename "$js_file" .js)

# Setup output directories
output_base="/code2vec/results/${project_name}"
c2v_dir="${output_base}/c2v"
vector_dir="${output_base}/vectors"
log_file="${output_base}/process.log"

mkdir -p "$c2v_dir" "$vector_dir" "$(dirname "$log_file")" 2>/dev/null || true

# Thread-safe logging
log_safe() {
  echo "[$(date '+%H:%M:%S')] $*" >> "$log_file" 2>/dev/null || true
}

log_safe "[START] Processing: $file_name"

# Output files
raw_file="${c2v_dir}/${file_name}.test.raw.txt"
c2v_file="${c2v_dir}/${file_name}.test.c2v"
vectors_file="${c2v_file}.vectors"
out_vector="${vector_dir}/${file_name}.vector"

# Skip if already exists
if [ -f "$out_vector" ]; then
  log_safe "[SKIP] Already exists: $file_name"
  exit 0
fi

# Step 1: Extract with JavaExtractor (generates raw)
log_safe "[1/3] Extracting AST paths..."
if ! "$PYTHON_BIN" /code2vec/JavaExtractor/extract.py \
  --file "$js_file" \
  --max_contexts "$MAX_CONTEXTS" \
  --output "$raw_file" >/dev/null 2>&1; then
  log_safe "[ERROR] Extraction failed: $file_name"
  exit 0  # Continue to next file
fi

if [ ! -s "$raw_file" ]; then
  log_safe "[SKIP] Empty extraction: $file_name"
  exit 0
fi

# Step 2: Preprocess (raw -> c2v using shared memory histograms)
log_safe "[2/3] Preprocessing with shared memory..."
if ! timeout 120s "$PYTHON_BIN" /code2vec/ql2vec/preprocess_test.py \
  --test_data "$raw_file" \
  --data_dir "/code2vec/data/js_dataset_min5" \
  --max_contexts "$MAX_CONTEXTS" \
  --word_vocab_size "$WORD_VOCAB_SIZE" \
  --path_vocab_size "$PATH_VOCAB_SIZE" \
  --target_vocab_size "$TARGET_VOCAB_SIZE" >/dev/null 2>&1; then
  log_safe "[ERROR] Preprocessing failed: $file_name"
  exit 0
fi

if [ ! -s "$c2v_file" ]; then
  log_safe "[SKIP] Empty c2v: $file_name"
  exit 0
fi

# Step 3: Vectorize (c2v -> vectors)
log_safe "[3/3] Vectorizing..."
if ! "$PYTHON_BIN" /code2vec/export_test_vec.py \
  --load models/js_dataset_min5/saved_model_iter8 \
  --test "$c2v_file" >/dev/null 2>&1; then
  log_safe "[ERROR] Vectorization failed: $file_name"
  exit 0
fi

if [ ! -s "$vectors_file" ]; then
  log_safe "[ERROR] No vectors generated: $file_name"
  exit 0
fi

# Move to final location
mv "$vectors_file" "$out_vector" 2>/dev/null || true

if [ -s "$out_vector" ]; then
  log_safe "[OK] Success: $file_name"
else
  log_safe "[ERROR] Final output missing: $file_name"
fi

exit 0
