"""Génère le PDF de veille à partir de analysis.json (validé) + données de collecte.

Les chiffres (engagement, qualité des données) sont injectés ici depuis les données, jamais
recopiés depuis le texte de l'analyse.
Style : fond lavande, pastilles numérotées, grands titres centrés, cartes blanches arrondies,
accents violets (police Plus Jakarta Sans, licence OFL, embarquée depuis fonts/).
"""
import sys
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from common import CONFIG, ND, TZ, load, resolve_week

rl_config.useA85 = 0  # flux binaires compressés

FONTS = Path(__file__).resolve().parent / "fonts"
for nom in ("Regular", "Medium", "Bold", "ExtraBold"):
    pdfmetrics.registerFont(TTFont(f"PJS-{nom}", str(FONTS / f"PlusJakartaSans-{nom}.ttf")))
pdfmetrics.registerFontFamily("PJS", normal="PJS-Regular", bold="PJS-Bold", italic="PJS-Regular", boldItalic="PJS-Bold")

# Palette (reprise du mémo Figma : lavande, bleu ardoise, violet)
FOND = colors.HexColor("#F4F3FC")
INK = colors.HexColor("#2B2F4E")
BODY = colors.HexColor("#555A75")
MUTED = colors.HexColor("#8A8FA8")
VIOLET = colors.HexColor("#6E56F8")
PASTILLE = colors.HexColor("#E3E0FB")
BORD = colors.HexColor("#E7E5F6")
CORAIL = colors.HexColor("#E8604C")
CORAIL_BG = colors.HexColor("#FFF5F3")
VERT = colors.HexColor("#1F9D63")
HEX = lambda c: "#" + c.hexval()[2:]  # noqa: E731

W = A4[0] - 3 * cm  # largeur utile
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]


def style(name, **kw):
    base = dict(fontName="PJS-Regular", fontSize=9.5, leading=14, textColor=BODY)
    base.update(kw)
    return ParagraphStyle(name, **base)


P = style("p")
PI = style("pi", textColor=INK)
SM = style("sm", fontSize=8, leading=11, textColor=MUTED)
SMI = style("smi", fontSize=8.5, leading=12)
LABEL = style("label", fontName="PJS-Bold", fontSize=7.5, leading=10, textColor=MUTED)
CARD_T = style("cardt", fontName="PJS-ExtraBold", fontSize=12, leading=16, textColor=INK)
CHIPS = style("chips", fontName="PJS-Bold", fontSize=8.5, leading=12, textColor=VIOLET)
QUOTE = style("quote", fontName="PJS-Medium", fontSize=9, leading=13, textColor=INK)
TITRE = style("titre", fontName="PJS-ExtraBold", fontSize=24, leading=29, textColor=INK, alignment=TA_CENTER)
INTRO = style("intro", fontSize=10.5, leading=16, textColor=BODY, alignment=TA_CENTER)
PAST = style("past", fontName="PJS-Bold", fontSize=11, leading=13, textColor=INK, alignment=TA_CENTER)
PAST_B = style("pastb", fontName="PJS-Bold", fontSize=10, leading=12, textColor=colors.white, alignment=TA_CENTER)
HERO_T = style("herot", fontName="PJS-ExtraBold", fontSize=30, leading=36, textColor=INK, alignment=TA_CENTER)
KPI_N = style("kpin", fontName="PJS-ExtraBold", fontSize=20, leading=24, textColor=INK, alignment=TA_CENTER)
KPI_L = style("kpil", fontSize=7.5, leading=10, textColor=MUTED, alignment=TA_CENTER)
TH = style("th", fontName="PJS-Bold", fontSize=6.8, leading=9, textColor=MUTED)
TD = style("td", fontSize=8, leading=11, textColor=INK)


def t(s):
    """Texte sûr : échappé XML, caractères hors police (émojis) retirés."""
    s = "" if s is None else str(s)
    return escape(s.encode("cp1252", errors="ignore").decode("cp1252"))


def v(s):
    """Mise en avant violette, comme les mots-clés du mémo."""
    return f'<font name="PJS-Bold" color="{HEX(VIOLET)}">{s}</font>'


def link(url, label=None):
    return f'<link href="{escape(url)}" color="{HEX(VIOLET)}"><font name="PJS-Bold">{t(label or url)}</font></link>' if url else t(ND)


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


