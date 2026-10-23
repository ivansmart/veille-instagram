"""Envoi déterministe de data/<semaine>/email.json via l'API Resend (pièce jointe encodée par le code).

Le connecteur Gmail exige que l'IA recopie la pièce jointe en base64 : impraticable au-delà de quelques Ko
(testé : un PDF de 34 Ko = 46 000 caractères). D'où cet envoi par API, avec vérification de la réponse.
Variable requise : RESEND_API_KEY. Expéditeur par défaut : onboarding@resend.dev (autorisé vers l'adresse
du titulaire du compte Resend, sans domaine à configurer).
"""
import base64
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from common import TZ, load, log_event, resolve_week


def send(mail, wdir):
    key = os.environ.get("RESEND_API_KEY", "").strip()
    if not key:
        raise SystemExit("RESEND_API_KEY absent : envoi impossible")
    payload = {"from": os.environ.get("VEILLE_FROM", "Veille Instagram <onboarding@resend.dev>"),
               "to": [mail["to"]], "subject": mail["subject"], "html": mail["htmlBody"], "text": mail["body"]}
    if mail.get("piece_jointe"):
        pdf = Path(mail["piece_jointe"])
        payload["attachments"] = [{"filename": pdf.name, "content": base64.b64encode(pdf.read_bytes()).decode()}]
    for essai in (1, 2):
        r = requests.post("https://api.resend.com/emails", json=payload, timeout=60,
                          headers={"Authorization": f"Bearer {key}"})
        if r.ok:
            log_event(wdir, "envoi", "info", f"e-mail envoyé (id {r.json().get('id')})", type=mail["type"])
            return r.json()
        log_event(wdir, "envoi", "erreur", f"tentative {essai} : HTTP {r.status_code} {r.text[:200]}")
    raise SystemExit(f"Envoi échoué : HTTP {r.status_code}")


def attendre(heure):
    """Bloque jusqu'à HH:MM (heure de Paris) si l'on est en avance : l'e-mail part à l'heure promise."""
    h, m = map(int, heure.split(":"))
    cible = datetime.now(TZ).replace(hour=h, minute=m, second=0, microsecond=0)
    reste = (cible - datetime.now(TZ)).total_seconds()
    if 0 < reste < 3 * 3600:
        print(f"attente de {int(reste)} s jusqu'à {heure}", file=sys.stderr)
        time.sleep(reste)


if __name__ == "__main__":
    start, end, wdir = resolve_week()
    if "--attendre-jusqua" in sys.argv:
        attendre(sys.argv[sys.argv.index("--attendre-jusqua") + 1])
    print(send(load(wdir / "email.json"), wdir))
