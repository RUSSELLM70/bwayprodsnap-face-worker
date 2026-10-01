"""
Reindexa las fotos EXISTENTES de BwayProdSnap con el worker 512-d.
(Las fotos nuevas se indexan solas al subirse desde el dashboard.)

Uso:
  SUPABASE_URL=...  SUPABASE_SERVICE_KEY=...  FACE_WORKER_URL=https://tu-worker  \
  [FACE_WORKER_KEY=...] [MEDIA_BASE=https://media.bwayprod.vip] python reindex.py

Recorre gallery_photos activas, calcula embeddings por foto y los inserta en
gallery_photo_faces (borra los previos de cada foto antes, para ser idempotente).
"""
import os
import sys
import time
import requests

SB = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]
WORKER = os.environ["FACE_WORKER_URL"].rstrip("/")
WKEY = os.environ.get("FACE_WORKER_KEY", "")
MEDIA_BASE = os.environ.get("MEDIA_BASE", "https://media.bwayprod.vip").rstrip("/")

H = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"}


def public_url(path):
    if not path:
        return None
    if path.startswith("public/"):
        return MEDIA_BASE + "/" + path
    return SB + "/storage/v1/object/public/bway-shop/" + path


def fetch_photos():
    rows, step, off = [], 1000, 0
    while True:
        r = requests.get(
            SB + "/rest/v1/gallery_photos",
            headers=H,
            params={"select": "id,product_id,preview_path", "is_active": "eq.true",
                    "order": "id.asc", "limit": step, "offset": off},
            timeout=30)
        r.raise_for_status()
        batch = r.json()
        rows += batch
        if len(batch) < step:
            break
        off += step
    return rows


def embed(url):
    r = requests.post(WORKER + "/embed", json={"image_url": url},
                      headers={"x-api-key": WKEY} if WKEY else {}, timeout=60)
    r.raise_for_status()
    return r.json().get("faces", [])


def main():
    photos = fetch_photos()
    print(f"Fotos activas: {len(photos)}")
    ok = faces_total = skipped = errors = 0
    for i, p in enumerate(photos, 1):
        url = public_url(p.get("preview_path"))
        if not url:
            skipped += 1
            continue
        try:
            faces = embed(url)
            # idempotente: borrar embeddings previos de esta foto
            requests.delete(SB + "/rest/v1/gallery_photo_faces",
                            headers=H, params={"photo_id": "eq." + str(p["id"])}, timeout=30)
            if faces:
                payload = [{"photo_id": p["id"], "product_id": p["product_id"],
                            "embedding": "[" + ",".join(str(x) for x in f["embedding"]) + "]"}
                           for f in faces]
                ins = requests.post(SB + "/rest/v1/gallery_photo_faces",
                                    headers=H, json=payload, timeout=30)
                ins.raise_for_status()
                faces_total += len(faces)
            ok += 1
        except Exception as e:  # noqa
            errors += 1
            print(f"  ! foto {p['id']}: {e}", file=sys.stderr)
        if i % 25 == 0:
            print(f"  {i}/{len(photos)} · caras={faces_total} · err={errors}")
        time.sleep(0.02)
    print(f"Listo. procesadas={ok} caras={faces_total} sin_imagen={skipped} errores={errors}")


if __name__ == "__main__":
    main()
