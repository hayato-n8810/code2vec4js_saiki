#!/usr/bin/env bash

# Parallel vectorization pipeline for multiple JS projects with Shared Memory
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
  echo "  max_parallel_jobs: defaults to auto-detect (60% of CPU cores)" >&2
  exit 1
fi

TARGET_BASE_DIR="$1"

# Detect available cores (always needed for thread calculation)
if command -v nproc >/dev/null 2>&1; then
  AVAILABLE_CORES=$(nproc)
elif command -v sysctl >/dev/null 2>&1; then
  AVAILABLE_CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
else
  AVAILABLE_CORES=4
fi

# Auto-detect parallel jobs
if [ $# -ge 2 ]; then
  MAX_PARALLEL_JOBS="$2"
else
  MAX_PARALLEL_JOBS=$((AVAILABLE_CORES * 60 / 100))
  
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

# Memory optimization
export TF_FORCE_GPU_ALLOW_GROWTH=true
export TF_CPP_MIN_LOG_LEVEL=3

THREADS_PER_PROCESS=$((MAX_PARALLEL_JOBS > 0 ? (AVAILABLE_CORES / MAX_PARALLEL_JOBS) : 1))
if [ "$THREADS_PER_PROCESS" -lt 1 ]; then
  THREADS_PER_PROCESS=1
fi
export OMP_NUM_THREADS=$THREADS_PER_PROCESS
export MKL_NUM_THREADS=$THREADS_PER_PROCESS
export OPENBLAS_NUM_THREADS=$THREADS_PER_PROCESS

DATASET_NAME=js_dataset_min5
HISTO_DIR="/code2vec/data/${DATASET_NAME}"
WORD_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.ori.c2v"
PATH_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.path.c2v"
TARGET_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.tgt.c2v"
MODEL_PATH="/code2vec/models/${DATASET_NAME}/saved_model_iter19.release"

# Validate histograms
for f in "$WORD_HISTO" "$PATH_HISTO" "$TARGET_HISTO"; do
  if [ ! -f "$f" ]; then
    echo "[ERROR] Histogram not found: $f" >&2
    exit 1
  fi
done

# Validate model
if [ ! -f "${MODEL_PATH}.meta" ]; then
  echo "[ERROR] Model not found: ${MODEL_PATH}.meta" >&2
  exit 1
fi

# Export variables for worker script
export PYTHON_BIN MAX_CONTEXTS WORD_VOCAB_SIZE PATH_VOCAB_SIZE TARGET_VOCAB_SIZE
export WORD_HISTO PATH_HISTO TARGET_HISTO TARGET_BASE_DIR MODEL_PATH
export OMP_NUM_THREADS MKL_NUM_THREADS OPENBLAS_NUM_THREADS

# ---------- Shared Memory Histogram Server ----------
echo ""
echo "============================================================"
echo "  Project-Level Parallel Processing with Shared Memory"
echo "============================================================"
echo ""

HISTOGRAM_SERVER_SCRIPT="/code2vec/ql2vec/histogram_server.py"
HISTOGRAM_SERVER_PID=""
SERVER_OWNER=false  # Track if we started the server

# Cleanup function
cleanup_histogram_server() {
  # Only stop server if we started it
  if [ "$SERVER_OWNER" = true ]; then
    echo ""
    echo "[INFO] Stopping histogram server (we started it)..."
    $PYTHON_BIN "$HISTOGRAM_SERVER_SCRIPT" stop || true
    if [ -n "$HISTOGRAM_SERVER_PID" ]; then
      wait $HISTOGRAM_SERVER_PID 2>/dev/null || true
    fi
    echo "[OK] Histogram server stopped"
  else
    # We're using an existing server, don't stop it
    if [ -n "$HISTOGRAM_SERVER_PID" ]; then
      echo ""
      echo "[INFO] Leaving shared histogram server running (shared by multiple processes)"
    fi
  fi
}

# Register cleanup on exit (catches EXIT, SIGINT, SIGTERM)
trap cleanup_histogram_server EXIT INT TERM

# Check if server is already running
METADATA_FILE="/tmp/code2vec_histograms_${DATASET_NAME}_metadata.json"
if [ -f "$METADATA_FILE" ] && $PYTHON_BIN "$HISTOGRAM_SERVER_SCRIPT" status 2>/dev/null | grep -q "Server Status: RUNNING"; then
  echo "[INFO] Histogram server already running, using existing instance"
  SERVER_OWNER=false
  
  # Get shared memory name from metadata
  export HISTOGRAM_SHM_NAME=$(grep -o '"shm_name": "[^"]*"' "$METADATA_FILE" | cut -d'"' -f4)
  export HISTOGRAM_SHM_SIZE=$(grep -o '"size": [0-9]*' "$METADATA_FILE" | awk '{print $2}')
  echo "[INFO] Using shared memory: $HISTOGRAM_SHM_NAME ($HISTOGRAM_SHM_SIZE bytes)"
else
  echo "[INFO] Starting histogram shared memory server..."
  echo "[INFO] This loads histograms ONCE into RAM for all workers"
  echo ""
  
  SERVER_OWNER=true  # We're starting the server
  
  # Start server in background
  $PYTHON_BIN "$HISTOGRAM_SERVER_SCRIPT" \
    --dataset "$DATASET_NAME" \
    --word_vocab_size "$WORD_VOCAB_SIZE" \
    --path_vocab_size "$PATH_VOCAB_SIZE" \
    --target_vocab_size "$TARGET_VOCAB_SIZE" \
    start &
  
  HISTOGRAM_SERVER_PID=$!
  
  # Wait for server to be ready
  echo "[INFO] Waiting for server to initialize..."
  
  for i in {1..30}; do
    if [ -f "$METADATA_FILE" ]; then
      export HISTOGRAM_SHM_NAME=$(grep -o '"shm_name": "[^"]*"' "$METADATA_FILE" | cut -d'"' -f4)
      export HISTOGRAM_SHM_SIZE=$(grep -o '"size": [0-9]*' "$METADATA_FILE" | awk '{print $2}')
      echo ""
      echo "[OK] Histogram server ready!"
      echo "[INFO] Shared Memory: $HISTOGRAM_SHM_NAME"
      echo "[INFO] Size: $(echo "scale=2; $HISTOGRAM_SHM_SIZE / 1024 / 1024" | bc) MB"
      echo ""
      break
    fi
    sleep 1
    
    if [ $i -eq 30 ]; then
      echo "[ERROR] Histogram server failed to start" >&2
      exit 1
    fi
  done
fi

# ---------- Main execution ----------

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting project-level parallel vectorization (SHM mode)"
echo "[INFO] Base directory: $TARGET_BASE_DIR"
echo "[INFO] Max parallel jobs: $MAX_PARALLEL_JOBS"
echo "[INFO] Histogram mode: SHARED MEMORY (zero disk I/O)"

# Find all project directories
mapfile -t PROJECT_DIRS < <(find "$TARGET_BASE_DIR" -mindepth 1 -maxdepth 1 -type d | sort)

if [ ${#PROJECT_DIRS[@]} -eq 0 ]; then
  echo "[ERROR] No project directories found in $TARGET_BASE_DIR" >&2
  exit 1
fi

echo "[INFO] Found ${#PROJECT_DIRS[@]} project(s)"

# Job logging
JOBLOG_FILE="/code2vec/results/parallel_projects_shm.log"
mkdir -p "$(dirname "$JOBLOG_FILE")"

echo "[INFO] Parallel execution settings:"
echo "  - Parallel jobs: ${MAX_PARALLEL_JOBS}"
echo "  - Job log: ${JOBLOG_FILE}"
echo "  - Histogram I/O: ZERO (shared memory)"
echo ""

# Debug: Show environment variables
if [ -n "${HISTOGRAM_SHM_NAME:-}" ]; then
  echo "[DEBUG] Shared memory env vars:"
  echo "  HISTOGRAM_SHM_NAME=$HISTOGRAM_SHM_NAME"
  echo "  HISTOGRAM_SHM_SIZE=$HISTOGRAM_SHM_SIZE"
  echo ""
fi

# Process projects in parallel (with environment variable propagation)
printf '%s\n' "${PROJECT_DIRS[@]}" | \
  parallel -j "$MAX_PARALLEL_JOBS" \
    --line-buffer \
    --joblog "$JOBLOG_FILE" \
    --env HISTOGRAM_SHM_NAME \
    --env HISTOGRAM_SHM_SIZE \
    --env PYTHON_BIN \
    --env MAX_CONTEXTS \
    --env WORD_VOCAB_SIZE \
    --env PATH_VOCAB_SIZE \
    --env TARGET_VOCAB_SIZE \
    --env WORD_HISTO \
    --env PATH_HISTO \
    --env TARGET_HISTO \
    --env TARGET_BASE_DIR \
    --env MODEL_PATH \
    /code2vec/ql2vec/process_project_worker.sh {}

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] All projects processed"
echo "[INFO] Check individual logs at: results/{project_name}/process.log"
echo ""
echo "============================================================"
echo "  Processing Complete!"
echo "============================================================"

# Server cleanup handled by trap
