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
MAX_PARALLEL_JOBS=${2:-10}  # Default: 10 parallel projects (each uses ~3-4 cores)

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
HISTO_DIR="data/${DATASET_NAME}"
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
    ./process_project_worker.sh {}

echo "[$(date '+%Y-%m-%d %H:%M:%S')] All projects processed"
echo "[INFO] Check individual logs at: results/{project_name}/process.log"
