"""Transcription des Reels/vidéos de la semaine (faster-whisper en local, CPU).

Statuts par vidéo : ok | pas_de_voix | echec (avec cause). Jamais de texte reconstitué.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import requests

from common import CONFIG, load, log_event, resolve_week, save

T = CONFIG["transcription"]
MIN_MOTS = 5


def download(url, dest: Path):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        size = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                size += len(chunk)
                if size > T["taille_max_mo"] << 20:
                    raise RuntimeError("vidéo trop lourde")
                f.write(chunk)


def decode(path: Path):
    # ffmpeg direct : contourne l'incompatibilité PyAV de faster-whisper
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-t", str(T["duree_max_s"]),
                          "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True, timeout=300).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def fetch_audio(p):
    """Piste audio du post : la vidéo, sinon l'audio séparé (vidéos servies sans son)."""
    erreurs = []
    for key in ("video_url", "audio_url"):
        if not p.get(key):
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                f = Path(td) / "media"
                download(p[key], f)
                return decode(f), key
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"{key}: {type(e).__name__}")
    raise RuntimeError("aucune piste audio exploitable (" + ", ".join(erreurs or ["aucune URL"]) + ")")


def main():
    start, end, wdir = resolve_week()
    posts = load(wdir / "posts.json", [])
    out = load(wdir / "transcriptions.json", {})
    videos = [p for p in posts if p["type"] in ("Reel", "Vidéo")]
    todo = [p for p in videos if p["shortcode"] not in out or out[p["shortcode"]]["statut"] == "echec"
            or ("--refaire-courts" in sys.argv and len((out[p["shortcode"]].get("texte") or "").split()) < MIN_MOTS)]
    if not todo:
        log_event(wdir, "transcription", "info", f"rien à transcrire ({len(videos)} vidéos)")
        return
    from faster_whisper import WhisperModel
    model = WhisperModel(T["modele"], device="cpu", compute_type="int8")
    for p in todo:
        sc = p["shortcode"]
        if not p.get("video_url") and not p.get("audio_url"):
            out[sc] = {"statut": "echec", "cause": "Ni URL vidéo ni URL audio fournie par le scraper", "texte": None}
            continue
        try:
            audio, source = fetch_audio(p)
            segs, info = model.transcribe(audio, vad_filter=True, beam_size=1)
            texte = " ".join(s.text.strip() for s in segs).strip()
            if len(texte.split()) >= MIN_MOTS:
                out[sc] = {"statut": "ok", "texte": texte, "langue": info.language,
                           "proba_langue": round(info.language_probability, 2), "source_audio": source}
            else:
                # Whisper « hallucine » des mots isolés (« You », « Merci. ») sur de la musique seule
                out[sc] = {"statut": "pas_de_voix", "texte": None,
                           "cause": "Aucune parole exploitable détectée (musique seule ?)" + (f" ; sortie brute rejetée : « {texte} »" if texte else "")}
        except Exception as e:  # noqa: BLE001 : on consigne et on continue en mode dégradé
            out[sc] = {"statut": "echec", "cause": f"{type(e).__name__}: {str(e)[:200]}", "texte": None}
        save(wdir / "transcriptions.json", out)
    n_ok = sum(1 for p in videos if out.get(p["shortcode"], {}).get("statut") == "ok")
    log_event(wdir, "transcription", "info", f"{n_ok}/{len(videos)} vidéos transcrites")
    save(wdir / "transcriptions.json", out)


if __name__ == "__main__":
    main()
