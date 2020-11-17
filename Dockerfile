FROM tensorflow/tensorflow:2.0.1-gpu-py3

RUN apt-get update && apt-get upgrade -y &&\
    apt install -y nodejs npm

RUN pip3 install -U pandas

WORKDIR /code2vec/JSExtractor/JSExtractor
RUN npm install
