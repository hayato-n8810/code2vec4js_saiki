FROM tensorflow/tensorflow:2.13.0-gpu

# Install Node.js (using NodeSource for newer version)
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip3 install --no-cache-dir -U pandas numpy

# Set working directory and copy JSExtractor source
WORKDIR /code2vec/JSExtractor/JSExtractor
COPY JSExtractor/JSExtractor/package*.json ./

RUN npm install

# Set final working directory
WORKDIR /code2vec
