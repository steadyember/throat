FROM node:14-buster-slim

COPY requirements.txt /requirements.txt
COPY package.json /package.json
COPY package-lock.json /package-lock.json

RUN useradd -ms /bin/bash app

RUN \
  apt-get update && apt-get install -yqq \
     build-essential \
     python3-dev \
     python3-pip \
     libgirepository1.0-dev \
     libcairo2-dev \
     libgexiv2-dev \
     libpq-dev \
     postgresql-client \
  # Install our python requirements
  && pip3 install -r requirements.txt && rm requirements.txt \
  # Install our npm requirements
  && npm ci && rm package.json && rm package-lock.json \
  # Clean Up
  && rm -rf /var/lib/apt/lists/*

COPY . /throat
WORKDIR /throat
RUN mv ../node_modules node_modules && npm run build

RUN \
  mv ../node_modules node_modules \
  && npm run build \
  && chown -R app:app .

USER app
EXPOSE 5000

CMD ["./throat.py"]
