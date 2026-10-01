# BwayProdSnap — Face Worker (512-d, open-source)

Reconocimiento facial **preciso y gratis** para la búsqueda por selfie.
Motor: **DeepFace · Facenet512** (embedding 512-d, licencia MIT → uso comercial OK)
+ **RetinaFace** (detección multi-cara, buena en multitudes/ángulos). Corre en CPU.

> Reemplaza al face-api.js (128-d, en el navegador) que no detectaba/filtraba.

## Qué hace
- `GET /health` → estado + modelo.
- `POST /embed` → embeddings 512-d **normalizados** de todas las caras de la imagen.
  - multipart `file` (selfie/foto) **o** JSON `{"image_url": "..."}`.
  - respuesta: `{"faces":[{"embedding":[512], "box":{x,y,w,h}, "score":n}], "count":N}`.

Los embeddings se L2-normalizan → en la BD se compara por **coseno** (`<=>`).

## Deploy SIN terminal (recomendado) — por interfaz web
No necesitás SSH ni Docker local. El worker se despliega conectando el repo de
GitHub a una plataforma gestionada que lee el `Dockerfile` y te da una **URL
HTTPS pública** lista para `FACE_WORKER_URL`.

**Opción A — Render (blueprint incluido `render.yaml`):**
1. https://dashboard.render.com → **New → Blueprint** → conectar `RUSSELLM70/bwayprodx`.
2. Render detecta `render.yaml` y crea el servicio `bwayprodsnap-face-worker`.
3. En *Environment*, poné `FACE_WORKER_KEY` = una clave larga aleatoria.
4. **Deploy** → te queda una URL tipo `https://bwayprodsnap-face-worker.onrender.com`.
   (Plan `starter` ~US$7/mes = always-on. `free` funciona pero duerme por inactividad.)
5. Probar: abrir `https://…onrender.com/health` → `{"ok":true,...}`.

**Opción B — Hugging Face Spaces (Docker, free):**
1. huggingface.co → **New Space** → SDK **Docker** → subir el contenido de
   `face-worker/` (o apuntar al repo). Agregar al README del Space el front-matter
   `sdk: docker` y `app_port: 8080`. En *Settings → Secrets* poné `FACE_WORKER_KEY`.
2. Queda en `https://<usuario>-<space>.hf.space`. (El free duerme por inactividad.)

> Para producción always-on sin cold-start: Render `starter`, Fly.io, o un VPS
> propio con el método Docker de abajo.

## Correrlo con Docker propio (ej. en tu Hetzner, el mismo de n8n)
```bash
cd face-worker
# opcional pero recomendado: una clave compartida
export FACE_WORKER_KEY="una-clave-larga-secreta"
docker compose up -d --build
curl -s localhost:8080/health      # {"ok":true,"model":"Facenet512",...}
```
Poné un dominio/HTTPS delante (Caddy/Nginx o Cloudflare Tunnel), ej.
`https://face.bwayprod.vip`. Primer arranque descarga pesos (~100 MB, ya se
hornean en la imagen). RAM ~1.5–2 GB.

## Conectarlo a la app (2 valores en `config.js`)
```js
window.__BWAY_CONFIG__ = {
  ...
  FACE_WORKER_URL: "https://face.bwayprod.vip",  // ← al setearlo, la búsqueda por selfie se ENCIENDE sola
  FACE_WORKER_KEY: "una-clave-larga-secreta",    // opcional, debe coincidir con el worker
};
```
> Mientras `FACE_WORKER_URL` esté vacío, la UI de selfie queda **oculta**
> automáticamente (solo dorsal). Al setearla, aparece sin más cambios.

## Aplicar la migración de BD (una vez)
`supabase/migrations/20260930_snap_face_512.sql` — pasa `gallery_photo_faces`
a `vector(512)` + índice coseno y actualiza las RPC. Borra los embeddings
128-d viejos (inservibles).

## Reindexar las fotos existentes (una vez)
Las fotos **nuevas** se indexan solas al subirse. Para las que ya estaban:
```bash
SUPABASE_URL="https://wdxwrhbguppfghswxmzy.supabase.co" \
SUPABASE_SERVICE_KEY="<service_role>" \
FACE_WORKER_URL="https://face.bwayprod.vip" \
FACE_WORKER_KEY="una-clave-larga-secreta" \
python reindex.py
```

## Calibrar precisión
- Umbral de coseno en las RPC: **0.40** por defecto (más bajo = más estricto).
  Subí a 0.45 si quedan fotos fuera; bajá a 0.35 si trae caras ajenas.
- Para indexar conviene la **foto original** (no la de marca de agua). El
  dashboard ya usa el archivo original al subir; el reindex usa la preview
  (suficiente, pero el original es más preciso si querés ajustarlo).