def pastille(texte, fond=PASTILLE, st=PAST, taille=26):
    tb = Table([[Paragraph(t(texte), st)]], colWidths=[taille], rowHeights=[taille])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fond), ("ROUNDEDCORNERS", [taille / 2] * 4),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return tb


def section(num, titre, intro=None):
    """En-tête de section du mémo : pastille numérotée, grand titre centré, chapeau centré."""
    out = [CondPageBreak(6 * cm), Spacer(1, 22), pastille(str(num)), Spacer(1, 8), Paragraph(t(titre), TITRE)]
    if intro:
        out += [Spacer(1, 4), Paragraph(intro, INTRO)]
    return out + [Spacer(1, 14)]


def colle(S, premier):
    """Attache le premier élément à l'en-tête de section qui le précède (évite un titre seul en bas de page)."""
    i = max(k for k, x in enumerate(S) if isinstance(x, CondPageBreak))
    entete = S[i + 1:]
    del S[i + 1:]
    S.append(KeepTogether(entete + [premier]))


def carte(rows, width=W, fond=colors.white, bord=BORD, pad=14):
    tb = Table([[r] for r in rows], colWidths=[width])
    tb.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fond), ("ROUNDEDCORNERS", [10, 10, 10, 10]),
        ("BOX", (0, 0), (-1, -1), 0.8, bord),
        ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, 0), pad), ("BOTTOMPADDING", (0, -1), (-1, -1), pad),
    ]))
    return tb


def carte_numerotee(num, rows, fond_pastille=INK):
    """Carte avec pastille pleine à gauche, comme les annotations du mémo."""
    inner = Table([[pastille(str(num), fond=fond_pastille, st=PAST_B, taille=22), rows]], colWidths=[30, W - 2 * 14 - 30])
    inner.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return carte([inner])


def tableau(rows, widths):
    tb = Table(rows, colWidths=widths, repeatRows=1)
    tb.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white), ("ROUNDEDCORNERS", [10, 10, 10, 10]),
        ("BOX", (0, 0), (-1, -1), 0.8, BORD),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FAFAFE")),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORD),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tb


def th(*labels):
    return [Paragraph(t(x), TH) for x in labels]


def td(s, st=TD):
    return Paragraph(s if s.startswith("<link") else t(s), st)


