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

# Logging function (both to file and stdout for parallel --line-buffer)
log_both() {
  local msg="[$(date '+%H:%M:%S')] [$project_name/$file_name] $*"
  echo "$msg" >> "$log_file" 2>/dev/null || true
  echo "$msg"  # Also to stdout for parallel to capture
}

log_both "[START] Processing"

# Output files (same naming as process_project_worker.sh)
base_name="$file_name"
raw_file="${c2v_dir}/${base_name}.test.raw.txt"
c2v_file="${c2v_dir}/${base_name}.test.c2v"
vectors_file="${c2v_file}.vectors"
out_vector="${vector_dir}/${base_name}.vector"

# Skip if already processed
if [ -f "$out_vector" ]; then
  log_both "[SKIP] ${base_name}.vector already exists"
  exit 0
fi

# Step 1: Extract (same as process_project_worker.sh)
if ! $PYTHON_BIN /code2vec/JSExtractor/extract.py \
    --file "$js_file" \
    --whole_file \
    --max_path_length 8 \
    --max_path_width 2 \
    > "$raw_file" 2>/dev/null; then
  log_both "[ERROR] Extraction failed: $base_name"
  rm -f "$raw_file"
  exit 0
fi

# Step 2: Validate (same as process_project_worker.sh)
if ! grep -E "^[a-zA-Z|]+\s" "$raw_file" > "${raw_file}.tmp" 2>/dev/null; then
  log_both "[WARN] No valid lines after validation: $base_name"
  rm -f "$raw_file" "${raw_file}.tmp"
  exit 0
fi
mv -f "${raw_file}.tmp" "$raw_file" 2>/dev/null

if [ ! -s "$raw_file" ]; then
  log_both "[WARN] Empty after validation: $base_name"
  rm -f "$raw_file"
  exit 0
fi

# Step 3: Preprocess (with retry mechanism - same as process_project_worker.sh)
MAX_RETRIES=2
preprocess_success=false

for retry in $(seq 1 $MAX_RETRIES); do
  if $PYTHON_BIN /code2vec/ql2vec/preprocess_test.py \
      --test_data "$raw_file" \
      --max_contexts "$MAX_CONTEXTS" \
      --word_vocab_size "$WORD_VOCAB_SIZE" \
      --path_vocab_size "$PATH_VOCAB_SIZE" \
      --target_vocab_size "$TARGET_VOCAB_SIZE" \
      --word_histogram "$WORD_HISTO" \
      --path_histogram "$PATH_HISTO" \
      --target_histogram "$TARGET_HISTO" \
      --output_name "${c2v_dir}/${base_name}" 2>&1; then
    preprocess_success=true
    break
  else
    if [ $retry -lt $MAX_RETRIES ]; then
      log_both "[RETRY $retry/$MAX_RETRIES] Preprocess failed, retrying: $base_name"
      sleep 1
    fi
  fi
done

if [ "$preprocess_success" = false ]; then
  log_both "[ERROR] Preprocess failed after $MAX_RETRIES attempts: $base_name"
  rm -f "$raw_file"
  exit 0
fi

if [ ! -s "$c2v_file" ]; then
  log_both "[WARN] No contexts produced: $base_name"
  rm -f "$raw_file" "$c2v_file"
  exit 0
fi

# Step 4: Vectorize (same as process_project_worker.sh)
# Suppress TensorFlow and code2vec verbose output
# Timeout: 15 minutes (covers P99 of processing time)
export TF_CPP_MIN_LOG_LEVEL=3  # Suppress TensorFlow C++ warnings

# Run with timeout using GNU timeout command
# - 900s = 15 minutes (recommended for production)
# - --kill-after=10s: Send SIGKILL if process doesn't terminate after SIGTERM
if ! timeout --kill-after=10s 900s $PYTHON_BIN /code2vec/ql2vec/code2vec_only.py \
    --load /code2vec/models/js_dataset_min5/saved_model_iter19.release \
    --test "$c2v_file" \
    --export_code_vectors >/dev/null 2>&1; then
  exit_code=$?
  if [ $exit_code -eq 124 ]; then
    log_both "[ERROR] Vectorization timeout (>15m): $base_name"
  elif [ $exit_code -eq 137 ] || [ $exit_code -eq 143 ]; then
    log_both "[ERROR] Vectorization killed (OOM or forced kill): $base_name"
  else
    log_both "[ERROR] Vectorization failed (exit code $exit_code): $base_name"
  fi
  # Cleanup and continue
  rm -f "$raw_file" "$c2v_file"
  exit 0
fi
unset TF_CPP_MIN_LOG_LEVEL

if [ -s "$vectors_file" ]; then
  mv -f "$vectors_file" "$out_vector"
  log_both "[DONE] ${base_name}.vector"
else
  log_both "[WARN] Vector file not generated: $base_name"
  exit 0
fi

# Cleanup intermediates
rm -f "$raw_file"

exit 0
