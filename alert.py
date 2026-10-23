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


INK, BODY, MUTED, VIOLET, PASTILLE, BORD, FOND, CORAIL = ("#2B2F4E", "#555A75", "#8A8FA8", "#6E56F8",
                                                         "#E3E0FB", "#E7E5F6", "#F4F3FC", "#E8604C")
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]
FONT = "font-family:'Plus Jakarta Sans',Helvetica,Arial,sans-serif;"


def e(s):
    return escape("" if s is None else str(s))


def n(v):
    return f"{v:,}".replace(",", " ")


def vi(s):
    return f'<b style="color:{VIOLET};">{s}</b>'


def coque(etiquette, titre, intro, contenu, couleur=VIOLET):
    """Squelette au style du mémo : fond lavande, étiquette en pastille, grand titre centré, contenu en cartes."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap" rel="stylesheet"></head>
<body style="margin:0;padding:0;background:{FOND};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{FOND};"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
<tr><td align="center" style="{FONT}padding:4px 16px 0;">
<span style="display:inline-block;background:{PASTILLE};color:{couleur};font-size:11px;font-weight:700;letter-spacing:.5px;padding:6px 14px;border-radius:20px;">{e(etiquette)}</span>
<div style="font-size:30px;line-height:38px;font-weight:800;color:{INK};margin-top:16px;letter-spacing:-0.3px;">{e(titre)}</div>
<div style="font-size:15px;line-height:24px;color:{BODY};margin:12px auto 0;max-width:460px;">{intro}</div>
</td></tr>
{contenu}
<tr><td align="center" style="{FONT}padding:26px 24px 8px;font-size:11px;line-height:17px;color:{MUTED};">
Veille automatisée pour Ivan Ouedraogo. Chaque information provient des publications collectées :
aucune donnée n'est inventée, les données absentes sont signalées comme telles.
</td></tr></table></td></tr></table></body></html>"""


def section(num, titre, intro=""):
    """Pastille > titre > chapeau : 48 px au-dessus, 24 px avant le contenu."""
    return (f'<tr><td align="center" style="{FONT}padding:48px 16px 24px;">'
            f'<div style="display:inline-block;width:32px;height:32px;line-height:32px;border-radius:16px;background:{PASTILLE};'
            f'color:{INK};font-size:13px;font-weight:700;text-align:center;">{num}</div>'
            f'<div style="font-size:22px;line-height:28px;font-weight:800;color:{INK};margin-top:12px;">{e(titre)}</div>'
            + (f'<div style="font-size:14px;line-height:22px;color:{BODY};margin:8px auto 0;max-width:420px;">{intro}</div>' if intro else "")
            + '</td></tr>')


def carte(interieur, fond="#FFFFFF", bord=BORD, pad="24px"):
    return (f'<tr><td style="padding:0 0 12px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:{fond};border:1px solid {bord};border-radius:16px;"><tr><td style="{FONT}padding:{pad};">'
            f'{interieur}</td></tr></table></td></tr>')


def numero(i, fond=INK):
    return (f'<td valign="top" width="40" style="padding-top:1px;"><div style="width:24px;height:24px;line-height:24px;border-radius:12px;'
            f'background:{fond};color:#FFFFFF;font-size:12px;font-weight:700;text-align:center;{FONT}">{i}</div></td>')


def etiquette(txt):
    return f'<div style="font-size:11px;line-height:16px;font-weight:700;letter-spacing:.6px;color:{MUTED};">{e(txt)}</div>'


def separateur():
    return f'<div style="height:1px;background:#EEEDF6;margin:16px 0;line-height:1px;font-size:1px;">&nbsp;</div>'


