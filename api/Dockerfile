FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl build-essential gcc g++ && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

RUN python -m spacy download it_core_news_lg

# Rizzo-PII 0.3B (MIT): pinned revision baked into the image, never downloaded at runtime.
ARG INCLUDE_RIZZO=false
ARG RIZZO_REPO=rizzoaiacademy/rizzo-pii-0.3B
ARG RIZZO_REVISION=a1c3c83827eca22e9675e30c1111c4641caf5901
ARG RIZZO_DIR=/opt/models/rizzo-pii-0.3B-v1.5.0
RUN if [ "$INCLUDE_RIZZO" = true ]; then \
    python -c "import sys; from huggingface_hub import snapshot_download as d; d(sys.argv[1], revision=sys.argv[2], local_dir=sys.argv[3], allow_patterns=['*.json', '*.safetensors', 'README.md'])" "$RIZZO_REPO" "$RIZZO_REVISION" "$RIZZO_DIR" \
    && echo "$RIZZO_REVISION" > "$RIZZO_DIR/REVISION" && rm -rf "$RIZZO_DIR/.cache"; fi

COPY . .

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
