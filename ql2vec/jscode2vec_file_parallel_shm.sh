#!/usr/bin/env bash

# Revolutionary File-Level Parallel Vectorization with Shared Memory Histograms
# ==============================================================================
#
# Key Innovation: Histograms are loaded ONCE into shared memory
# - Zero disk I/O contention (all workers read from RAM)
# - Zero memory duplication (single copy shared by all)
# - Supports unlimited parallelization
#
# Usage:
#   ./jscode2vec_file_parallel_shm.sh /absolute/path/to/target_dir_js [max_parallel_jobs]

set -u
set -o pipefail

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "[ERROR] Usage: $0 /absolute/path/to/target_dir_js [max_parallel_jobs]" >&2
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

# Export variables for worker
export PYTHON_BIN MAX_CONTEXTS WORD_VOCAB_SIZE PATH_VOCAB_SIZE TARGET_VOCAB_SIZE
export WORD_HISTO PATH_HISTO TARGET_HISTO TARGET_BASE_DIR MODEL_PATH
export OMP_NUM_THREADS MKL_NUM_THREADS OPENBLAS_NUM_THREADS

# ---------- Shared Memory Histogram Server ----------
echo ""
echo "============================================================"
echo "  Revolutionary Shared Memory Histogram Approach"
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
# Note: Suppress stderr (TensorFlow warnings) and check for metadata file
METADATA_FILE="/tmp/code2vec_histograms_${DATASET_NAME}_metadata.json"
if [ -f "$METADATA_FILE" ] && $PYTHON_BIN "$HISTOGRAM_SERVER_SCRIPT" status 2>/dev/null | grep -q "Server Status: RUNNING"; then
  echo "[INFO] Histogram server already running, using existing instance"
  SERVER_OWNER=false
  
  # Get shared memory name from metadata (file already exists, checked above)
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
  # METADATA_FILE already defined at the top of this if-else block
  
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

# ---------- Main Execution ----------

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting file-level parallel vectorization (SHM mode)"
echo "[INFO] Base directory: $TARGET_BASE_DIR"
echo "[INFO] Max parallel jobs: $MAX_PARALLEL_JOBS"
echo "[INFO] Histogram mode: SHARED MEMORY (zero disk I/O)"

# Count files
echo "[INFO] Scanning for JS files..."
total_files=$(find "$TARGET_BASE_DIR" -type f -name "*.js" | wc -l)
echo "[INFO] Found ${total_files} JS file(s) across all projects"

# Job logging
JOBLOG_FILE="/code2vec/results/parallel_jobs_shm.log"
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

# Process files in parallel (similar to jscode2vec_parallel.sh)
# CRITICAL: Use --env to pass ALL required variables to workers
find "$TARGET_BASE_DIR" -type f -name "*.js" -print0 | \
  parallel -0 \
    -j "$MAX_PARALLEL_JOBS" \
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
    /code2vec/ql2vec/process_single_file_worker.sh {}

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] All files processed"
echo "[INFO] Check project logs at: results/{project_name}/process.log"
echo ""
echo "============================================================"
echo "  Processing Complete!"
echo "============================================================"

# Server cleanup handled by trap
