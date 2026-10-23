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
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (CondPageBreak, HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from common import CONFIG, ND, TZ, load, resolve_week

rl_config.useA85 = 0  # flux binaires compressés : PDF ~25 % plus léger

# Palette
INK = colors.HexColor("#14213D")      # bleu nuit : titres, bandeau
ACCENT = colors.HexColor("#D62F6B")   # rose Instagram : numéros, comptes, liens forts
MUTED = colors.HexColor("#6B7280")    # gris texte secondaire
LINE = colors.HexColor("#E5E7EB")     # filets
CARD = colors.HexColor("#F6F7F9")     # fond des cartes
WARN = colors.HexColor("#C2410C")     # vigilance
WARN_BG = colors.HexColor("#FFF4EC")
OK = colors.HexColor("#15803D")
LINK = "#1D4ED8"

W = A4[0] - 3 * cm  # largeur utile

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]


def style(name, **kw):
    base = dict(fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


P = style("p")
SM = style("sm", fontSize=8, leading=10.5, textColor=MUTED)
SMI = style("smi", fontSize=8, leading=10.5)
B = style("b", fontName="Helvetica-Bold")
LABEL = style("label", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=MUTED)
CARD_T = style("cardt", fontName="Helvetica-Bold", fontSize=11, leading=14)
CHIPS = style("chips", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=ACCENT)
QUOTE = style("quote", fontName="Helvetica-Oblique", fontSize=9, leading=12.5)
SEC_NUM = style("secnum", fontName="Helvetica-Bold", fontSize=18, leading=20, textColor=ACCENT)
SEC_T = style("sect", fontName="Helvetica-Bold", fontSize=14, leading=20)
KPI_N = style("kpin", fontName="Helvetica-Bold", fontSize=20, leading=23, alignment=TA_CENTER)
KPI_L = style("kpil", fontSize=7.5, leading=9.5, textColor=MUTED, alignment=TA_CENTER)
HERO_K = style("herok", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.HexColor("#F9A8C9"))
HERO_T = style("herot", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=colors.white)
HERO_S = style("heros", fontSize=9, leading=12, textColor=colors.HexColor("#CBD5E1"))
RANK = style("rank", fontName="Helvetica-Bold", fontSize=16, leading=18, textColor=ACCENT, alignment=TA_CENTER)
TH = style("th", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=MUTED)
TD = style("td", fontSize=8, leading=10.5)


def t(s):
    """Texte sûr : échappé XML et limité au jeu de caractères des polices standard (cp1252)."""
    s = "" if s is None else str(s)
    return escape(s.encode("cp1252", errors="ignore").decode("cp1252"))


def para(s, st=P):
    return Paragraph(t(s), st)


def link(url, label=None):
    return f'<link href="{escape(url)}" color="{LINK}">{t(label or url)}</link>' if url else t(ND)


def fmt_date(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ).strftime("%d/%m/%Y") if iso else ND


def date_longue(iso, annee=True):
    d = datetime.fromisoformat(iso).astimezone(TZ)
    return f"{d.day} {MOIS[d.month - 1]}" + (f" {d.year}" if annee else "")


def fmt_n(n):
    return f"{n:,}".replace(",", " ")


def engagement(sources, known):
    ps = [known[s] for s in sources if s in known]
    if not ps:
        return ND
    parts = [f"{len(ps)} publication(s)"]
    for key, lab in (("likes", "likes"), ("commentaires", "commentaires"), ("lectures", "lectures"), ("vues", "vues")):
        if key in ("lectures", "vues") and not any(p["type"] in ("Reel", "Vidéo") for p in ps):
            continue
        vals = [p[key] for p in ps if p[key] is not None]
        parts.append(f"{fmt_n(sum(vals))} {lab}" + ("" if len(vals) == len(ps) else f" (sur {len(vals)}/{len(ps)} posts)")
                     if vals else f"{lab} : {ND.lower()}")
    return " · ".join(parts)


def sources_line(sources, known):
    liens = [link(known[s]["url"], f"@{known[s]['compte']} ({fmt_date(known[s]['date_utc'])[:5]})")
             for s in sources or [] if s in known]
    return Paragraph("Sources : " + ", ".join(liens), SM) if liens else Spacer(1, 0)


def section(num, titre):
    tb = Table([[Paragraph(f"{num:02d}", SEC_NUM), Paragraph(t(titre), SEC_T)]], colWidths=[1.2 * cm, W - 1.2 * cm])
    tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return [CondPageBreak(4 * cm), Spacer(1, 14), tb,
            HRFlowable(width="100%", thickness=0.6, color=LINE, spaceBefore=2, spaceAfter=8)]


def card(rows, bar=ACCENT, bg=CARD, width=W):
    """Carte : fond clair + barre verticale colorée à gauche."""
    tb = Table([[r] for r in rows], colWidths=[width])
    tb.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 3, bar),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
    ]))
    return tb


