"""Génère le PDF de veille à partir de analysis.json (validé) + données de collecte.

Les chiffres (engagement, qualité des données) sont injectés ici depuis les données, jamais
recopiés depuis le texte de l'analyse.

Système de design (inspiré du mémo Figma) :
- espacements sur une grille de 4 pt : 4, 8, 12, 16, 24, 32, 48 ;
- échelle typographique : Display 30 · Titre de section 22 · Titre de carte 12.5 · Texte 9.5 · Détail 8 · Étiquette 7 ;
- trois niveaux de couleur de texte : INK (titres), BODY (texte), MUTED (métadonnées) ; le violet est réservé
  aux comptes, liens et mises en avant ;
- dans chaque carte, un seul ordre de lecture : titre > contexte > contenu > détails (séparés par un filet).
Police Plus Jakarta Sans (licence OFL), embarquée depuis fonts/.
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
from reportlab.platypus import (CondPageBreak, HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from common import CONFIG, ND, TZ, load, resolve_week

rl_config.useA85 = 0

FONTS = Path(__file__).resolve().parent / "fonts"
for _nom in ("Regular", "Medium", "Bold", "ExtraBold"):
    pdfmetrics.registerFont(TTFont(f"PJS-{_nom}", str(FONTS / f"PlusJakartaSans-{_nom}.ttf")))
pdfmetrics.registerFontFamily("PJS", normal="PJS-Regular", bold="PJS-Bold", italic="PJS-Regular", boldItalic="PJS-Bold")

# ---- Jetons de design -------------------------------------------------------------------------
S1, S2, S3, S4, S6, S8, S12 = 4, 8, 12, 16, 24, 32, 48     # espacements (pt)
RAYON = 12

FOND = colors.HexColor("#F4F3FC")
SURFACE = colors.white
INK = colors.HexColor("#262A47")
BODY = colors.HexColor("#4F5470")
MUTED = colors.HexColor("#8C90A8")
VIOLET = colors.HexColor("#6E56F8")
VIOLET_PALE = colors.HexColor("#EFECFF")
PASTILLE = colors.HexColor("#E3E0FB")
BORD = colors.HexColor("#E6E4F4")
FILET = colors.HexColor("#EEEDF6")
CORAIL = colors.HexColor("#D9533F")
CORAIL_PALE = colors.HexColor("#FFF4F1")
VERT = colors.HexColor("#1F9D63")
HEX = lambda c: "#" + c.hexval()[2:]  # noqa: E731

W = A4[0] - 2 * 1.6 * cm      # largeur utile
PAD = S4 + 2                  # marge intérieure des cartes (18 pt)
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre"]


def style(name, **kw):
    """Style typographique. Avec parent=, on hérite du parent et on ne surcharge que ce qui est précisé."""
    if "parent" in kw:
        return ParagraphStyle(name, **kw)
    base = dict(fontName="PJS-Regular", fontSize=9.5, leading=15, textColor=BODY)
    base.update(kw)
    return ParagraphStyle(name, **base)


# Échelle typographique
DISPLAY = style("display", fontName="PJS-ExtraBold", fontSize=30, leading=37, textColor=INK, alignment=TA_CENTER)
H_SECTION = style("hsec", fontName="PJS-ExtraBold", fontSize=22, leading=28, textColor=INK, alignment=TA_CENTER)
CHAPEAU = style("chapeau", fontSize=10.5, leading=16.5, alignment=TA_CENTER)
H_CARTE = style("hcarte", fontName="PJS-ExtraBold", fontSize=12.5, leading=17, textColor=INK)
LEAD = style("lead", fontSize=11, leading=18, textColor=INK)
TEXTE = style("texte")
TEXTE_INK = style("texteink", textColor=INK)
DETAIL = style("detail", fontSize=8, leading=12, textColor=MUTED)
ETIQUETTE = style("etiquette", fontName="PJS-Bold", fontSize=7, leading=10, textColor=MUTED)
COMPTES = style("comptes", fontName="PJS-Bold", fontSize=8.5, leading=12, textColor=VIOLET)
NUM_N = style("numn", fontName="PJS-ExtraBold", fontSize=21, leading=25, textColor=INK, alignment=TA_CENTER)
NUM_L = style("numl", fontSize=7.5, leading=10, textColor=MUTED, alignment=TA_CENTER)
TH = style("th", fontName="PJS-Bold", fontSize=6.8, leading=9, textColor=MUTED)
TD = style("td", fontSize=8, leading=11.5, textColor=INK)
TD_MUTED = style("tdm", fontSize=7.5, leading=11, textColor=MUTED)


# ---- Utilitaires de texte ---------------------------------------------------------------------
def t(s):
    """Texte sûr : échappé XML, caractères hors police (émojis) retirés."""
    s = "" if s is None else str(s)
    return escape(s.encode("cp1252", errors="ignore").decode("cp1252"))


def v(s):
    return f'<font name="PJS-Bold" color="{HEX(VIOLET)}">{s}</font>'


def gras(s, couleur=INK):
    return f'<font name="PJS-Bold" color="{HEX(couleur)}">{s}</font>'


def link(url, label=None):
    return f'<link href="{escape(url)}" color="{HEX(VIOLET)}"><font name="PJS-Bold">{t(label or url)}</font></link>' if url else t(ND)


def fmt_date(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ).strftime("%d/%m/%Y") if iso else ND


def fmt_n(n):
    return f"{n:,}".replace(",", " ")


def titre_semaine(debut_iso, fin_iso):
    d, f = datetime.fromisoformat(debut_iso).astimezone(TZ), datetime.fromisoformat(fin_iso).astimezone(TZ)
    if d.month == f.month:
        return f"Semaine du {d.day} au {f.day} {MOIS[f.month - 1]} {f.year}"
    return f"Semaine du {d.day} {MOIS[d.month - 1]} au {f.day} {MOIS[f.month - 1]} {f.year}"


def stats(ps):
    """Chiffres d'engagement agrégés, directement depuis les données."""
    out = []
    for key, lab in (("lectures", "lectures"), ("likes", "likes"), ("commentaires", "commentaires")):
        if key == "lectures" and not any(p["type"] in ("Reel", "Vidéo") for p in ps):
            continue
        vals = [p[key] for p in ps if p[key] is not None]
        if vals:
            out.append(f"{gras(fmt_n(sum(vals)), BODY)} {lab}" + ("" if len(vals) == len(ps) else f" ({len(vals)}/{len(ps)} posts)"))
        else:
            out.append(f"{lab} : {t(ND.lower())}")
    return "  ·  ".join(out)