def html_veille(st, a, posts, start, end):
    T = st["totaux"]
    known = {p["shortcode"]: p for p in posts}
    actifs = sum(1 for q in st["par_compte"].values() if q["posts"] > 0)
    nb_comptes = len(st["par_compte"])
    tuiles = [(T["posts"], "publications", INK), (f"{actifs}/{nb_comptes}", "comptes actifs", INK),
              (f"{T['transcrites']}/{T['videos_transcriptibles']}", "Reels transcrits", INK),
              (st["fiabilite"].capitalize(), "fiabilité", "#1F9D63" if st["fiabilite"] == "élevée" else CORAIL)]
    kpi = "".join(f'<td width="25%" style="padding:0 4px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                  f'style="background:#FFFFFF;border:1px solid {BORD};border-radius:16px;"><tr><td align="center" style="{FONT}padding:16px 4px;">'
                  f'<div style="font-size:24px;line-height:30px;font-weight:800;color:{c};">{e(v)}</div>'
                  f'<div style="font-size:11px;line-height:16px;color:{MUTED};margin-top:4px;">{e(l)}</div></td></tr></table></td>' for v, l, c in tuiles)
    c = f'<tr><td style="padding:32px 0 0;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{kpi}</tr></table></td></tr>'
    if st["statut"] == "partielle":
        lim = "".join(f'<li style="margin-bottom:4px;">{e(r)}</li>' for r in st["raisons"])
        c += '<tr><td style="padding:16px 0 0;"></td></tr>' + carte(
            f'<div style="font-size:11px;font-weight:700;letter-spacing:.6px;color:{CORAIL};">DONNÉES MANQUANTES CETTE SEMAINE</div>'
            f'<ul style="margin:8px 0 0 18px;padding:0;font-size:14px;line-height:22px;color:{INK};">{lim}</ul>', fond="#FFF5F3", bord=CORAIL)
    c += section(1, "En bref", "L'essentiel de la semaine en " + vi("trois phrases") + ".")
    c += carte(f'<div style="font-size:16px;line-height:26px;color:{INK};">{e(a.get("resume_executif"))}</div>', pad="28px")
    nb = len(a.get("tendances") or [])
    c += section(2, "Grandes tendances", f"Les {vi(f'{nb} sujets')} qui ont structuré la semaine.")
    for i, x in enumerate(a.get("tendances") or [], 1):
        comptes = " &nbsp;·&nbsp; ".join(e("@" + k.lstrip("@")) for k in x.get("comptes") or [])
        c += carte(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{numero(i)}<td style="{FONT}">'
                   f'<div style="font-size:17px;line-height:24px;font-weight:800;color:{INK};">{e(x.get("titre"))}</div>'
                   f'<div style="font-size:12px;line-height:18px;font-weight:700;color:{VIOLET};margin-top:4px;">{comptes}</div>'
                   f'{separateur()}{etiquette("POURQUOI C’EST IMPORTANT")}'
                   f'<div style="font-size:14px;line-height:22px;color:{BODY};margin-top:4px;">{e(x.get("pourquoi"))}</div>'
                   f'</td></tr></table>')
    c += section(3, "Top 5 à consulter", "Les publications les plus " + vi("utiles pour ta veille") + ".")
    for i, x in enumerate(a.get("top5") or [], 1):
        p = known.get(x.get("shortcode"))
        if not p:
            continue
        chiffres = " &nbsp;·&nbsp; ".join(f'<b style="color:{BODY};">{n(p[k])}</b> {lab}'
                                          for k, lab in (("lectures", "lectures"), ("likes", "likes"), ("commentaires", "commentaires"))
                                          if p.get(k) is not None)
        c += carte(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{numero(i, VIOLET)}<td style="{FONT}">'
                   f'<div style="font-size:13px;line-height:18px;color:{MUTED};"><b style="color:{INK};">@{e(p["compte"])}</b> &nbsp;·&nbsp; {e(p["type"])}</div>'
                   f'<div style="font-size:15px;line-height:23px;color:{INK};margin-top:8px;">{e(x.get("raison"))}</div>'
                   f'<div style="font-size:12px;line-height:18px;color:{MUTED};margin-top:8px;">{chiffres}</div>'
                   f'<div style="margin-top:16px;"><a href="{e(p["url"])}" style="display:inline-block;background:{VIOLET};color:#FFFFFF;'
                   f'text-decoration:none;font-size:13px;line-height:18px;font-weight:700;padding:10px 18px;border-radius:10px;">Voir la publication</a></div>'
                   f'</td></tr></table>')
    c += section(4, "Recommandation", "Une seule action, " + vi("à mener cette semaine") + ".")
    c += carte(f'<div style="font-size:11px;font-weight:700;letter-spacing:.6px;color:#CFC6FF;text-align:center;">RECOMMANDATION PRIORITAIRE</div>'
               f'<div style="font-size:18px;line-height:28px;font-weight:800;color:#FFFFFF;text-align:center;margin-top:8px;">{e(a.get("recommandation"))}</div>',
               fond=VIOLET, bord=VIOLET, pad="32px")
    c += (f'<tr><td align="center" style="{FONT}padding:24px 24px 0;font-size:14px;line-height:22px;color:{BODY};">'
          f'Le rapport complet est en {vi("pièce jointe (PDF)")} : insights actionnables, outils cités, '
          f'points de vigilance et qualité des données.</td></tr>')
    titre = f"Semaine du {start.day} au {end.day} {MOIS[end.month - 1]} {end.year}" if start.month == end.month else \
        f"Semaine du {start.day} {MOIS[start.month - 1]} au {end.day} {MOIS[end.month - 1]} {end.year}"
    intro = (f"Ta veille sur {nb_comptes} comptes Instagram : {vi(str(T['posts']) + ' publications')} analysées, "
             f"{vi(str(actifs) + ' comptes actifs')} cette semaine.")
    return coque("VEILLE INSTAGRAM HEBDOMADAIRE", titre, intro, c)


def html_alerte(lines_infos, causes, comptes, tentatives, reco, start, end, now):
    li = "".join(f'<li style="margin-bottom:4px;">{e(x)}</li>' for x in tentatives) or "<li>(journal vide)</li>"
    c = section(1, "Diagnostic")
    c += carte(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="{FONT}font-size:13px;line-height:20px;color:{INK};">'
               f'<tr><td width="140" style="color:{MUTED};padding:4px 0;">Date de l\'échec</td><td style="padding:4px 0;">{e(now)} (heure de Paris)</td></tr>'
               f'<tr><td style="color:{MUTED};padding:4px 0;">Comptes concernés</td><td style="padding:4px 0;">{e(comptes)}</td></tr>'
               f'<tr><td style="color:{MUTED};padding:4px 0;" valign="top">Cause probable</td><td style="padding:4px 0;"><b>{e(causes)}</b></td></tr></table>')
    c += section(2, "Ce qui a été tenté")
    c += carte(f'<ul style="margin:0 0 0 18px;padding:0;font-size:12px;line-height:18px;color:{BODY};">{li}</ul>')
    c += section(3, "Comment corriger")
    c += carte(f'<div style="font-size:15px;line-height:23px;font-weight:800;color:{INK};">{e(reco)}</div>', fond="#FFF5F3", bord=CORAIL)
    intro = ("La veille de cette semaine " + f'<b style="color:{CORAIL};">n\'a pas été générée</b>'
             " : la collecte a échoué. Aucun PDF n'est envoyé, pour ne pas te transmettre une analyse fausse.")
    return coque("⚠ ALERTE · VEILLE INSTAGRAM", f"Semaine du {start:%d/%m} au {end:%d/%m/%Y}", intro, c, couleur=CORAIL)


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
