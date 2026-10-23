"""Prépare l'e-mail (veille ou alerte) dans data/<semaine>/email.json.

L'envoi est fait par send_email.py (API Resend). Ce script ne fait que composer : sujet, corps texte,
corps HTML (mise en page compatible messageries : tableaux et styles en ligne) et pièce jointe.
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


INK, ACCENT, MUTED, LINE, CARD, WARN = "#14213D", "#D62F6B", "#6B7280", "#E5E7EB", "#F6F7F9", "#C2410C"
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]
FONT = "font-family:Helvetica,Arial,sans-serif;"


def e(s):
    return escape("" if s is None else str(s))


def n(v):
    return f"{v:,}".replace(",", " ")


def coque(entete_couleur, surtitre, titre, sous_titre, contenu):
    """Squelette commun : bandeau, contenu, pied. Tableaux + styles en ligne pour Gmail/Outlook/Apple Mail."""
    return f"""<!doctype html><html><body style="margin:0;padding:0;background:#EEF0F3;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF0F3;"><tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#FFFFFF;border-radius:10px;overflow:hidden;">
<tr><td style="background:{INK};border-top:5px solid {entete_couleur};padding:26px 28px;{FONT}">
<div style="font-size:11px;font-weight:bold;letter-spacing:1px;color:#F9A8C9;">{e(surtitre)}</div>
<div style="font-size:24px;line-height:30px;font-weight:bold;color:#FFFFFF;margin-top:6px;">{e(titre)}</div>
<div style="font-size:13px;color:#CBD5E1;margin-top:6px;">{e(sous_titre)}</div>
</td></tr>
{contenu}
<tr><td style="padding:18px 28px 24px;border-top:1px solid {LINE};{FONT}font-size:11px;line-height:16px;color:{MUTED};">
Veille automatisée pour Ivan Ouedraogo. Chaque information provient des publications collectées ;
aucune donnée n'est inventée. Les données absentes sont signalées comme telles.
</td></tr></table></td></tr></table></body></html>"""


def bloc(titre, interieur, haut=22):
    return (f'<tr><td style="padding:{haut}px 28px 0;{FONT}">'
            f'<div style="font-size:12px;font-weight:bold;letter-spacing:1px;color:{ACCENT};margin-bottom:10px;">{e(titre)}</div>'
            f'{interieur}</td></tr>')


def html_veille(st, a, posts, start, end):
    T = st["totaux"]
    known = {p["shortcode"]: p for p in posts}
    actifs = sum(1 for q in st["par_compte"].values() if q["posts"] > 0)
    tuiles = [(T["posts"], "publications"), (f"{actifs}/{len(st['par_compte'])}", "comptes actifs"),
              (f"{T['transcrites']}/{T['videos_transcriptibles']}", "Reels transcrits"),
              (st["fiabilite"].capitalize(), "fiabilité")]
    kpi = "".join(f'<td width="25%" align="center" style="background:{CARD};padding:14px 4px;border:4px solid #FFFFFF;">'
                  f'<div style="font-size:22px;font-weight:bold;color:{INK};">{e(v)}</div>'
                  f'<div style="font-size:11px;color:{MUTED};margin-top:2px;">{e(l)}</div></td>' for v, l in tuiles)
    c = f'<tr><td style="padding:18px 24px 0;{FONT}"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{kpi}</tr></table></td></tr>'
    if st["statut"] == "partielle":
        lim = "".join(f"<li>{e(r)}</li>" for r in st["raisons"])
        c += (f'<tr><td style="padding:16px 28px 0;{FONT}"><div style="background:#FFF4EC;border-left:4px solid {WARN};'
              f'padding:12px 14px;font-size:13px;line-height:19px;color:{INK};"><b>Collecte partielle : données manquantes</b>'
              f'<ul style="margin:6px 0 0 18px;padding:0;">{lim}</ul></div></td></tr>')
    c += bloc("EN BREF", f'<div style="font-size:15px;line-height:23px;color:{INK};">{e(a.get("resume_executif"))}</div>')
    lignes = ""
    for i, x in enumerate(a.get("tendances") or [], 1):
        comptes = " ".join("@" + k.lstrip("@") for k in x.get("comptes") or [])
        lignes += (f'<tr><td valign="top" width="28" style="font-size:18px;font-weight:bold;color:{ACCENT};padding:8px 0;">{i}</td>'
                   f'<td style="padding:8px 0;border-bottom:1px solid {LINE};"><div style="font-size:15px;font-weight:bold;color:{INK};">{e(x.get("titre"))}</div>'
                   f'<div style="font-size:12px;color:{ACCENT};margin-top:2px;">{e(comptes)}</div>'
                   f'<div style="font-size:13px;line-height:19px;color:{MUTED};margin-top:3px;">{e(x.get("pourquoi"))}</div></td></tr>')
    c += bloc("TENDANCES DE LA SEMAINE", f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="{FONT}">{lignes}</table>')
    cartes = ""
    for i, x in enumerate(a.get("top5") or [], 1):
        p = known.get(x.get("shortcode"))
        if not p:
            continue
        chiffres = " · ".join(f"{n(p[k])} {lab}" for k, lab in (("lectures", "lectures"), ("likes", "likes"), ("commentaires", "commentaires"))
                              if p.get(k) is not None)
        cartes += (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CARD};border-left:4px solid {ACCENT};margin-bottom:10px;">'
                   f'<tr><td style="padding:12px 14px;{FONT}"><div style="font-size:12px;color:{MUTED};"><b style="color:{ACCENT};">#{i}</b> &nbsp;@{e(p["compte"])} · {e(p["type"])}</div>'
                   f'<div style="font-size:14px;line-height:20px;color:{INK};margin:4px 0 8px;">{e(x.get("raison"))}</div>'
                   f'<div style="font-size:11px;color:{MUTED};margin-bottom:8px;">{e(chiffres)}</div>'
                   f'<a href="{e(p["url"])}" style="display:inline-block;background:{INK};color:#FFFFFF;text-decoration:none;font-size:12px;font-weight:bold;padding:7px 14px;border-radius:5px;">Voir la publication</a>'
                   f'</td></tr></table>')
    c += bloc("TOP 5 À CONSULTER", cartes)
    c += bloc("RECOMMANDATION PRIORITAIRE",
              f'<div style="background:#FDF2F7;border-left:4px solid {ACCENT};padding:14px 16px;font-size:15px;line-height:22px;font-weight:bold;color:{INK};">{e(a.get("recommandation"))}</div>')
    c += (f'<tr><td style="padding:20px 28px 22px;{FONT}font-size:13px;line-height:19px;color:{INK};">'
          f'📎 <b>Le rapport complet est en pièce jointe (PDF)</b> : 10 sections, dont les insights actionnables, '
          f'les outils cités, les points de vigilance et la qualité des données.</td></tr>')
    titre = f"Semaine du {start.day} {MOIS[start.month - 1]} au {end.day} {MOIS[end.month - 1]} {end.year}"
    sous = f"Collecte {'complète' if st['statut'] == 'complete' else 'partielle'} · {T['posts']} publications analysées"
    return coque(ACCENT, "VEILLE INSTAGRAM HEBDOMADAIRE", titre, sous, c)


def html_alerte(lines_infos, causes, comptes, tentatives, reco, start, end, now):
    li = "".join(f'<li style="margin-bottom:4px;">{e(x)}</li>' for x in tentatives) or "<li>(journal vide)</li>"
    c = (f'<tr><td style="padding:22px 28px 0;{FONT}font-size:15px;line-height:22px;color:{INK};">'
         f'La veille de cette semaine <b>n\'a pas été générée</b> : la collecte a échoué. '
         f'Aucun PDF n\'est envoyé, pour ne pas te transmettre une analyse fausse.</td></tr>')
    c += bloc("DIAGNOSTIC", (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="{FONT}font-size:13px;line-height:19px;color:{INK};">'
                             f'<tr><td width="150" style="color:{MUTED};padding:4px 0;">Date de l\'échec</td><td style="padding:4px 0;">{e(now)} (heure de Paris)</td></tr>'
                             f'<tr><td style="color:{MUTED};padding:4px 0;">Comptes concernés</td><td style="padding:4px 0;">{e(comptes)}</td></tr>'
                             f'<tr><td style="color:{MUTED};padding:4px 0;" valign="top">Cause probable</td><td style="padding:4px 0;"><b>{e(causes)}</b></td></tr></table>'))
    c += bloc("CE QUI A ÉTÉ TENTÉ", f'<ul style="margin:0 0 0 18px;padding:0;font-size:12px;line-height:18px;color:{MUTED};">{li}</ul>')
    c += bloc("COMMENT CORRIGER",
              f'<div style="background:#FFF4EC;border-left:4px solid {WARN};padding:14px 16px;font-size:14px;line-height:21px;font-weight:bold;color:{INK};">{e(reco)}</div>')
    c += '<tr><td style="padding:0 0 22px;"></td></tr>'
    return coque(WARN, "⚠ ALERTE · VEILLE INSTAGRAM", "Collecte échouée", f"Semaine du {start:%d/%m} au {end:%d/%m/%Y}", c)


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
        html = html_alerte(lines, " | ".join(causes) or "inconnue", ", ".join("@" + c for c in bad) or "tous",
                           tent, reco, start, end, now)
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
        html = html_veille(st, a, load(wdir / "posts.json", []), start, end)
    mail = {"to": CONFIG["destinataire"], "subject": subject, "body": "\n".join(lines), "htmlBody": html,
            "piece_jointe": att, "type": "alerte" if st["statut"] == "echouee" else "veille"}
    save(wdir / "email.json", mail)
    return mail


if __name__ == "__main__":
    start, end, wdir = resolve_week()
    m = compose(wdir, start, end, test="--test" in sys.argv)
    print(m["subject"]); print(m["body"]); print("PJ:", m["piece_jointe"])