def sources(srcs, known):
    liens = [link(known[s]["url"], f"@{known[s]['compte']} {fmt_date(known[s]['date_utc'])[:5]}")
             for s in srcs or [] if s in known]
    return "  ·  ".join(liens)


# ---- Composants -------------------------------------------------------------------------------
def sans_marges(tb, *extra):
    tb.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"), *extra]))
    return tb


def pastille(texte, fond=PASTILLE, couleur=INK, taille=26, corps=11):
    st = style("p" + str(taille), fontName="PJS-Bold", fontSize=corps, leading=corps + 1, textColor=couleur, alignment=TA_CENTER)
    tb = Table([[Paragraph(t(texte), st)]], colWidths=[taille], rowHeights=[taille])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fond), ("ROUNDEDCORNERS", [taille / 2] * 4),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    return tb


def etiquette_pilule(texte, couleur=VIOLET, fond=PASTILLE, largeur=6.4 * cm):
    st = style("pil", fontName="PJS-Bold", fontSize=7.5, leading=9, textColor=couleur, alignment=TA_CENTER)
    tb = Table([[Paragraph(t(texte), st)]], colWidths=[largeur], rowHeights=[20])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fond), ("ROUNDEDCORNERS", [10] * 4),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))
    return tb


def centre(flowable_or_text, largeur=0.78 * W, st=CHAPEAU):
    """Bloc centré à largeur limitée : lignes de lecture courtes sous les titres."""
    contenu = Paragraph(flowable_or_text, st) if isinstance(flowable_or_text, str) else flowable_or_text
    tb = Table([[contenu]], colWidths=[largeur])
    return sans_marges(tb)


