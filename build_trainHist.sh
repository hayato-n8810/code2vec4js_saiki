
DATASET_NAME=js_dataset_min5
HISTO_DIR="data/${DATASET_NAME}"
WORD_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.ori.c2v"
PATH_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.path.c2v"
TARGET_HISTO="${HISTO_DIR}/${DATASET_NAME}.histo.tgt.c2v"

MODEL_DIR="/model/${DATASET_NAME}"

# モデルの特性に合わせるため，学習時の語彙データを作成
TRAIN_DIR=/data/sampling/train
TRAIN_DATA_FILE=${DATASET_NAME}.train.raw.txt
mkdir -p data
mkdir -p data/${DATASET_NAME}

TARGET_HISTOGRAM_FILE=data/${DATASET_NAME}/${DATASET_NAME}.histo.tgt.c2v
ORIGIN_HISTOGRAM_FILE=data/${DATASET_NAME}/${DATASET_NAME}.histo.ori.c2v
PATH_HISTOGRAM_FILE=data/${DATASET_NAME}/${DATASET_NAME}.histo.path.c2v
# 特徴抽出
echo "Extracting paths from training set..."
${PYTHON} JSExtractor/extract.py --dir ${TRAIN_DIR} --max_path_length 8 --max_path_width 2 | shuf > ${TRAIN_DATA_FILE}
echo "Finished extracting paths from training set"
# 整形
echo "validating"
grep -E "^[a-zA-Z|]+\s" ${TRAIN_DATA_FILE} > ${TRAIN_DATA_FILE}.tmp
mv -f ${TRAIN_DATA_FILE}.tmp ${TRAIN_DATA_FILE}
# 語彙データ作成
echo "Creating histograms from the training data"
cat ${TRAIN_DATA_FILE} | cut -d' ' -f1 | awk '{n[$0]++} END {for (i in n) print i,n[i]}' > ${TARGET_HISTO}
cat ${TRAIN_DATA_FILE} | cut -d' ' -f2- | tr ' ' '\n' | cut -d',' -f1,3 | tr ',' '\n' | awk '{n[$0]++} END {for (i in n) print i,n[i]}' > ${ORIGIN_HISTO}
cat ${TRAIN_DATA_FILE} | cut -d' ' -f2- | tr ' ' '\n' | cut -d',' -f2 | awk '{n[$0]++} END {for (i in n) print i,n[i]}' > ${PATH_HISTO}

echo "Finished creating histograms from the training data"