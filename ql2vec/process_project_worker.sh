#!/usr/bin/env bash
# Worker script for processing a single project
# Called by jscode2vec_parallel.sh via GNU parallel

set -u
set -o pipefail

project_dir="$1"
project_name=$(basename "$project_dir")

# Setup output directories
output_base="/code2vec/results/${project_name}"
c2v_dir="${output_base}/c2v"
vector_dir="${output_base}/vectors"
log_file="${output_base}/process.log"
context_count_file="${c2v_dir}/context_count.json"

mkdir -p "$c2v_dir" "$vector_dir" "$(dirname "$log_file")" 2>/dev/null || true

# Initialize context count JSON file
echo "{" > "$context_count_file"

# Cleanup function for temporary files
cleanup_temp_files() {
  # Clean up intermediate files on exit/interrupt (but keep raw_file)
  if [ -n "${c2v_file:-}" ] && [ -f "$c2v_file" ]; then
    rm -f "$c2v_file"
  fi
  
  # Finalize context_count.json on exit
  if [ -f "$context_count_file" ]; then
    # Remove trailing comma if exists and close JSON
    sed -i '$ s/,$//' "$context_count_file" 2>/dev/null || sed -i '' '$ s/,$//' "$context_count_file" 2>/dev/null
    echo "}" >> "$context_count_file"
  fi
}

# Register cleanup on exit/interrupt (catches TERM, INT, EXIT)
trap cleanup_temp_files EXIT INT TERM

# Save original stdout for progress reporting
exec 3>&1

# Redirect all output to log file
exec > "$log_file" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [START] Processing project: $project_name"

# Find all .js files in this project
js_files=()
while IFS= read -r -d '' file; do
  js_files+=("$file")
done < <(find "$project_dir" -type f -name "*.js" -print0 | sort -z)

if [ ${#js_files[@]} -eq 0 ]; then
  echo "[WARN] No .js files found in $project_name"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [END] $project_name (no files)"
  exit 0
fi

echo "[INFO] Found ${#js_files[@]} JS file(s) in $project_name"

success_count=0
skip_count=0
error_count=0
first_entry=true

# Helper function to count contexts in raw file
count_contexts() {
  local file="$1"
  if [ ! -f "$file" ] || [ ! -s "$file" ]; then
    echo 0
    return
  fi
  
  # Count total contexts (space-separated fields minus target name)
  awk '{print NF-1}' "$file" | awk '{sum+=$1} END {print sum+0}'
}

# Helper function to add JSON entry
add_context_count() {
  local filename="$1"
  local count="$2"
  
  if [ "$first_entry" = true ]; then
    echo "  \"$filename\": $count" >> "$context_count_file"
    first_entry=false
  else
    echo "," >> "$context_count_file"
    echo "  \"$filename\": $count" >> "$context_count_file"
  fi
}

for jsf in "${js_files[@]}"; do
  base_name=$(basename "$jsf" .js)
  raw_file="${c2v_dir}/${base_name}.test.raw.txt"
  c2v_file="${c2v_dir}/${base_name}.test.c2v"
  vectors_file="${c2v_file}.vectors"
  out_vector="${vector_dir}/${base_name}.vector"
  
  # Skip if already processed
  if [ -f "$out_vector" ]; then
    echo "[SKIP] ${base_name}.vector already exists"
    ((skip_count++))
    
    # Count contexts from existing raw file
    if [ -f "$raw_file" ]; then
      context_count=$(count_contexts "$raw_file")
      add_context_count "$base_name" "$context_count"
    else
      add_context_count "$base_name" "\"error\""
    fi
    continue
  fi
  
  # Step 1: Extract
  if ! timeout --kill-after=10s 480s $PYTHON_BIN /code2vec/JSExtractor/extract.py \
      --file "$jsf" \
      --whole_file \
      --max_path_length 8 \
      --max_path_width 2 \
      > "$raw_file" 2>/dev/null; then
    echo "[ERROR] Extraction failed: $base_name"
    ((error_count++))
    add_context_count "$base_name" "\"error\""
    rm -f "$raw_file"
    continue
  fi
  
  # Step 2: Validate
  if ! grep -E "^[a-zA-Z|]+\s" "$raw_file" > "${raw_file}.tmp" 2>/dev/null; then
    echo "[WARN] No valid lines after validation: $base_name"
    ((error_count++))
    add_context_count "$base_name" 0
    rm -f "${raw_file}.tmp"
    # Keep raw_file for debugging
    continue
  fi
  mv -f "${raw_file}.tmp" "$raw_file" 2>/dev/null
  
  if [ ! -s "$raw_file" ]; then
    echo "[WARN] Empty after validation: $base_name"
    ((error_count++))
    add_context_count "$base_name" 0
    # Keep raw_file for debugging
    continue
  fi
  
  # Count contexts after validation
  context_count=$(count_contexts "$raw_file")
  add_context_count "$base_name" "$context_count"
  
  # Step 3: Preprocess (with retry mechanism)
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
        echo "[RETRY $retry/$MAX_RETRIES] Preprocess failed, retrying: $base_name"
        sleep 1
      fi
    fi
  done
  
  if [ "$preprocess_success" = false ]; then
    echo "[ERROR] Preprocess failed after $MAX_RETRIES attempts: $base_name"
    ((error_count++))
    rm -f "$raw_file"
    continue
  fi
  
  if [ ! -s "$c2v_file" ]; then
    echo "[WARN] No contexts produced: $base_name"
    ((error_count++))
    # Keep raw_file for debugging
    continue
  fi
  
  # Step 4: Vectorize
  # Suppress TensorFlow and code2vec verbose output
  # Timeout: 15 minutes (covers P99 of processing time)
  export TF_CPP_MIN_LOG_LEVEL=3  # Suppress TensorFlow C++ warnings
  
  # Use MODEL_PATH environment variable (defaults to js_dataset_min5 iter19)
  MODEL_PATH=${MODEL_PATH:-/code2vec/models/js_dataset_min5/saved_model_iter19.release}
  
  # Run with timeout using GNU timeout command
  # - 900s = 15 minutes (recommended for production)
  # - --kill-after=10s: Send SIGKILL if process doesn't terminate after SIGTERM
  if ! timeout --kill-after=10s 900s $PYTHON_BIN /code2vec/ql2vec/code2vec_only.py \
      --load "$MODEL_PATH" \
      --test "$c2v_file" \
      --export_code_vectors >/dev/null 2>&1; then
    exit_code=$?
    if [ $exit_code -eq 124 ]; then
      echo "[ERROR] Vectorization timeout (>15m): $base_name"
    elif [ $exit_code -eq 137 ] || [ $exit_code -eq 143 ]; then
      echo "[ERROR] Vectorization killed (OOM or forced kill): $base_name"
    else
      echo "[ERROR] Vectorization failed (exit code $exit_code): $base_name"
    fi
    ((error_count++))
    continue
  fi
  unset TF_CPP_MIN_LOG_LEVEL
  
  if [ -s "$vectors_file" ]; then
    mv -f "$vectors_file" "$out_vector"
    echo "[DONE] ${base_name}.vector"
    ((success_count++))
    # Keep raw_file for reference, only cleanup c2v intermediate file
  else
    echo "[WARN] Vector file not generated: $base_name"
    ((error_count++))
  fi
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SUMMARY] $project_name"
echo "  Total files: ${#js_files[@]}"
echo "  Success: $success_count"
echo "  Skipped: $skip_count"
echo "  Errors: $error_count"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [END] $project_name"

# Output completion marker to original stdout (fd 3) for progress tracking
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [END] $project_name" >&3

# Cleanup handled by trap

