"""Génère le PDF de veille à partir de analysis.json (validé) + données de collecte.

Les chiffres (engagement, qualité des données) sont injectés ici depuis les données, jamais
recopiés depuis le texte de l'analyse. Polices standard (Helvetica) : PDF léger, sans police embarquée.
"""
import sys
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from common import CONFIG, ND, TZ, load, resolve_week

rl_config.useA85 = 0  # flux binaires compressés : PDF ~25 % plus léger
ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, spaceAfter=4)
SUB = ParagraphStyle("sub", parent=ss["Normal"], alignment=TA_CENTER, textColor=colors.HexColor("#555555"))
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13, spaceBefore=12, spaceAfter=4,
                    textColor=colors.HexColor("#1F3A5F"))
H3 = ParagraphStyle("h3", parent=ss["Heading4"], fontSize=10.5, spaceBefore=6, spaceAfter=2)
P = ParagraphStyle("p", parent=ss["Normal"], fontSize=9.5, leading=12.5)
SM = ParagraphStyle("sm", parent=P, fontSize=8, leading=10)
BOX = ParagraphStyle("box", parent=P, backColor=colors.HexColor("#FFF4E5"), borderPadding=6,
                     borderColor=colors.HexColor("#E8A33D"), borderWidth=0.8)


def t(s):
    """Texte sûr : échappé XML et limité au jeu de caractères des polices standard (cp1252)."""
    s = "" if s is None else str(s)
    return escape(s.encode("cp1252", errors="ignore").decode("cp1252"))


def para(s, st=P):
    return Paragraph(t(s), st)


def kv(label, value, st=P):
    return Paragraph(f"<b>{t(label)} :</b> {t(value) if value not in (None, '', []) else t(ND)}", st)


def link(url, label=None):
    return f'<link href="{escape(url)}" color="blue"><u>{t(label or url)}</u></link>' if url else t(ND)


def fmt_date(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ).strftime("%d/%m/%Y") if iso else ND


def engagement(sources, known):
    ps = [known[s] for s in sources if s in known]
    if not ps:
        return ND
    parts = [f"{len(ps)} publication(s)"]
    for key, lab in (("likes", "likes"), ("commentaires", "commentaires"), ("lectures", "lectures"), ("vues", "vues")):
        if key in ("lectures", "vues") and not any(p["type"] in ("Reel", "Vidéo") for p in ps):
            continue
        vals = [p[key] for p in ps if p[key] is not None]
        parts.append(f"{lab} : {sum(vals):,}".replace(",", " ") + ("" if len(vals) == len(ps) else f" (sur {len(vals)}/{len(ps)} posts)")
                     if vals else f"{lab} : {ND.lower()}")
    return " ; ".join(parts)


def table(rows, widths, header=True):
    tb = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    tb.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F") if header else colors.white),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white if header else colors.black),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#BBBBBB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
    ]))
    return tb


HDR = ParagraphStyle("hdr", parent=SM, textColor=colors.white, fontName="Helvetica-Bold")


def hrow(*labels):
    return [Paragraph(t(x), HDR) for x in labels]


def cell(s):
    return Paragraph(s if s.startswith("<link") else t(s), SM)


