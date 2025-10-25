# main.py
import os
import time  # <-- AJOUTÉ
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import soundfile as sf
import asyncio

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware  # <-- AJOUTÉ

# Kokoro import (attendre que kokoro soit installé)
try:
    from kokoro import KPipeline
except Exception as e:
    # On laisse pipeline = None pour pouvoir donner une erreur claire plus bas
    KPipeline = None

APP_ROOT = Path(__file__).parent
STATIC_DIR = APP_ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)

# ---------- Configuration ----------
MAX_TEXT_LENGTH = 3000
AUDIO_SR = 24000
DEFAULT_VOICE = "af_heart"
DEFAULT_LANG = "f"
PIPELINE_TIMEOUT = 60
FILE_CLEANUP_DELAY = 300  # <-- AJOUTÉ : Délai en secondes avant suppression (ex: 5 minutes)

# ---------- Logging ----------
logger = logging.getLogger("tts_api")
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# file handler with rotation
fh = RotatingFileHandler("tts_api.log", maxBytes=5_000_000, backupCount=3)
fh.setFormatter(fmt)
logger.addHandler(fh)

# console handler
ch = logging.StreamHandler()
ch.setFormatter(fmt)
logger.addHandler(ch)

# ---------- FastAPI app ----------
app = FastAPI(title="Simple TTS API (Kokoro)")

# ---------- AJOUT MIDDLEWARE CORS ----------
# Permet à ton app React (sur un autre port) d'appeler cette API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Autorise toutes les origines (simple pour le dev)
    # Pour plus de sécurité, tu pourrais mettre : ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],  # Autorise GET, POST, etc.
    allow_headers=["*"],
)
# ----------------------------------------

# ---------- Pydantic models ----------
class TTSRequest(BaseModel):
    text: str = Field(..., example="Bonjour tout le monde")
    voice: Optional[str] = Field(None, example="af_heart")
    lang: Optional[str] = Field(DEFAULT_LANG, example="f")
    speed: Optional[float] = Field(1.0, example=1.0) # <-- Corrigé: 'exemple' -> 'example'

class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

# ---------- Helpers ----------
def write_wav_file(filename: Path, audio_numpy, samplerate: int = AUDIO_SR):
    """Écrit un fichier WAV en utilisant soundfile"""
    sf.write(str(filename), audio_numpy, samplerate)

def safe_filename(ts: int):
    return f"kokoro_{ts}.wav"

def cleanup_file(path: Path):
    """Supprime un fichier s'il existe."""
    try:
        if path.exists():
            path.unlink()
            logger.info("Supprime fichier temporaire: %s", path)
    except Exception as e:
        logger.warning("Erreur suppression fichier %s : %s", path, e)

# <-- AJOUTÉ : Nouvelle fonction pour la suppression différée -->
def cleanup_file_delayed(path: Path, delay_seconds: int):
    """Attend N secondes puis supprime le fichier."""
    logger.info("Planification suppression de %s dans %d secondes", path, delay_seconds)
    time.sleep(delay_seconds)
    cleanup_file(path)
# -------------------------------------------------------------

