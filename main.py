"""
BwayProdSnap — Face worker (open-source, 512-d).

Motor: DeepFace · Facenet512 (embedding 512-d, MIT, uso comercial OK)
       · RetinaFace (detección multi-cara, buena en multitudes/ángulos).

Expone:
  GET  /health            → {ok, model}
  POST /embed             → calcula embeddings 512-d normalizados de TODAS las caras
       entrada: multipart "file"  (selfie/foto)  — o  JSON {"image_url": "..."}
       salida : {"faces": [{"embedding": [512 floats], "box": {...}, "score": float}], "count": N}

Los embeddings se L2-normalizan → usar distancia COSENO (<=>) en pgvector.
Seguridad opcional: si FACE_WORKER_KEY está seteada, exige header  x-api-key.
"""
import os
import io
import numpy as np
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import cv2
import requests
from deepface import DeepFace

MODEL = "Facenet512"          # 512-d, MIT (comercial OK)
DETECTOR = "retinaface"        # robusto para fotos de evento (multi-cara/ángulos)
API_KEY = os.environ.get("FACE_WORKER_KEY", "").strip()
# CORS: orígenes permitidos (coma-separados). Default: dominios de BwayProd.
ORIGINS = [o.strip() for o in os.environ.get(
    "FACE_WORKER_ORIGINS",
    "https://bwayprod.vip,https://www.bwayprod.vip,https://bwayprodx.pages.dev,http://localhost:8000"
).split(",") if o.strip()]

app = FastAPI(title="BwayProdSnap Face Worker", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"],
    allow_headers=["*"], allow_credentials=False,
)


def _check_key(x_api_key):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="bad api key")


def _decode(data: bytes):
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)   # BGR (lo que espera DeepFace)
    if img is None:
        raise HTTPException(status_code=400, detail="imagen ilegible")
    # Redimensionar si es enorme (acelera sin perder caras razonables).
    h, w = img.shape[:2]
    m = max(h, w)
    if m > 1600:
        s = 1600.0 / m
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return img


def _embeddings(img):
    reps = DeepFace.represent(
        img_path=img, model_name=MODEL, detector_backend=DETECTOR,
        enforce_detection=False, align=True,
    )
    out = []
    for r in reps or []:
        emb = np.asarray(r.get("embedding", []), dtype=np.float32)
        if emb.size != 512:
            continue
        n = np.linalg.norm(emb)
        if n > 0:
            emb = emb / n                       # L2-normalizar → coseno
        fa = r.get("facial_area", {}) or {}
        score = float(r.get("face_confidence", 0) or 0)
        # DeepFace con enforce_detection=False puede devolver la imagen entera
        # como "cara" (score 0) → descartarla.
        if score <= 0 and (fa.get("w", 0) == 0 or fa.get("h", 0) == 0):
            continue
        out.append({
            "embedding": emb.tolist(),
            "box": {k: int(fa.get(k, 0)) for k in ("x", "y", "w", "h")},
            "score": score,
        })
    return out


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL, "detector": DETECTOR, "dim": 512}


@app.post("/embed")
async def embed(request: Request,
                file: UploadFile = File(default=None),
                x_api_key: str = Header(default="")):
    _check_key(x_api_key)
    data = None
    if file is not None:
        data = await file.read()
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
        url = (body or {}).get("image_url")
        if url:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.content
    if not data:
        raise HTTPException(status_code=400, detail="enviá 'file' (multipart) o {image_url}")
    img = _decode(data)
    faces = _embeddings(img)
    return {"faces": faces, "count": len(faces)}
