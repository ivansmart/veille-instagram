"""Prépare l'e-mail (veille ou alerte) dans data/<semaine>/email.json.

L'envoi est fait par la session Claude via le connecteur Gmail (le SMTP sortant est bloqué
dans le conteneur). Ce script ne fait que composer : sujet, corps texte, corps HTML, pièce jointe.
"""
import json
import sys
from datetime import datetime
from xml.sax.saxutils import escape

from common import CONFIG, TZ, load, resolve_week, save

CORRECTIFS = {
    "APIFY_TOKEN": "Ajouter le jeton Apify dans les paramètres de l'environnement cloud (variable APIFY_TOKEN), puis relancer.",
    "401": "Jeton Apify refusé : en générer un nouveau sur console.apify.com > Settings > Integrations et mettre à jour APIFY_TOKEN.",
    "402": "Crédit Apify épuisé : recharger le compte ou passer au forfait supérieur.",
    "délai": "Le scraper a dépassé le délai : relancer manuellement ; si ça se répète, réduire max_posts_par_compte.",
    "Profil non renvoyé": "Vérifier à la main que le compte existe toujours (renommage ?) et mettre à jour config.yaml.",
    "privé": "Compte passé en privé : le retirer de config.yaml ou s'y abonner (non scrappable).",
}


def correctif(texte):
    for k, v in CORRECTIFS.items():
        if k in (texte or ""):
            return v
    return "Consulter journal.jsonl de la semaine ; relancer run_weekly.sh. Si l'actor Apify est cassé, vérifier son statut sur apify.com/apify/instagram-scraper (onglet Issues)."


def compose(wdir, start, end, test=False):
    st = load(wdir / "status.json")
    coll = load(wdir / "collecte.json", {})
    journal = [json.loads(l) for l in (wdir / "journal.jsonl").read_text(encoding="utf-8").splitlines()] \
        if (wdir / "journal.jsonl").exists() else []
    pfx = "[TEST] " if test else ""
    periode = f"du {start:%d/%m/%Y} au {end:%d/%m/%Y}"
    now = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")

    if st["statut"] == "echouee":
        bad = {c: q for c, q in st["par_compte"].items() if q["statut"] in ("erreur", "privé")}
        causes = [coll.get("fatal")] if coll.get("fatal") else []
        causes += sorted({q["cause"] for q in bad.values() if q["cause"]})
        tent = [f"{e['ts']} [{e['etape']}] {e['niveau']} : {e['message']}" for e in journal]
        reco = correctif(" ".join(causes))
        lines = [f"La veille Instagram de la semaine {periode} n'a PAS été générée : la collecte a échoué.",
                 "Aucun PDF n'est envoyé pour ne pas te transmettre une analyse fausse.", "",
                 f"Date de l'échec : {now} (Europe/Paris)",
                 "Comptes concernés : " + (", ".join("@" + c for c in bad) or "tous"),
                 "Cause probable : " + (" | ".join(causes) or "inconnue"), "",
                 "Ce qui a été tenté :"] + [f"  - {x}" for x in tent or ["(journal vide)"]] + ["",
                 f"Recommandation : {reco}"]
        subject = f"{pfx}⚠ ALERTE veille Instagram : collecte échouée ({start:%d/%m}-{end:%d/%m})"
        att = None
    else:
        T = st["totaux"]
        lines = [f"Veille Instagram de la semaine {periode} en pièce jointe.",
                 f"Collecte : {st['statut']} | fiabilité {st['fiabilite']} | {T['posts']} publications | "
                 f"{T['transcrites']}/{T['videos_transcriptibles']} vidéos avec voix transcrites.",
                 ]
        if st["raisons"]:
            lines += ["", "Limites de la semaine :"] + [f"  - {r}" for r in st["raisons"]]
        a = load(wdir / "analysis.json") or {}
        if a.get("resume_executif"):
            lines += ["", "Résumé : " + a["resume_executif"]]
        tag = "" if st["statut"] == "complete" else " (partielle)"
        subject = f"{pfx}Veille Instagram{tag} : semaine du {start:%d/%m} au {end:%d/%m/%Y}"
        att = str(wdir / f"veille-instagram-{start:%Y-%m-%d}.pdf")
    html = "<div style='font-family:Arial,sans-serif;font-size:14px'>" + "".join(
        f"<p style='margin:2px 0'>{escape(l) if l else '&nbsp;'}</p>" for l in lines) + "</div>"
    mail = {"to": CONFIG["destinataire"], "subject": subject, "body": "\n".join(lines), "htmlBody": html,
            "piece_jointe": att, "type": "alerte" if st["statut"] == "echouee" else "veille"}
    save(wdir / "email.json", mail)
    return mail


if __name__ == "__main__":
    start, end, wdir = resolve_week()
    m = compose(wdir, start, end, test="--test" in sys.argv)
    print(m["subject"]); print(m["body"]); print("PJ:", m["piece_jointe"])
