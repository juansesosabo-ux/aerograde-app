import os
import shutil
import tempfile
import uuid

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from enhance_photo import enhance_image
from enhance_video import enhance_video

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}

app = FastAPI(title="AeroGrade API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKDIR = os.path.join(tempfile.gettempdir(), "aerograde")
os.makedirs(WORKDIR, exist_ok=True)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/enhance")
async def enhance(
    file: UploadFile = File(...),
    intensity: float = Form(100),
    warmth: float = Form(0),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    job_id = uuid.uuid4().hex
    in_path = os.path.join(WORKDIR, f"{job_id}_in{ext}")
    out_path = os.path.join(WORKDIR, f"{job_id}_out{ext}")

    with open(in_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        if ext in PHOTO_EXTENSIONS:
            enhance_image(in_path, out_path, intensity=intensity, warmth=warmth)
            media_type = "image/jpeg"
        elif ext in VIDEO_EXTENSIONS:
            enhance_video(in_path, out_path, intensity=intensity, warmth=warmth)
            media_type = "video/mp4"
        else:
            raise HTTPException(status_code=400, detail=f"Formato no soportado: {ext}")
    finally:
        if os.path.exists(in_path):
            os.remove(in_path)

    if not os.path.exists(out_path):
        raise HTTPException(status_code=500, detail="El procesamiento no generó un archivo de salida")

    return FileResponse(
        out_path,
        media_type=media_type,
        filename=f"editado_{file.filename}",
        background=None,
    )


frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