def couverture(st):
    T = st["totaux"]
    actifs = sum(1 for q in st["par_compte"].values() if q["posts"] > 0)
    titre = f"Semaine du {date_longue(st['periode']['debut'], annee=False)} au {date_longue(st['periode']['fin'])}"
    nb_posts, nb_comptes = T["posts"], len(st["par_compte"])
    intro = (f"Ta veille sur {nb_comptes} comptes Instagram : {v(f'{nb_posts} publications')} analysées, "
             f"{v(f'{actifs} comptes actifs')} cette semaine.")
    tr = f"{T['transcrites']}/{T['videos_transcriptibles']}" if T["videos_transcriptibles"] else "-"
    fiab = st["fiabilite"].capitalize()
    fiab_c = {"Élevée": VERT, "Moyenne": CORAIL}.get(fiab, CORAIL)
    tuiles = [(str(T["posts"]), "publications", INK), (f"{actifs}/{len(st['par_compte'])}", "comptes actifs", INK),
              (tr, "Reels transcrits", INK), (fiab, "fiabilité de la collecte", fiab_c)]
    gap = 8
    w = (W - 3 * gap) / 4
    cellules = []
    for n, l, c in tuiles:
        cellules.append(carte([Paragraph(f'<font color="{HEX(c)}">{t(n)}</font>', KPI_N), Paragraph(t(l), KPI_L)], width=w, pad=10))
    rang = Table([cellules], colWidths=[w + gap] * 3 + [w])
    rang.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    genere = datetime.now(TZ).strftime("%d/%m/%Y à %H:%M")
    return [Spacer(1, 10),
            Table([[Paragraph("VEILLE INSTAGRAM HEBDOMADAIRE", style("k", fontName="PJS-Bold", fontSize=8, leading=10,
                                                                     textColor=VIOLET, alignment=TA_CENTER))]],
                  colWidths=[6.2 * cm], rowHeights=[20],
                  style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), PASTILLE), ("ROUNDEDCORNERS", [10] * 4),
                                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])),
            Spacer(1, 12), Paragraph(t(titre), HERO_T), Spacer(1, 8), Paragraph(intro, INTRO),
            Paragraph(t(f"Préparée pour Ivan Ouedraogo · générée le {genere}"), style("g", fontSize=8, leading=11,
                                                                                     textColor=MUTED, alignment=TA_CENTER)),
            Spacer(1, 16), rang]


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
        S += [carte([Paragraph(f'<font name="PJS-Bold">{t(test_banner)}</font>', PI)], fond=CORAIL_BG, bord=CORAIL), Spacer(1, 6)]
    S += couverture(st)

    if st["statut"] == "partielle":
        S += [Spacer(1, 10), carte([Paragraph("DONNÉES MANQUANTES ET LIMITES DE LA SEMAINE",
                                              style("lw", fontName="PJS-Bold", fontSize=7.5, leading=10, textColor=CORAIL))]
                                   + [Paragraph("• " + t(r), PI) for r in st["raisons"]], fond=CORAIL_BG, bord=CORAIL)]

    # 1. Résumé exécutif
    S += section(1, "Résumé exécutif", "L'essentiel de la semaine en " + v("trois phrases") + ".")
    colle(S, carte([Paragraph(t(a["resume_executif"]), style("res", fontSize=11, leading=17, textColor=INK))], pad=18))

    # 2. Tendances
    nb = len(a.get("tendances") or [])
    S += section(2, "Grandes tendances", f"Les {v(f'{nb} sujets')} qui ont structuré la semaine, avec les comptes qui les portent.")
    if a.get("note_volume"):
        S += [Paragraph(t(f"Note : {a['note_volume']}"), style("nv", fontSize=8, leading=11, textColor=MUTED, alignment=TA_CENTER)),
              Spacer(1, 6)]
    demi = (W - 2 * 14 - 30 - 12) / 2
    for i, x in enumerate(a.get("tendances") or [], 1):
        duo = Table([[[Paragraph("POURQUOI C'EST IMPORTANT", LABEL), Paragraph(t(x.get("pourquoi") or ND), SMI)],
                      [Paragraph("CE QU'IL FAUT SURVEILLER", LABEL), Paragraph(t(x.get("a_surveiller") or ND), SMI)]]],
                    colWidths=[demi + 6, demi + 6])
        duo.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 12),
                                 ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        rows = [Paragraph(t(x["titre"]), CARD_T),
                Paragraph(t("  ".join("@" + c.lstrip("@") for c in x.get("comptes") or [])), CHIPS),
                Paragraph(t(x.get("sujet") or ""), SM), Spacer(1, 6),
                Paragraph("IDÉES FORTES", LABEL)]
        rows += [Paragraph("• " + t(idee), PI) for idee in x.get("idees") or []]
        rows += [Spacer(1, 6), duo, Spacer(1, 4),
                 Paragraph("Engagement : " + t(engagement(x.get("sources") or [], known)), SM),
                 sources_line(x.get("sources"), known)]
        bloc_ = carte_numerotee(i, rows)
        colle(S, bloc_) if i == 1 else S.append(KeepTogether(bloc_))
        S.append(Spacer(1, 10))

    # 3. Insights
    S += section(3, "Insights actionnables", "Trois signaux concrets, et " + v("ce que tu peux en faire") + " dès cette semaine.")
    for i, x in enumerate(a.get("insights") or [], 1):
        rows = [Paragraph(t(x.get("signal")), CARD_T), Spacer(1, 4),
                Paragraph("POURQUOI C'EST INTÉRESSANT", LABEL), Paragraph(t(x.get("pourquoi") or ND), PI), Spacer(1, 3),
                Paragraph("ACTION CONCRÈTE", LABEL),
                Paragraph(f'<font name="PJS-Bold" color="{HEX(VIOLET)}">{t(x.get("action") or ND)}</font>', PI), Spacer(1, 3),
                Paragraph("EXEMPLE D'APPLICATION", LABEL), Paragraph(t(x.get("exemple") or ND), PI),
                sources_line(x.get("sources"), known)]
        bloc_ = carte_numerotee(i, rows, fond_pastille=VIOLET)
        colle(S, bloc_) if i == 1 else S.append(KeepTogether(bloc_))
        S.append(Spacer(1, 10))

    # 4. Ressources
    S += section(4, "Outils et ressources", "Uniquement ce qui est " + v("réellement cité") + " dans les publications, avec la phrase exacte.")
    res = a.get("ressources") or []
    if res:
        rows = [th("NOM", "TYPE", "MENTION EXACTE", "SOURCE")]
        for r in res:
            p = known[r["source"]]
            rows.append([Paragraph(f'<font name="PJS-Bold">{t(r["nom"])}</font>', TD),
                         Paragraph(t(r.get("categorie") or ""), style("cat", fontName="PJS-Bold", fontSize=7.5, leading=10, textColor=VIOLET)),
                         Paragraph("« " + t(r["citation"]) + " »", style("cit", fontSize=8, leading=11, textColor=BODY)),
                         td(link(p["url"], "@" + p["compte"]))])
        S.append(tableau(rows, [3.4 * cm, 2 * cm, 8.6 * cm, 4 * cm]))
    else:
        S.append(Paragraph("Aucun outil, prompt ou workflow explicitement mentionné cette semaine.", INTRO))

    # 5. Signaux émergents
    S += section(5, "Signaux émergents", "Les sujets " + v("récents ou en croissance") + " à garder à l'œil.")
    sig = a.get("signaux_emergents") or []
    for i, x in enumerate(sig, 1):
        rows = [Paragraph(t(x["signal"]), style("st", fontName="PJS-Bold", fontSize=10.5, leading=14, textColor=INK)),
                Paragraph(t(x.get("description")), PI),
                Paragraph(", ".join(link(known[s]["url"], "@" + known[s]["compte"]) for s in x.get("sources") or [] if s in known), SM)]
        colle(S, carte_numerotee(i, rows)) if i == 1 else S.append(KeepTogether(carte_numerotee(i, rows)))
        S.append(Spacer(1, 8))
    if not sig:
        S.append(Paragraph("Aucun signal émergent identifiable avec les données de la semaine.", INTRO))

    # 6. Vigilance
    S += section(6, "Points de vigilance", "Promesses exagérées, affirmations non vérifiées et " + v("contenus sponsorisés") + ".")
    for k, x in enumerate(a.get("vigilance") or []):
        p = known[x["source"]]
        rows = [Paragraph(f'<font name="PJS-Bold" color="{HEX(INK)}">{t(x["affirmation"])}</font>  ' + link(p["url"], "@" + p["compte"]), PI),
                Spacer(1, 3), Paragraph("« " + t(x["citation"]) + " »", QUOTE), Spacer(1, 3),
                Paragraph(f'<font color="{HEX(CORAIL)}" name="PJS-Medium">{t(x.get("probleme"))}</font>', SMI)]
        colle(S, carte(rows)) if k == 0 else S.append(KeepTogether(carte(rows)))
        S.append(Spacer(1, 8))
    if not a.get("vigilance"):
        S.append(Paragraph("Aucun point de vigilance relevé.", INTRO))

    # 7. Top 5
    S += section(7, "Top 5 à consulter", "Les publications les plus " + v("utiles pour ta veille") + ", pas forcément les plus vues.")
    for i, x in enumerate(a.get("top5") or [], 1):
        p = known[x["shortcode"]]
        chiffres = engagement([p["shortcode"]], known).split(" · ", 1)[-1]
        rows = [Paragraph(f'<font name="PJS-Bold" color="{HEX(INK)}">@{t(p["compte"])}</font>  '
                          f'<font color="{HEX(MUTED)}">{t(p["type"])} · {fmt_date(p["date_utc"])}</font>', PI),
                Paragraph(t(x.get("raison") or ""), style("rz", fontSize=10, leading=15, textColor=INK)),
                Paragraph(t(chiffres) + "   " + link(p["url"], "Voir la publication ›"), SM)]
        bloc_ = carte_numerotee(i, rows, fond_pastille=VIOLET)
        colle(S, bloc_) if i == 1 else S.append(KeepTogether(bloc_))
        S.append(Spacer(1, 8))

    # 8. Synthèse par compte
    S += section(8, "Synthèse par compte", "Ce que chacun des " + v(f"{len(CONFIG['comptes'])} comptes") + " a apporté cette semaine.")
    rows = [th("COMPTE", "THÈME DOMINANT", "POST", "DONNÉES", "INTÉRÊT POUR MA VEILLE")]
    for c in CONFIG["comptes"]:
        c = c.lower()
        s = (a.get("synthese_comptes") or {}).get(c, {})
        q = st["par_compte"][c]
        qual = (f"{q['posts']} post(s), {q['transcrites']}/{q['videos']} transcrite(s)" if q["statut"] == "ok"
                else "aucune publication" if q["statut"] == "vide" else f"{q['statut']} : {q['cause'] or ND}")
        pn = s.get("publication_notable")
        rows.append([Paragraph(f'<font name="PJS-Bold">@{t(c)}</font>', TD), td(s.get("theme") or ND),
                     td(link(known[pn]["url"], "Voir ›") if pn in known else "-"), td(qual), td(s.get("interet") or ND)])
    S.append(tableau(rows, [3.4 * cm, 4.1 * cm, 1.9 * cm, 3.5 * cm, 5.1 * cm]))

    # 9. Qualité des données
    T = st["totaux"]
    S += section(9, "Qualité des données", "Ce qui a été " + v("réellement collecté") + ", compte par compte.")
    rows = [th("COMPTE", "STATUT", "POSTS", "VIDÉOS", "TRANSCR.", "SANS VOIX", "STATS MANQ.", "REMARQUE")]
    for c, q in st["par_compte"].items():
        couleur = {"ok": VERT, "vide": MUTED}.get(q["statut"], CORAIL)
        rows.append([td("@" + c), Paragraph(f'<font name="PJS-Bold" color="{HEX(couleur)}">{t(q["statut"])}</font>', TD),
                     td(str(q["posts"])), td(str(q["videos"])), td(str(q["transcrites"])),
                     td(str(q["sans_voix"])), td(str(q["stats_manquantes"])), Paragraph(t(q["cause"] or ""), SM)])
    S.append(tableau(rows, [3.4 * cm, 1.4 * cm, 1.3 * cm, 1.5 * cm, 1.7 * cm, 1.6 * cm, 1.9 * cm, 5.2 * cm]))
    S.append(Spacer(1, 8))
    inacc = [c for c, q in st["par_compte"].items() if q["statut"] in ("erreur", "privé")]
    lignes = [("Reels / vidéos transcrits", f"{T['transcrites']} sur {T['videos_transcriptibles']} avec voix "
               f"({T['pct_transcription'] if T['pct_transcription'] is not None else '-'} %) ; {T['videos']} vidéos au total"),
              ("Posts sans likes ou commentaires", f"{T['pct_stats_manquantes'] if T['pct_stats_manquantes'] is not None else '-'} %"),
              ("Comptes inaccessibles", ", ".join("@" + c for c in inacc) or "aucun"),
              ("Fiabilité estimée", st["fiabilite"]),
              ("Coût de collecte", f"{T['cout_apify_usd']:.2f} $".replace(".", ",") if T.get("cout_apify_usd") is not None else ND)]
    S.append(carte([Paragraph(f'<font name="PJS-Bold" color="{HEX(INK)}">{t(l)} :</font> {t(x)}', SMI) for l, x in lignes]))

    # 10. Limites et recommandation
    reco = carte([Paragraph("RECOMMANDATION PRIORITAIRE", style("rl", fontName="PJS-Bold", fontSize=8, leading=11,
                                                                textColor=colors.HexColor("#C9C0FF"), alignment=TA_CENTER)),
                  Spacer(1, 4),
                  Paragraph(t(a["recommandation"]), style("rc", fontName="PJS-ExtraBold", fontSize=13, leading=19,
                                                           textColor=colors.white, alignment=TA_CENTER))],
                 fond=VIOLET, bord=VIOLET, pad=18)
    S.append(KeepTogether(section(10, "Limites et recommandation", "Ce qu'il faut garder en tête, et " + v("une seule action") + " à mener.")
                          + [carte([Paragraph("• " + t(l), PI) for l in (a.get("limites") or []) + st["raisons"]]),
                             Spacer(1, 12), reco]))

    def decor(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(FOND)
        canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        canvas.setFont("PJS-Regular", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(1.5 * cm, 0.9 * cm, f"Veille Instagram · Ivan Ouedraogo · semaine du {debut} au {fin}")
        canvas.setFont("PJS-Bold", 7.5)
        canvas.drawRightString(A4[0] - 1.5 * cm, 0.9 * cm, str(doc.page))
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