def entete_section(num, titre, chapeau=None, nouvelle_page=False):
    """Pastille > titre > chapeau. Renvoie une liste ; colle() la lie au premier contenu.
    nouvelle_page : les grandes sections ouvrent une page, comme les planches du mémo (blancs voulus)."""
    haut = [PageBreak(), CondPageBreak(7 * cm), Spacer(1, S6)] if nouvelle_page else [CondPageBreak(7 * cm), Spacer(1, S12 - S2)]
    out = haut + [pastille(str(num)), Spacer(1, S3), Paragraph(t(titre), H_SECTION)]
    if chapeau:
        out += [Spacer(1, S2), centre(chapeau)]
    return out + [Spacer(1, S6)]


def colle(S, premier):
    """Lie l'en-tête de section à son premier élément (jamais de titre seul en bas de page)."""
    i = max(k for k, x in enumerate(S) if isinstance(x, CondPageBreak))
    entete = S[i + 1:]
    del S[i + 1:]
    S.append(KeepTogether(entete + [premier]))


def carte(rows, width=W, fond=SURFACE, bord=BORD, pad=PAD, pad_v=None):
    pad_v = PAD if pad_v is None else pad_v
    tb = Table([[r] for r in rows], colWidths=[width])
    tb.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fond), ("ROUNDEDCORNERS", [RAYON] * 4),
        ("BOX", (0, 0), (-1, -1), 0.75, bord),
        ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, 0), pad_v), ("BOTTOMPADDING", (0, -1), (-1, -1), pad_v),
    ]))
    return tb


def filet(espace=S3):
    return HRFlowable(width="100%", thickness=0.6, color=FILET, spaceBefore=espace, spaceAfter=espace)


def puces(items, st=None):
    """Liste à puces avec retrait suspendu : les retours à la ligne s'alignent sur le texte, pas sur la puce."""
    st = st or style("puce", parent=TEXTE_INK, leftIndent=11, bulletIndent=0, spaceAfter=3)
    return [Paragraph(t(x), st, bulletText="•") for x in items]


def bloc_label(label, contenu, st=TEXTE_INK, gap=S1):
    """Étiquette + texte : l'étiquette annonce, le texte porte l'information."""
    corps = contenu if not isinstance(contenu, str) else Paragraph(contenu, st)
    return [Paragraph(label, ETIQUETTE), Spacer(1, gap), corps]


def carte_numerotee(num, rows, fond_pastille=INK, **kw):
    """Carte avec pastille alignée sur la première ligne du titre ; le contenu garde sa propre colonne."""
    larg_contenu = W - 2 * PAD - 34
    inner = Table([[pastille(str(num), fond=fond_pastille, couleur=colors.white, taille=22, corps=10), rows]],
                  colWidths=[34, larg_contenu])
    sans_marges(inner, ("TOPPADDING", (0, 0), (0, 0), -1))
    return carte([inner], **kw)


def deux_colonnes(gauche, droite, gouttiere=S6):
    larg = (W - 2 * PAD - 34 - gouttiere) / 2
    tb = Table([[gauche, droite]], colWidths=[larg + gouttiere, larg])
    return sans_marges(tb, ("RIGHTPADDING", (0, 0), (0, -1), gouttiere))


def tableau(rows, widths, centrer=()):
    tb = Table(rows, colWidths=widths, repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, -1), SURFACE), ("ROUNDEDCORNERS", [RAYON] * 4),
          ("BOX", (0, 0), (-1, -1), 0.75, BORD),
          ("LINEBELOW", (0, 0), (-1, 0), 0.75, BORD),
          ("LINEBELOW", (0, 1), (-1, -2), 0.5, FILET),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, 0), S3), ("BOTTOMPADDING", (0, 0), (-1, 0), S2),
          ("TOPPADDING", (0, 1), (-1, -1), S2), ("BOTTOMPADDING", (0, 1), (-1, -1), S2),
          ("LEFTPADDING", (0, 0), (0, -1), S4), ("LEFTPADDING", (1, 0), (-1, -1), S2),
          ("RIGHTPADDING", (0, 0), (-1, -1), S2), ("RIGHTPADDING", (-1, 0), (-1, -1), S4)]
    st += [("ALIGN", (c, 0), (c, -1), "CENTER") for c in centrer]
    tb.setStyle(TableStyle(st))
    return tb


def th(*labels, centrer=()):
    return [Paragraph(t(x), style(f"th{i}", parent=TH, alignment=TA_CENTER if i in centrer else 0))
            for i, x in enumerate(labels)]