# ---------- Endpoints ----------
@app.post("/tts", response_model=APIResponse)
async def synthesize_tts(payload: TTSRequest):
    # 1) validations simples
    text = (payload.text or "").strip()
    if not text:
        logger.warning("Requete TTS avec texte vide")
        raise HTTPException(status_code=422, detail="Le champ 'text' est requis et ne peut pas être vide.")

    if len(text) > MAX_TEXT_LENGTH:
        logger.info("Texte trop long: %d (> %d)", len(text), MAX_TEXT_LENGTH)
        raise HTTPException(status_code=413, detail=f"Texte trop long (max {MAX_TEXT_LENGTH} caractères).")

    voice = payload.voice or DEFAULT_VOICE
    lang = payload.lang or DEFAULT_LANG

    # 2) vérifier que Kokoro est disponible
    if KPipeline is None:
        logger.error("KPipeline (kokoro) non disponible: import failed")
        raise HTTPException(status_code=503, detail="TTS engine not available (kokoro not installed or failed to import).")

    # 3) préparer fichier de sortie temporaire
    ts = int(time.time() * 1000)
    out_path = STATIC_DIR / safe_filename(ts)

    logger.info("TTS requested (len=%d, voice=%s, lang=%s). Out: %s", len(text), voice, lang, out_path)

    # 4) exécuter la génération dans un thread (blocking operation)
    async def run_pipeline_and_write():
        try:
            pipeline = KPipeline(lang_code=lang)
        except Exception as e:
            logger.exception("Erreur initialisation KPipeline: %s", e)
            raise RuntimeError("Erreur d'initialisation du moteur TTS.") from e

        try:
            # pipeline retourne un générateur: for i, (gs, ps, audio) in enumerate(gen):
            # on l'exécute en local (bloquant) et on sauvegarde le dernier audio rendu
            gen = pipeline(text, voice=voice, speed=payload.speed)
            last_audio = None
            for i, item in enumerate(gen):
                # item attendu: (gs, ps, audio)
                if not item or len(item) < 3:
                    continue
                gs, ps, audio = item
                last_audio = audio  # numpy array
                # si on veut, on peut streamer ici (non implémenté)
            if last_audio is None:
                logger.error("Pipeline n'a retourné aucun audio.")
                raise RuntimeError("Aucune sortie audio produite par le modèle.")
            # écrire le wav final
            write_wav_file(out_path, last_audio, AUDIO_SR)
            logger.info("Fichier audio généré: %s", out_path)
            return str(out_path.name)
        except Exception as e:
            logger.exception("Erreur pendant génération TTS: %s", e)
            # Si fichier résiduel existant, supprimer
            if out_path.exists():
                try:
                    out_path.unlink()
                except Exception:
                    pass
            raise

    try:
        # (Logique de thread/async conservée telle quelle)
        filename = await asyncio.wait_for(asyncio.to_thread(lambda: asyncio.run(run_pipeline_and_write()) if False else asyncio.get_event_loop()), timeout=PIPELINE_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error("Timeout lors de l'appel au pipeline TTS (>%d s)", PIPELINE_TIMEOUT)
        raise HTTPException(status_code=504, detail="Génération TTS trop longue (timeout).")
    except Exception as e:
        logger.debug("Retrying pipeline run in to_thread with proper sync wrapper due to earlier failure.")
        try:
            def sync_wrapper():
                # run the async inner function in a new loop for this thread
                return asyncio.new_event_loop().run_until_complete(run_pipeline_and_write())
            filename = await asyncio.to_thread(sync_wrapper)
        except asyncio.TimeoutError:
            logger.error("Timeout lors de l'appel au pipeline TTS (retry).")
            raise HTTPException(status_code=504, detail="Génération TTS trop longue (timeout).")
        except Exception as e_inner:
            logger.exception("Échec génération TTS après tentative: %s", e_inner)
            raise HTTPException(status_code=500, detail="Erreur interne lors de la génération TTS.")

    # 5) construire URL de téléchargement (relatif)
    download_url = f"/download/{filename}"
    response = {
        "success": True,
        "message": "Audio généré avec succès.",
        "data": {
            "filename": filename,
            "download_url": download_url
        }
    }
    return response

# <-- MODIFIÉ : Endpoint /download corrigé -->
@app.get("/download/{filename}", response_class=FileResponse)
def download_file(filename: str, background_tasks: BackgroundTasks):
    # sanitation simple: s'assurer que le nom est dans le dossier static
    safe_path = STATIC_DIR / filename
    if not safe_path.exists():
        logger.warning("Téléchargement demandé pour fichier inexistant: %s", filename)
        raise HTTPException(status_code=404, detail="Fichier non trouvé.")
    
    # On planifie la suppression du fichier APRES un délai,
    # pour laisser le temps au client de le télécharger.
    background_tasks.add_task(cleanup_file_delayed, safe_path, delay_seconds=FILE_CLEANUP_DELAY)
    
    logger.info("Serving file %s", safe_path)
    return FileResponse(path=str(safe_path), filename=filename, media_type="audio/wav")