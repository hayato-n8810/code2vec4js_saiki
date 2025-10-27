#!/usr/bin/env bash

# Parallel vectorization pipeline for multiple JS projects
# Processes multiple projects in parallel using GNU parallel
#
# Usage:
#   ./jscode2vec_parallel.sh /absolute/path/to/target_dir_js [max_parallel_jobs]
#
# Structure:
#   /absolute/path/to/target_dir_js/
#     project1/
#       project1_0.js
#       project1_1.js
#     project2/
#       project2_0.js
#       ...
#
# Output:
#   results/project1/c2v/*.c2v
#   results/project1/vectors/*.vector
#   results/project1/process.log

set -u
set -o pipefail

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "[ERROR] Usage: $0 /absolute/path/to/target_dir_js [max_parallel_jobs]" >&2
  echo "  max_parallel_jobs: defaults to 10 (for 3500% CPU = 35 cores)" >&2
  exit 1
fi

TARGET_BASE_DIR="$1"

# Default parallel jobs (adjust based on available CPU cores)
# Auto-detect available cores and use conservative setting
if [ $# -ge 2 ]; then
  MAX_PARALLEL_JOBS="$2"
else
  # Auto-detect CPU cores
  if command -v nproc >/dev/null 2>&1; then
    AVAILABLE_CORES=$(nproc)
  elif command -v sysctl >/dev/null 2>&1; then
    AVAILABLE_CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
  else
    AVAILABLE_CORES=4
  fi
  
  # Use 60% of available cores (conservative, leaving headroom)
  MAX_PARALLEL_JOBS=$((AVAILABLE_CORES * 60 / 100))
  
  # Ensure at least 2, at most 16
  if [ "$MAX_PARALLEL_JOBS" -lt 2 ]; then
    MAX_PARALLEL_JOBS=2
  elif [ "$MAX_PARALLEL_JOBS" -gt 16 ]; then
    MAX_PARALLEL_JOBS=16
  fi
  
  echo "[INFO] Auto-detected $AVAILABLE_CORES CPU cores, using $MAX_PARALLEL_JOBS parallel jobs"
fi

if [ ! -d "$TARGET_BASE_DIR" ]; then
  echo "[ERROR] Directory not found: $TARGET_BASE_DIR" >&2
  exit 1
fi

# ---------- Configuration ----------
PYTHON_BIN=${PYTHON_BIN:-python3}
MAX_CONTEXTS=${MAX_CONTEXTS:-200}
WORD_VOCAB_SIZE=${WORD_VOCAB_SIZE:-1301136}
PATH_VOCAB_SIZE=${PATH_VOCAB_SIZE:-911417}
TARGET_VOCAB_SIZE=${TARGET_VOCAB_SIZE:-261245}

DATASET_NAME=js_dataset_min5
HISTO_DIR="/code2vec/data/${DATASET_NAME}"
WORD_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.ori.c2v"
PATH_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.path.c2v"
TARGET_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.tgt.c2v"

# Validate histograms
for f in "$WORD_HISTO" "$PATH_HISTO" "$TARGET_HISTO"; do
  if [ ! -f "$f" ]; then
    echo "[ERROR] Histogram not found: $f" >&2
    exit 1
  fi
done

# Export variables for worker script
export PYTHON_BIN MAX_CONTEXTS WORD_VOCAB_SIZE PATH_VOCAB_SIZE TARGET_VOCAB_SIZE
export WORD_HISTO PATH_HISTO TARGET_HISTO

# ---------- Optimization: Preload histograms ----------
HISTOGRAM_CACHE="${HISTO_DIR}/histogram_cache.pkl"

if [ ! -f "$HISTOGRAM_CACHE" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [OPTIMIZATION] Preloading histograms (first time only)..."
  echo "[INFO] This will speed up parallel processing significantly"
  
  if ! $PYTHON_BIN /code2vec/ql2vec/preload_histograms.py \
      --dataset "$DATASET_NAME" \
      --word_vocab_size "$WORD_VOCAB_SIZE" \
      --path_vocab_size "$PATH_VOCAB_SIZE" \
      --target_vocab_size "$TARGET_VOCAB_SIZE"; then
    echo "[WARN] Failed to create histogram cache, continuing with raw histograms" >&2
    echo "[WARN] Parallel execution may be slower and less stable" >&2
  else
    echo "[INFO] Histogram cache created successfully: $HISTOGRAM_CACHE"
  fi
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] Using cached histograms: $HISTOGRAM_CACHE"
fi

# ---------- Main execution ----------

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting parallel vectorization"
echo "[INFO] Base directory: $TARGET_BASE_DIR"
echo "[INFO] Max parallel jobs: $MAX_PARALLEL_JOBS"

# Find all project directories
mapfile -t PROJECT_DIRS < <(find "$TARGET_BASE_DIR" -mindepth 1 -maxdepth 1 -type d | sort)

if [ ${#PROJECT_DIRS[@]} -eq 0 ]; then
  echo "[ERROR] No project directories found in $TARGET_BASE_DIR" >&2
  exit 1
fi

echo "[INFO] Found ${#PROJECT_DIRS[@]} project(s)"

# Process projects in parallel using GNU parallel and worker script
printf '%s\n' "${PROJECT_DIRS[@]}" | \
  parallel -j "$MAX_PARALLEL_JOBS" --line-buffer \
    /code2vec/ql2vec/process_project_worker.sh {}

echo "[$(date '+%Y-%m-%d %H:%M:%S')] All projects processed"
echo "[INFO] Check individual logs at: results/{project_name}/process.log"