def light_table(rows, widths):
    tb = Table(rows, colWidths=widths, repeatRows=1)
    tb.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tb


def th(*labels):
    return [Paragraph(t(x), TH) for x in labels]


def td(s, st=TD):
    return Paragraph(s if s.startswith("<link") else t(s), st)


def hero(st, debut_iso, fin_iso):
    titre = f"Semaine du {date_longue(debut_iso, annee=False)} au {date_longue(fin_iso)}"
    rows = [[Paragraph("VEILLE INSTAGRAM HEBDOMADAIRE", HERO_K)],
            [Paragraph(t(titre), HERO_T)],
            [Paragraph(t(f"Préparée pour Ivan Ouedraogo · générée le {datetime.now(TZ).strftime('%d/%m/%Y à %H:%M')}"), HERO_S)]]
    tb = Table(rows, colWidths=[W])
    tb.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK),
        ("LINEABOVE", (0, 0), (-1, 0), 4, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 16), ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, 0), 16), ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
    ]))
    return tb


def kpis(st):
    T = st["totaux"]
    actifs = sum(1 for q in st["par_compte"].values() if q["posts"] > 0)
    tr = f"{T['transcrites']}/{T['videos_transcriptibles']}" if T["videos_transcriptibles"] else "-"
    fiab_color = {"élevée": OK, "moyenne": WARN, "faible": colors.HexColor("#B91C1C")}.get(st["fiabilite"], INK)
    data = [(str(T["posts"]), "publications analysées", INK),
            (f"{actifs}/{len(st['par_compte'])}", "comptes actifs", INK),
            (tr, "Reels avec voix transcrits", INK),
            (st["fiabilite"].capitalize(), "fiabilité de la collecte", fiab_color)]
    cells = [[Paragraph(f'<font color="{c.hexval().replace("0x", "#")}">{t(n)}</font>', KPI_N) for n, _, c in data],
             [Paragraph(t(l), KPI_L) for _, l, _ in data]]
    gap = 0.25 * cm
    w = (W - 3 * gap) / 4
    tb = Table(cells, colWidths=[w] * 4)
    tb.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CARD),
        ("LINEAFTER", (0, 0), (2, -1), gap * 2.2, colors.white),
        ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tb


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
        S += [card([Paragraph(f"<b>{t(test_banner)}</b>", P)], bar=WARN, bg=WARN_BG), Spacer(1, 8)]
    S += [hero(st, st["periode"]["debut"], st["periode"]["fin"]), Spacer(1, 10), kpis(st), Spacer(1, 10)]

    if st["statut"] == "partielle":
        S += [card([Paragraph("DONNÉES MANQUANTES ET LIMITES DE LA SEMAINE", LABEL)]
                   + [Paragraph("• " + t(r), P) for r in st["raisons"]], bar=WARN, bg=WARN_BG), Spacer(1, 6)]

    # 1. Résumé exécutif
    S += section(1, "Résumé exécutif")
    S.append(card([Paragraph(t(a["resume_executif"]), style("res", fontSize=10.5, leading=15))], bar=INK))

    # 2. Tendances
    S += section(2, "Grandes tendances de la semaine")
    if a.get("note_volume"):
        S += [para(f"Note : {a['note_volume']}", SM), Spacer(1, 4)]
    half = (W - 20) / 2
    for i, x in enumerate(a.get("tendances") or [], 1):
        duo = Table([[[Paragraph("POURQUOI C'EST IMPORTANT", LABEL), Paragraph(t(x.get("pourquoi") or ND), SMI)],
                      [Paragraph("CE QU'IL FAUT SURVEILLER", LABEL), Paragraph(t(x.get("a_surveiller") or ND), SMI)]]],
                    colWidths=[half / 1.02, half / 1.02])
        duo.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 8),
                                 ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        rows = [Paragraph(f'<font color="{ACCENT.hexval().replace("0x", "#")}">{i}.</font> {t(x["titre"])}', CARD_T),
                Paragraph(t("  ".join("@" + c.lstrip("@") for c in x.get("comptes") or [])), CHIPS),
                Paragraph(t(x.get("sujet") or ""), SM), Spacer(1, 4),
                Paragraph("IDÉES FORTES", LABEL)]
        rows += [Paragraph("• " + t(idee), P) for idee in x.get("idees") or []]
        rows += [Spacer(1, 4), duo, Spacer(1, 3),
                 Paragraph("Engagement : " + t(engagement(x.get("sources") or [], known)), SM),
                 sources_line(x.get("sources"), known)]
        S += [KeepTogether(card(rows)), Spacer(1, 8)]

    # 3. Insights
    S += section(3, "Insights actionnables")
    for i, x in enumerate(a.get("insights") or [], 1):
        rows = [Paragraph(f'<font color="{ACCENT.hexval().replace("0x", "#")}">Insight {i}</font> · {t(x.get("signal"))}', CARD_T),
                Spacer(1, 2),
                Paragraph("POURQUOI C'EST INTÉRESSANT", LABEL), Paragraph(t(x.get("pourquoi") or ND), P),
                Paragraph("ACTION CONCRÈTE", LABEL), Paragraph("<b>" + t(x.get("action") or ND) + "</b>", P),
                Paragraph("EXEMPLE D'APPLICATION", LABEL), Paragraph(t(x.get("exemple") or ND), P),
                sources_line(x.get("sources"), known)]
        S += [KeepTogether(card(rows, bar=INK)), Spacer(1, 8)]

    # 4. Ressources
    S += section(4, "Outils, prompts, workflows et ressources")
    res = a.get("ressources") or []
    if res:
        rows = [th("NOM", "TYPE", "MENTION EXACTE", "SOURCE")]
        for r in res:
            p = known[r["source"]]
            rows.append([Paragraph(f"<b>{t(r['nom'])}</b>", TD),
                         Paragraph(t(r.get("categorie") or ""), style("cat", fontSize=7.5, leading=10, textColor=ACCENT)),
                         Paragraph("« " + t(r["citation"]) + " »", style("cit", fontName="Helvetica-Oblique", fontSize=8, leading=10.5)),
                         td(link(p["url"], "@" + p["compte"]))])
        S.append(light_table(rows, [3.4 * cm, 2 * cm, 8.8 * cm, 3.8 * cm]))
    else:
        S.append(para("Aucun outil, prompt ou workflow explicitement mentionné dans les données de la semaine."))

    # 5. Signaux émergents
    S += section(5, "Signaux émergents")
    for x in a.get("signaux_emergents") or []:
        S += [Paragraph(f'<font color="{ACCENT.hexval().replace("0x", "#")}">›</font> <b>{t(x["signal"])}</b>', P),
              Paragraph(t(x.get("description")), style("sd", leftIndent=9, textColor=INK)),
              Paragraph("&nbsp;&nbsp;&nbsp;" + ", ".join(link(known[s]["url"], "@" + known[s]["compte"])
                                                         for s in x.get("sources") or [] if s in known), SM),
              Spacer(1, 5)]
    if not a.get("signaux_emergents"):
        S.append(para("Aucun signal émergent identifiable avec les données de la semaine."))

    # 6. Vigilance
    S += section(6, "Désaccords et points de vigilance")
    for x in a.get("vigilance") or []:
        p = known[x["source"]]
        rows = [Paragraph("<b>" + t(x["affirmation"]) + "</b>  " + link(p["url"], "@" + p["compte"]), P),
                Paragraph("« " + t(x["citation"]) + " »", QUOTE),
                Paragraph(t(x.get("probleme")), SMI)]
        S += [KeepTogether(card(rows, bar=WARN, bg=WARN_BG)), Spacer(1, 6)]
    if not a.get("vigilance"):
        S.append(para("Aucun point de vigilance relevé."))

    # 7. Top 5
    S += section(7, "Top 5 publications à consulter")
    rows = [th("", "PUBLICATION", "POURQUOI LA REGARDER", "ENGAGEMENT")]
    for i, x in enumerate(a.get("top5") or [], 1):
        p = known[x["shortcode"]]
        rows.append([Paragraph(str(i), RANK),
                     Paragraph(f"<b>@{t(p['compte'])}</b><br/>{t(p['type'])} · {fmt_date(p['date_utc'])}<br/>{link(p['url'], 'Ouvrir ›')}", TD),
                     td(x.get("raison") or ""),
                     Paragraph(t(engagement([p["shortcode"]], known).split(" · ", 1)[-1]).replace(" · ", "<br/>"), SM)])
    S.append(light_table(rows, [1 * cm, 3.6 * cm, 9 * cm, 4.4 * cm]))

    # 8. Synthèse par compte
    S += section(8, "Synthèse par compte")
    rows = [th("COMPTE", "THÈME DOMINANT", "PUBLICATION NOTABLE", "QUALITÉ DES DONNÉES", "INTÉRÊT POUR MA VEILLE")]
    for c in CONFIG["comptes"]:
        c = c.lower()
        s = (a.get("synthese_comptes") or {}).get(c, {})
        q = st["par_compte"][c]
        qual = (f"{q['posts']} post(s), {q['transcrites']}/{q['videos']} vidéo(s) transcrite(s)" if q["statut"] == "ok"
                else "aucune publication" if q["statut"] == "vide" else f"{q['statut']} : {q['cause'] or ND}")
        pn = s.get("publication_notable")
        rows.append([Paragraph(f"<b>@{t(c)}</b>", TD), td(s.get("theme") or ND),
                     td(link(known[pn]["url"], "Ouvrir ›") if pn in known else "-"), td(qual), td(s.get("interet") or ND)])
    S.append(light_table(rows, [3.3 * cm, 4 * cm, 2.3 * cm, 3.6 * cm, 4.8 * cm]))

    # 9. Qualité des données
    S += section(9, "Qualité des données")
    T = st["totaux"]
    rows = [th("COMPTE", "STATUT", "POSTS", "VIDÉOS", "TRANSCR.", "SANS VOIX", "STATS MANQ.", "REMARQUE")]
    for c, q in st["par_compte"].items():
        couleur = {"ok": OK, "vide": MUTED}.get(q["statut"], WARN)
        rows.append([td("@" + c), Paragraph(f'<font color="{couleur.hexval().replace("0x", "#")}"><b>{t(q["statut"])}</b></font>', TD),
                     td(str(q["posts"])), td(str(q["videos"])), td(str(q["transcrites"])),
                     td(str(q["sans_voix"])), td(str(q["stats_manquantes"])), Paragraph(t(q["cause"] or ""), SM)])
    S.append(light_table(rows, [3.0 * cm, 1.3 * cm, 1.3 * cm, 1.4 * cm, 1.6 * cm, 1.6 * cm, 1.9 * cm, 5.9 * cm]))
    S.append(Spacer(1, 6))
    inacc = [c for c, q in st["par_compte"].items() if q["statut"] in ("erreur", "privé")]
    for lab, val_ in (("Reels / vidéos transcrits", f"{T['transcrites']} sur {T['videos_transcriptibles']} avec voix "
                       f"({T['pct_transcription'] if T['pct_transcription'] is not None else '-'} %) ; {T['videos']} vidéos au total"),
                      ("Posts sans likes ou commentaires", f"{T['pct_stats_manquantes'] if T['pct_stats_manquantes'] is not None else '-'} %"),
                      ("Comptes inaccessibles", ", ".join("@" + c for c in inacc) or "aucun"),
                      ("Fiabilité estimée", st["fiabilite"]),
                      ("Coût de collecte", f"{T['cout_apify_usd']:.2f} $".replace(".", ",") if T.get("cout_apify_usd") is not None else ND)):
        S.append(Paragraph(f"<b>{t(lab)} :</b> {t(val_)}", SMI))

    # 10. Limites et recommandation
    reco = card([Paragraph("RECOMMANDATION PRIORITAIRE", style("rl", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=ACCENT)),
                 Paragraph(t(a["recommandation"]), style("rc", fontName="Helvetica-Bold", fontSize=11, leading=15))], bar=ACCENT)
    S.append(KeepTogether(section(10, "Limites et recommandation")
                          + [Paragraph("• " + t(l), P) for l in (a.get("limites") or []) + st["raisons"]]
                          + [Spacer(1, 10), reco]))

    def decor(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(1.5 * cm, 1.25 * cm, A4[0] - 1.5 * cm, 1.25 * cm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(1.5 * cm, 0.85 * cm, f"Veille Instagram · Ivan Ouedraogo · semaine du {debut} au {fin}")
        canvas.drawRightString(A4[0] - 1.5 * cm, 0.85 * cm, f"{doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                      topMargin=1.4 * cm, bottomMargin=1.7 * cm, title=f"Veille Instagram {debut}-{fin}",
                      author="Veille automatisée").build(S, onFirstPage=decor, onLaterPages=decor)
    return out_path


if __name__ == "__main__":
    start, end, wdir = resolve_week()
    banner = sys.argv[sys.argv.index("--bandeau") + 1] if "--bandeau" in sys.argv else None
    out = build(wdir, wdir / f"veille-instagram-{start:%Y-%m-%d}.pdf", banner)
    print(out, out.stat().st_size, "octets")
