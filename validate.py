"""Garde-fou anti-invention : vérifie analysis.json contre les données réellement collectées.

Toute référence doit pointer vers un post existant de la semaine, toute citation doit figurer
mot pour mot dans la légende ou la transcription, et aucun chiffre d'engagement n'est autorisé
dans le texte libre (les chiffres sont injectés par le code depuis les données).
"""
import re
import sys
import unicodedata

from common import CONFIG, ND, load, resolve_week, save

METRIC = re.compile(r"\d[\d\s.,]*\s*(?:k|K|M|millions?)?\s*(?:likes?|j['’]aime|vues|views|commentaires?|comments?|"
                    r"abonnés|followers|partages|shares|lectures|%)", re.I)


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("«", '"').replace("»", '"')
    return re.sub(r"\s+", " ", s).strip()


def check(analysis, posts, trans):
    E, W = [], []
    known = {p["shortcode"]: p for p in posts}
    corpus = {sc: norm((p.get("legende") or "") + " \n " + ((trans.get(sc) or {}).get("texte") or ""))
              for sc, p in known.items()}
    comptes = [c.lower() for c in CONFIG["comptes"]]

    def refs(where, sources, required=True):
        if required and not sources:
            E.append(f"{where} : aucune source citée")
        for sc in sources or []:
            if sc not in known:
                E.append(f"{where} : shortcode inconnu ou hors semaine « {sc} »")

    def verbatim(where, citation, sc):
        if sc not in known:
            E.append(f"{where} : source inconnue « {sc} »")
        elif not citation or norm(citation) not in corpus[sc]:
            E.append(f"{where} : citation introuvable mot pour mot dans {sc} : « {(citation or '')[:80]} »")

    def walk_text(obj, where):
        if isinstance(obj, str):
            m = METRIC.search(obj)
            if m:
                E.append(f"{where} : chiffre d'engagement écrit à la main « {m.group(0).strip()} » (interdit, injecté par le code)")
        elif isinstance(obj, list):
            for i, x in enumerate(obj):
                walk_text(x, f"{where}[{i}]")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if k not in ("citation", "sources", "source", "shortcode", "publication_notable"):
                    walk_text(v, f"{where}.{k}")

    a = analysis
    phrases = [x for x in re.split(r"(?<=[.!?])\s+", (a.get("resume_executif") or "").strip()) if x]
    if not phrases:
        E.append("resume_executif vide")
    elif len(phrases) > 3:
        E.append(f"resume_executif : {len(phrases)} phrases (max 3)")

    tend = a.get("tendances") or []
    if len(tend) > 7:
        E.append(f"{len(tend)} tendances (max 7)")
    if len(tend) < 5:
        if not a.get("note_volume"):
            E.append(f"{len(tend)} tendances (< 5) sans justification dans note_volume")
        else:
            W.append(f"{len(tend)} tendances seulement : {a['note_volume']}")
    for i, t in enumerate(tend):
        refs(f"tendances[{i}]", t.get("sources"))
        src_accounts = {known[s]["compte"] for s in t.get("sources") or [] if s in known}
        extra = {c.lower().lstrip("@") for c in t.get("comptes") or []} - src_accounts
        if extra:
            E.append(f"tendances[{i}] : comptes cités sans post source {sorted(extra)}")

    ins = a.get("insights") or []
    if len(posts) >= 3 and len(ins) != 3:
        E.append(f"{len(ins)} insights (exactement 3 exigés)")
    for i, x in enumerate(ins):
        refs(f"insights[{i}]", x.get("sources"))

    for i, r in enumerate(a.get("ressources") or []):
        verbatim(f"ressources[{i}]", r.get("citation"), r.get("source"))
        if r.get("nom") and norm(r["nom"]) not in norm(r.get("citation")):
            E.append(f"ressources[{i}] : le nom « {r['nom']} » n'apparaît pas dans sa citation")
    for i, s in enumerate(a.get("signaux_emergents") or []):
        refs(f"signaux_emergents[{i}]", s.get("sources"))
    for i, v in enumerate(a.get("vigilance") or []):
        verbatim(f"vigilance[{i}]", v.get("citation"), v.get("source"))

    top = a.get("top5") or []
    if len(top) > 5:
        E.append(f"top5 : {len(top)} entrées")
    if len({t.get("shortcode") for t in top}) != len(top):
        E.append("top5 : doublons")
    for i, t in enumerate(top):
        refs(f"top5[{i}]", [t.get("shortcode")])

    syn = a.get("synthese_comptes") or {}
    for c in comptes:
        s = syn.get(c)
        if s is None:
            E.append(f"synthese_comptes : compte manquant {c}")
            continue
        n = sum(1 for p in posts if p["compte"] == c)
        pn = s.get("publication_notable")
        if pn and (pn not in known or known[pn]["compte"] != c):
            E.append(f"synthese_comptes.{c} : publication notable invalide « {pn} »")
        if n == 0 and (s.get("theme") != ND or pn):
            E.append(f"synthese_comptes.{c} : aucune donnée cette semaine, thème doit être « {ND} » et sans publication")

    if not (a.get("recommandation") or "").strip():
        E.append("recommandation manquante")
    walk_text({k: v for k, v in a.items()}, "analysis")
    return E, W


if __name__ == "__main__":
    start, end, wdir = resolve_week()
    analysis = load(wdir / "analysis.json")
    if analysis is None:
        sys.exit("analysis.json absent")
    E, W = check(analysis, load(wdir / "posts.json", []), load(wdir / "transcriptions.json", {}))
    save(wdir / "validation.json", {"ok": not E, "erreurs": E, "avertissements": W})
    for e in E:
        print("ERREUR", e)
    for w in W:
        print("AVERT ", w)
    print("VALIDATION", "OK" if not E else f"KO ({len(E)} erreurs)")
    sys.exit(1 if E else 0)
