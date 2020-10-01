FROM tensorflow/tensorflow:latest-gpu-py3

RUN apt-get update && apt-get upgrade -y &&\
    apt install -y nodejs npm

WORKDIR /code2vec/JSExtractor/JSExtractor
RUN npm install
