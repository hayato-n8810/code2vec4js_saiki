FROM tensorflow/tensorflow:2.13.0-gpu

# Install Node.js and GNU parallel (using NodeSource for newer version)
RUN apt-get update && \
    apt-get install -y curl parallel && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip3 install --no-cache-dir -U pandas numpy

# Set TensorFlow thread limits for efficient parallel execution
# With 35 cores available (3500%) and up to 10 parallel jobs:
# - Each code2vec process gets ~3.5 cores
# - Set conservative limits to prevent oversubscription
ENV OMP_NUM_THREADS=3
ENV TF_NUM_INTRAOP_THREADS=3
ENV TF_NUM_INTEROP_THREADS=1
ENV TF_FORCE_GPU_ALLOW_GROWTH=true

# Optimize GNU Parallel for resource management
ENV PARALLEL="--will-cite --memfree 2G --noswap"

# Set working directory and copy JSExtractor source
WORKDIR /code2vec/JSExtractor/JSExtractor
COPY JSExtractor/JSExtractor/package*.json ./

RUN npm install

# Set final working directory
WORKDIR /code2vec
