import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse


BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
app = FastAPI(title="The Hive Realtime Chat")


@app.get("/")
async def index():
    return FileResponse(PUBLIC_DIR / "index.html")


@app.get("/static/{asset_path:path}")
async def static_asset(asset_path: str):
    asset = (PUBLIC_DIR / "static" / asset_path).resolve()
    if not asset.is_relative_to(PUBLIC_DIR / "static") or not asset.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(asset)


@app.get("/api/config")
async def public_config():
    project_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
    if not project_url or not publishable_key:
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    return {"supabaseUrl": project_url, "supabaseKey": publishable_key}


@app.get("/api/health")
async def health():
    return {"status": "ok", "supabaseConfigured": bool(os.getenv("SUPABASE_URL") and
            (os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY")))}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
