FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl build-essential gcc g++ && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m spacy download it_core_news_lg

COPY . .

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