def td(s, st=TD):
    return Paragraph(s if s.startswith("<link") or s.startswith("<font") else t(s), st)


def tdc(s):
    return Paragraph(t(s), style("tdc", parent=TD, alignment=TA_CENTER))


# ---- Couverture -------------------------------------------------------------------------------
def couverture(st):
    T = st["totaux"]
    actifs = sum(1 for q in st["par_compte"].values() if q["posts"] > 0)
    nb_comptes = len(st["par_compte"])
    tr = f"{T['transcrites']}/{T['videos_transcriptibles']}" if T["videos_transcriptibles"] else "-"
    fiab = st["fiabilite"].capitalize()
    fiab_c = VERT if st["fiabilite"] == "élevée" else CORAIL
    tuiles = [(str(T["posts"]), "publications analysées", INK), (f"{actifs}/{nb_comptes}", "comptes actifs", INK),
              (tr, "Reels avec voix transcrits", INK), (fiab, "fiabilité de la collecte", fiab_c)]
    gap = S3
    w = (W - 3 * gap) / 4
    cellules = [carte([Paragraph(f'<font color="{HEX(c)}">{t(n)}</font>', NUM_N), Spacer(1, S1), Paragraph(t(l), NUM_L)],
                      width=w, pad=S2, pad_v=S4) for n, l, c in tuiles]
    rang = sans_marges(Table([cellules], colWidths=[w + gap] * 3 + [w]))
    genere = datetime.now(TZ).strftime("%d/%m/%Y à %H:%M")
    chapeau = (f"Ta veille sur {nb_comptes} comptes Instagram : {v(str(T['posts']) + ' publications')} analysées, "
               f"{v(str(actifs) + ' comptes actifs')} cette semaine.")
    meta = style("meta", fontSize=8, leading=12, textColor=MUTED, alignment=TA_CENTER)
    return [Spacer(1, S6), etiquette_pilule("VEILLE INSTAGRAM HEBDOMADAIRE"), Spacer(1, S4),
            centre(Paragraph(t(titre_semaine(st["periode"]["debut"], st["periode"]["fin"])), DISPLAY), largeur=0.86 * W),
            Spacer(1, S3), centre(chapeau), Spacer(1, S2),
            Paragraph(t(f"Préparée pour Ivan Ouedraogo · générée le {genere}"), meta),
            Spacer(1, S8), rang]