def build(wdir, out_path, test_banner=None):
    a = load(wdir / "analysis.json")
    st = load(wdir / "status.json")
    posts = load(wdir / "posts.json", [])
    val = load(wdir / "validation.json", {})
    if st["statut"] == "echouee":
        raise SystemExit("Collecte échouée : pas de PDF, envoyer l'alerte (alert.py)")
    if not val.get("ok"):
        raise SystemExit("analysis.json non validé : lancer validate.py et corriger")
    known = {p["shortcode"]: p for p in posts}
    debut, fin = fmt_date(st["periode"]["debut"]), fmt_date(st["periode"]["fin"])
    S = []
    if test_banner:
        S.append(Paragraph(f"<b>{t(test_banner)}</b>", BOX))
        S.append(Spacer(1, 6))
    S += [Paragraph("VEILLE INSTAGRAM HEBDOMADAIRE", H1),
          para(f"Semaine du {debut} au {fin}", SUB),
          para(f"Collecte : {st['statut']} | fiabilité {st['fiabilite']} | {st['totaux']['posts']} publications | "
               f"généré le {datetime.now(TZ).strftime('%d/%m/%Y %H:%M')}", SUB), Spacer(1, 8)]

    if st["statut"] == "partielle":
        S.append(Paragraph("<b>Données manquantes et limites de la semaine</b><br/>" +
                           "<br/>".join("• " + t(r) for r in st["raisons"]), BOX))
        S.append(Spacer(1, 6))

    S.append(Paragraph("1. Résumé exécutif", H2))
    S.append(para(a["resume_executif"]))

    S.append(Paragraph("2. Grandes tendances de la semaine", H2))
    if a.get("note_volume"):
        S.append(para(f"Note : {a['note_volume']}", SM))
    for i, x in enumerate(a.get("tendances") or [], 1):
        S.append(KeepTogether([
            Paragraph(f"2.{i} {t(x['titre'])}", H3),
            kv("Sujet principal", x.get("sujet")),
            kv("Comptes concernés", ", ".join("@" + c.lstrip("@") for c in x.get("comptes") or [])),
            kv("Idées fortes", " ; ".join(x.get("idees") or [])),
            kv("Signaux d'engagement disponibles", engagement(x.get("sources") or [], known)),
            kv("Pourquoi c'est important", x.get("pourquoi")),
            kv("Ce qu'il faut surveiller", x.get("a_surveiller")),
            Paragraph("<b>Sources :</b> " + ", ".join(link(known[s]["url"], s) for s in x.get("sources") or [] if s in known), SM),
        ]))

    S.append(Paragraph("3. Insights actionnables", H2))
    for i, x in enumerate(a.get("insights") or [], 1):
        S.append(KeepTogether([
            Paragraph(f"Insight {i}", H3), kv("Signal observé", x.get("signal")),
            kv("Pourquoi c'est intéressant", x.get("pourquoi")), kv("Action concrète", x.get("action")),
            kv("Exemple d'application", x.get("exemple")),
            Paragraph("<b>Sources :</b> " + ", ".join(link(known[s]["url"], s) for s in x.get("sources") or [] if s in known), SM)]))

    S.append(Paragraph("4. Outils, prompts, workflows et ressources", H2))
    res = a.get("ressources") or []
    if res:
        rows = [hrow("Nom", "Catégorie", "Mention exacte", "Source")]
        for r in res:
            p = known[r["source"]]
            rows.append([cell(r["nom"]), cell(r.get("categorie") or ""), cell(f"« {r['citation']} »"),
                         cell(link(p["url"], "@" + p["compte"]))])
        S.append(table(rows, [3.2 * cm, 2.2 * cm, 8.6 * cm, 3 * cm]))
    else:
        S.append(para("Aucun outil, prompt ou workflow explicitement mentionné dans les données de la semaine."))

    S.append(Paragraph("5. Signaux émergents", H2))
    for x in a.get("signaux_emergents") or []:
        S.append(Paragraph(f"• <b>{t(x['signal'])}</b> : {t(x.get('description'))} "
                           f"({', '.join(link(known[s]['url'], s) for s in x.get('sources') or [] if s in known)})", P))
    if not a.get("signaux_emergents"):
        S.append(para("Aucun signal émergent identifiable avec les données de la semaine."))

    S.append(Paragraph("6. Désaccords et points de vigilance", H2))
    for x in a.get("vigilance") or []:
        p = known[x["source"]]
        S.append(Paragraph(f"• <b>{t(x['affirmation'])}</b> ({link(p['url'], '@' + p['compte'])}) : « {t(x['citation'])} » "
                           f"<br/>&nbsp;&nbsp;{t(x.get('probleme'))}", P))
    if not a.get("vigilance"):
        S.append(para("Aucun point de vigilance relevé."))

    S.append(Paragraph("7. Top 5 publications à consulter", H2))
    rows = [hrow("#", "Compte", "Type / date", "Lien", "Pourquoi", "Engagement")]
    for i, x in enumerate(a.get("top5") or [], 1):
        p = known[x["shortcode"]]
        rows.append([cell(str(i)), cell("@" + p["compte"]), cell(f"{p['type']} {fmt_date(p['date_utc'])}"),
                     cell(link(p["url"], "ouvrir")), cell(x.get("raison") or ""), cell(engagement([p["shortcode"]], known).split(" ; ", 1)[-1])])
    S.append(table(rows, [0.6 * cm, 2.7 * cm, 2.3 * cm, 1.3 * cm, 6.2 * cm, 3.9 * cm]))

    S.append(Paragraph("8. Synthèse par compte", H2))
    rows = [hrow("Compte", "Thème dominant", "Publication notable", "Qualité des données", "Intérêt pour ma veille")]
    for c in CONFIG["comptes"]:
        c = c.lower()
        s = (a.get("synthese_comptes") or {}).get(c, {})
        q = st["par_compte"][c]
        qual = (f"{q['statut']} : {q['posts']} post(s), {q['transcrites']}/{q['videos']} vidéo(s) transcrite(s)"
                if q["statut"] in ("ok", "vide") else f"{q['statut']} : {q['cause'] or ND}")
        pn = s.get("publication_notable")
        rows.append([cell("@" + c), cell(s.get("theme") or ND), cell(link(known[pn]["url"], pn) if pn in known else ND),
                     cell(qual), cell(s.get("interet") or ND)])
    S.append(table(rows, [3 * cm, 3.6 * cm, 2.6 * cm, 4 * cm, 3.8 * cm]))

    S.append(Paragraph("9. Qualité des données", H2))
    T = st["totaux"]
    rows = [hrow("Compte", "Statut", "Posts", "Vidéos", "Transc.", "Sans voix", "Stats manq.", "Cause / remarque")]
    for c, q in st["par_compte"].items():
        rows.append([cell("@" + c), cell(q["statut"]), cell(str(q["posts"])), cell(str(q["videos"])), cell(str(q["transcrites"])),
                     cell(str(q["sans_voix"])), cell(str(q["stats_manquantes"])), cell(q["cause"] or "")])
    S.append(table(rows, [2.8 * cm, 1.4 * cm, 1.1 * cm, 1.2 * cm, 1.6 * cm, 1.4 * cm, 1.8 * cm, 5.7 * cm]))
    S.append(Spacer(1, 4))
    inacc = [c for c, q in st["par_compte"].items() if q["statut"] in ("erreur", "privé")]
    S += [kv("Reels / vidéos transcrits", f"{T['transcrites']} sur {T['videos_transcriptibles']} avec voix "
             f"({T['pct_transcription'] if T['pct_transcription'] is not None else '-'} %) ; {T['videos']} vidéos au total"),
          kv("Posts sans likes ou commentaires", f"{T['pct_stats_manquantes'] if T['pct_stats_manquantes'] is not None else '-'} %"),
          kv("Comptes inaccessibles", ", ".join("@" + c for c in inacc) or "aucun"),
          kv("Fiabilité estimée de la collecte", st["fiabilite"]),
          kv("Coût de collecte Apify", f"{T['cout_apify_usd']} $" if T.get("cout_apify_usd") is not None else None)]

    S.append(KeepTogether([Paragraph("10. Limites et recommandation", H2)]
                          + [para("• " + l) for l in (a.get("limites") or []) + st["raisons"]]
                          + [Spacer(1, 4), Paragraph(f"<b>Recommandation prioritaire :</b> {t(a['recommandation'])}", BOX)]))

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(1.5 * cm, 1 * cm, f"Veille Instagram, Ivan Ouedraogo | semaine du {debut} au {fin} | page {doc.page}")

    SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                      topMargin=1.5 * cm, bottomMargin=1.6 * cm, title=f"Veille Instagram {debut}-{fin}",
                      author="Veille automatisée").build(S, onFirstPage=footer, onLaterPages=footer)
    return out_path


if __name__ == "__main__":
    start, end, wdir = resolve_week()
    banner = sys.argv[sys.argv.index("--bandeau") + 1] if "--bandeau" in sys.argv else None
    out = build(wdir, wdir / f"veille-instagram-{start:%Y-%m-%d}.pdf", banner)
    print(out, out.stat().st_size, "octets")
