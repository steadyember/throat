FROM node:14-buster-slim

EXPOSE 5000

WORKDIR /throat

COPY requirements.txt package.json package-lock.json* ./

RUN \
  useradd -ms /bin/bash app \
  && apt-get update && apt-get install -yqq \
     build-essential \
     python3-dev \
     python3-pip \
     libgirepository1.0-dev \
     libcairo2-dev \
     libgexiv2-dev \
     libpq-dev \
     postgresql-client \
  && pip3 install -r requirements.txt \
  && npm install && npm cache clean --force \
  && rm -rf /var/lib/apt/lists/*

COPY . .

RUN npm run build  \
  && chown -R app:app .

USER app

CMD ["./throat.py"]