# ---- Document ---------------------------------------------------------------------------------
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
        S += [carte([Paragraph(gras(t(test_banner), CORAIL), TEXTE)], fond=CORAIL_PALE, bord=CORAIL, pad_v=S3), Spacer(1, S2)]
    S += couverture(st)

    if st["statut"] == "partielle":
        S += [Spacer(1, S4), carte(bloc_label('<font color="%s">DONNÉES MANQUANTES ET LIMITES DE LA SEMAINE</font>' % HEX(CORAIL),
                                              "<br/>".join("• " + t(r) for r in st["raisons"])),
                                   fond=CORAIL_PALE, bord=CORAIL)]

    # 1. Résumé exécutif ----------------------------------------------------------------------
    S += entete_section(1, "Résumé exécutif", "L'essentiel de la semaine en " + v("trois phrases") + ".")
    colle(S, carte([Paragraph(t(a["resume_executif"]), LEAD)], pad=S6, pad_v=S6))

    # 2. Tendances -----------------------------------------------------------------------------
    nb = len(a.get("tendances") or [])
    S += entete_section(2, "Grandes tendances", f"Les {v(f'{nb} sujets')} qui ont structuré la semaine, et les comptes qui les portent.",
                       nouvelle_page=True)
    if a.get("note_volume"):
        S += [centre(t(f"Note : {a['note_volume']}"), st=style("nv", parent=DETAIL, alignment=TA_CENTER)), Spacer(1, S3)]
    for i, x in enumerate(a.get("tendances") or [], 1):
        ps = [known[s] for s in x.get("sources") or [] if s in known]
        rows = [Paragraph(t(x["titre"]), H_CARTE), Spacer(1, S1),
                Paragraph("&nbsp;&nbsp;·&nbsp;&nbsp;".join(t("@" + c.lstrip("@")) for c in x.get("comptes") or []), COMPTES),
                Spacer(1, S1), Paragraph(t(x.get("sujet") or ""), DETAIL),
                Spacer(1, S3), Paragraph("IDÉES FORTES", ETIQUETTE), Spacer(1, S1)] + puces(x.get("idees") or []) + [
                filet(S3),
                deux_colonnes(bloc_label("POURQUOI C'EST IMPORTANT", t(x.get("pourquoi") or ND), st=TEXTE),
                              bloc_label("CE QU'IL FAUT SURVEILLER", t(x.get("a_surveiller") or ND), st=TEXTE)),
                filet(S3),
                Paragraph(f"{len(ps)} publication(s)  ·  " + stats(ps), DETAIL), Spacer(1, S1),
                Paragraph("Sources  " + sources(x.get("sources"), known), DETAIL)]
        bloc_ = carte_numerotee(i, rows)
        colle(S, bloc_) if i == 1 else S.append(KeepTogether(bloc_))
        S.append(Spacer(1, S3))

    # 3. Insights ------------------------------------------------------------------------------
    S += entete_section(3, "Insights actionnables", "Trois signaux concrets, et " + v("ce que tu peux en faire") + " dès cette semaine.",
                       nouvelle_page=True)
    for i, x in enumerate(a.get("insights") or [], 1):
        action = carte([Paragraph(gras(t(x.get("action") or ND), VIOLET), TEXTE_INK)],
                       width=W - 2 * PAD - 34, fond=VIOLET_PALE, bord=VIOLET_PALE, pad=S3, pad_v=S2 + 2)
        rows = [Paragraph(t(x.get("signal")), H_CARTE), Spacer(1, S3)] + \
            bloc_label("POURQUOI C'EST INTÉRESSANT", t(x.get("pourquoi") or ND), st=TEXTE) + [Spacer(1, S3)] + \
            bloc_label("ACTION CONCRÈTE", action) + [Spacer(1, S3)] + \
            bloc_label("EXEMPLE D'APPLICATION", t(x.get("exemple") or ND), st=TEXTE) + \
            [filet(S3), Paragraph("Sources  " + sources(x.get("sources"), known), DETAIL)]
        bloc_ = carte_numerotee(i, rows, fond_pastille=VIOLET)
        colle(S, bloc_) if i == 1 else S.append(KeepTogether(bloc_))
        S.append(Spacer(1, S3))

    # 4. Ressources ----------------------------------------------------------------------------
    S += entete_section(4, "Outils et ressources", "Uniquement ce qui est " + v("réellement cité") + " dans les publications, avec la phrase exacte.",
                       nouvelle_page=False)
    res = a.get("ressources") or []
    if res:
        rows = [th("NOM", "TYPE", "MENTION EXACTE", "SOURCE")]
        for r in res:
            p = known[r["source"]]
            rows.append([td(gras(t(r["nom"]))), Paragraph(t(r.get("categorie") or ""), style("cat", parent=TD_MUTED, textColor=VIOLET)),
                         Paragraph("« " + t(r["citation"]) + " »", style("cit", parent=TD, textColor=BODY)),
                         td(link(p["url"], "@" + p["compte"]))])
        S.append(tableau(rows, [3.5 * cm, 2.3 * cm, 8.0 * cm, W - 13.8 * cm]))  # peut se poursuivre page suivante
    else:
        colle(S, centre("Aucun outil, prompt ou workflow explicitement mentionné cette semaine."))

    # 5. Signaux émergents --------------------------------------------------------------------
    S += entete_section(5, "Signaux émergents", "Les sujets " + v("récents ou en croissance") + " à garder à l'œil.")
    sig = a.get("signaux_emergents") or []
    for i, x in enumerate(sig, 1):
        rows = [Paragraph(t(x["signal"]), style("hs", parent=H_CARTE, fontSize=11, leading=15)), Spacer(1, S1),
                Paragraph(t(x.get("description")), TEXTE), Spacer(1, S2),
                Paragraph(sources(x.get("sources"), known), DETAIL)]
        bloc_ = carte_numerotee(i, rows, pad_v=S4)
        colle(S, bloc_) if i == 1 else S.append(KeepTogether(bloc_))
        S.append(Spacer(1, S2))
    if not sig:
        colle(S, centre("Aucun signal émergent identifiable avec les données de la semaine."))

    # 6. Vigilance ------------------------------------------------------------------------------
    S += entete_section(6, "Points de vigilance", "Promesses exagérées, affirmations non vérifiées et " + v("contenus sponsorisés") + ".",
                       nouvelle_page=True)
    for k, x in enumerate(a.get("vigilance") or []):
        p = known[x["source"]]
        citation = sans_marges(Table([[Paragraph("« " + t(x["citation"]) + " »", style("q", parent=TEXTE_INK, fontName="PJS-Medium"))]],
                                     colWidths=[W - 2 * PAD - S3]),
                               ("LINEBEFORE", (0, 0), (0, -1), 2, CORAIL), ("LEFTPADDING", (0, 0), (-1, -1), S3))
        tete = sans_marges(Table([[Paragraph(t(x["affirmation"]), style("va", parent=H_CARTE, fontSize=11, leading=15)),
                                   Paragraph(link(p["url"], "@" + p["compte"]), style("vr", parent=DETAIL, alignment=2))]],
                                 colWidths=[W - 2 * PAD - 4 * cm, 4 * cm]))
        rows = [tete, Spacer(1, S2), citation, Spacer(1, S2),
                Paragraph(f'<font color="{HEX(CORAIL)}" name="PJS-Medium">→&nbsp;&nbsp;{t(x.get("probleme"))}</font>', TEXTE)]
        bloc_ = carte(rows, pad_v=S4)
        colle(S, bloc_) if k == 0 else S.append(KeepTogether(bloc_))
        S.append(Spacer(1, S2))
    if not a.get("vigilance"):
        colle(S, centre("Aucun point de vigilance relevé."))

    # 7. Top 5 ---------------------------------------------------------------------------------
    S += entete_section(7, "Top 5 à consulter", "Les publications les plus " + v("utiles pour ta veille") + ", pas forcément les plus vues.",
                       nouvelle_page=False)
    for i, x in enumerate(a.get("top5") or [], 1):
        p = known[x["shortcode"]]
        rows = [Paragraph(f'{gras("@" + t(p["compte"]))}&nbsp;&nbsp;<font color="{HEX(MUTED)}">{t(p["type"])} · {fmt_date(p["date_utc"])}</font>', TEXTE),
                Spacer(1, S1), Paragraph(t(x.get("raison") or ""), style("rz", parent=LEAD, fontSize=10.5, leading=16)),
                Spacer(1, S2),
                Paragraph(stats([p]) + "&nbsp;&nbsp;&nbsp;&nbsp;" + link(p["url"], "Voir la publication ›"), DETAIL)]
        bloc_ = carte_numerotee(i, rows, fond_pastille=VIOLET, pad_v=S4)
        colle(S, bloc_) if i == 1 else S.append(KeepTogether(bloc_))
        S.append(Spacer(1, S2))

    # 8. Synthèse par compte ------------------------------------------------------------------
    S += entete_section(8, "Synthèse par compte", "Ce que chacun des " + v(f"{len(CONFIG['comptes'])} comptes") + " a apporté cette semaine.",
                       nouvelle_page=True)
    rows = [th("COMPTE", "THÈME DOMINANT", "POST", "DONNÉES", "INTÉRÊT POUR MA VEILLE")]
    for c in CONFIG["comptes"]:
        c = c.lower()
        s = (a.get("synthese_comptes") or {}).get(c, {})
        q = st["par_compte"][c]
        qual = (f"{q['posts']} post(s) · {q['transcrites']}/{q['videos']} transcr." if q["statut"] == "ok"
                else "aucune publication" if q["statut"] == "vide" else f"{q['statut']} : {q['cause'] or ND}")
        pn = s.get("publication_notable")
        theme = s.get("theme") or ND
        rows.append([td(gras("@" + t(c))), Paragraph(t(theme), TD_MUTED if theme == ND else TD),
                     td(link(known[pn]["url"], "Voir ›") if pn in known else "-"), Paragraph(t(qual), TD_MUTED),
                     Paragraph(t(s.get("interet") or ND), TD)])
    S.append(tableau(rows, [3.6 * cm, 4.2 * cm, 1.7 * cm, 3.2 * cm, W - 12.7 * cm]))

    # 9. Qualité des données ------------------------------------------------------------------
    T = st["totaux"]
    S += entete_section(9, "Qualité des données", "Ce qui a été " + v("réellement collecté") + ", compte par compte.")
    centrees = (2, 3, 4, 5, 6)
    rows = [th("COMPTE", "STATUT", "POSTS", "VIDÉOS", "TRANSCR.", "SANS VOIX", "STATS MANQ.", "REMARQUE", centrer=centrees)]
    for c, q in st["par_compte"].items():
        couleur = {"ok": VERT, "vide": MUTED}.get(q["statut"], CORAIL)
        rows.append([td(gras("@" + t(c))), td(gras(t(q["statut"]), couleur)),
                     tdc(str(q["posts"])), tdc(str(q["videos"])), tdc(str(q["transcrites"])),
                     tdc(str(q["sans_voix"])), tdc(str(q["stats_manquantes"])), Paragraph(t(q["cause"] or ""), TD_MUTED)])
    S.append(tableau(rows, [3.6 * cm, 1.7 * cm, 1.5 * cm, 1.7 * cm, 1.8 * cm, 1.8 * cm, 2.1 * cm, W - 14.2 * cm], centrer=centrees))
    inacc = [c for c, q in st["par_compte"].items() if q["statut"] in ("erreur", "privé")]
    resume_q = [("Transcription", f"{T['transcrites']}/{T['videos_transcriptibles']} vidéos avec voix "
                 f"({T['pct_transcription'] if T['pct_transcription'] is not None else '-'} %), {T['videos']} vidéos au total"),
                ("Stats manquantes", f"{T['pct_stats_manquantes'] if T['pct_stats_manquantes'] is not None else '-'} % des posts"),
                ("Inaccessibles", ", ".join("@" + c for c in inacc) or "aucun compte"),
                ("Fiabilité", st["fiabilite"]),
                ("Coût", f"{T['cout_apify_usd']:.2f} $".replace(".", ",") if T.get("cout_apify_usd") is not None else ND)]
    S += [Spacer(1, S3), carte([sans_marges(Table([[Paragraph(t(l).upper(), ETIQUETTE), Paragraph(t(x), TEXTE_INK)]
                                                   for l, x in resume_q], colWidths=[3.4 * cm, W - 2 * PAD - 3.4 * cm]),
                                            ("BOTTOMPADDING", (0, 0), (-1, -2), S2), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"))],
                               pad_v=S4)]

    # 10. Limites et recommandation -----------------------------------------------------------
    reco = carte([Paragraph("RECOMMANDATION PRIORITAIRE", style("rl", parent=ETIQUETTE, textColor=colors.HexColor("#CFC6FF"),
                                                                alignment=TA_CENTER)),
                  Spacer(1, S2),
                  centre(Paragraph(t(a["recommandation"]), style("rc", fontName="PJS-ExtraBold", fontSize=14, leading=21,
                                                               textColor=colors.white, alignment=TA_CENTER)),
                         largeur=W - 2 * S8)],
                 fond=VIOLET, bord=VIOLET, pad=S8, pad_v=S6)
    S += entete_section(10, "Limites et recommandation", "Ce qu'il faut garder en tête, et " + v("une seule action") + " à mener.",
                       nouvelle_page=False)
    colle(S, carte(puces((a.get("limites") or []) + st["raisons"],
                         style("lim", parent=TEXTE, leftIndent=11, bulletIndent=0, spaceAfter=4))))
    S += [Spacer(1, S4), KeepTogether(reco)]

    def decor(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(FOND)
        canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        canvas.setFont("PJS-Regular", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(1.6 * cm, 0.95 * cm, f"Veille Instagram · Ivan Ouedraogo · semaine du {debut} au {fin}")
        canvas.setFont("PJS-Bold", 7.5)
        canvas.drawRightString(A4[0] - 1.6 * cm, 0.95 * cm, f"{doc.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                      topMargin=1.5 * cm, bottomMargin=1.8 * cm, title=f"Veille Instagram {debut}-{fin}",
                      author="Veille automatisée").build(S, onFirstPage=decor, onLaterPages=decor)
    return out_path


if __name__ == "__main__":
    start, end, wdir = resolve_week()
    banner = sys.argv[sys.argv.index("--bandeau") + 1] if "--bandeau" in sys.argv else None
    out = build(wdir, wdir / f"veille-instagram-{start:%Y-%m-%d}.pdf", banner)
    print(out, out.stat().st_size, "octets")
