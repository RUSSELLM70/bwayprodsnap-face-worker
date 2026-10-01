FROM python:3.11-slim

# libs de sistema para opencv / tensorflow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgl1 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    DEEPFACE_HOME=/app/.deepface \
    TF_CPP_MIN_LOG_LEVEL=3

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Pre-descargar los pesos de Facenet512 + RetinaFace para que el 1er request
# no tarde (se hornean en la imagen). Usa una imagen de prueba 1x1 que NO
# requiere detección (enforce_detection=False).
RUN python -c "import numpy as np; from deepface import DeepFace; \
DeepFace.represent(img_path=np.zeros((160,160,3),dtype='uint8'), model_name='Facenet512', \
detector_backend='skip', enforce_detection=False)" || true

EXPOSE 8080
# $PORT lo inyectan Render/HF Spaces/Fly; default 8080 para Docker local.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS http://localhost:${PORT:-8080}/health || exit 1

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
