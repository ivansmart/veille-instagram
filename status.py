"""Classe la collecte de la semaine : complete | partielle | echouee, avec les métriques de qualité."""
from common import CONFIG, load, resolve_week, save

S = CONFIG["seuils"]


def compute(wdir):
    comptes = load(wdir / "comptes.json", {})
    posts = load(wdir / "posts.json", [])
    trans = load(wdir / "transcriptions.json", {})
    coll = load(wdir / "collecte.json", {})

    par_compte = {}
    for c in CONFIG["comptes"]:
        c = c.lower()
        mine = [p for p in posts if p["compte"] == c]
        vids = [p for p in mine if p["type"] in ("Reel", "Vidéo")]
        par_compte[c] = {
            "statut": comptes.get(c, {}).get("statut", "erreur"),
            "cause": comptes.get(c, {}).get("cause") or ("Non traité" if c not in comptes else None),
            "posts": len(mine),
            "videos": len(vids),
            "transcrites": sum(1 for p in vids if trans.get(p["shortcode"], {}).get("statut") == "ok"),
            "sans_voix": sum(1 for p in vids if trans.get(p["shortcode"], {}).get("statut") == "pas_de_voix"),
            "stats_manquantes": sum(1 for p in mine if p["likes"] is None or p["commentaires"] is None),
            "vues_manquantes": sum(1 for p in vids if p["vues"] is None and p["lectures"] is None),
        }
    n_posts = len(posts)
    n_vids = sum(v["videos"] for v in par_compte.values())
    # les Reels sans voix ne sont pas des échecs : ils sont exclus du dénominateur
    transcriptibles = n_vids - sum(v["sans_voix"] for v in par_compte.values())
    n_tr = sum(v["transcrites"] for v in par_compte.values())
    n_err = sum(1 for v in par_compte.values() if v["statut"] == "erreur")
    n_prive = sum(1 for v in par_compte.values() if v["statut"] == "privé")
    n_stats_m = sum(v["stats_manquantes"] for v in par_compte.values())
    pct_tr = round(100 * n_tr / transcriptibles) if transcriptibles else None
    pct_stats_m = round(100 * n_stats_m / n_posts) if n_posts else None

    raisons = []
    if coll.get("fatal"):
        raisons.append(f"Erreur de collecte : {coll['fatal']}")
    if n_err:
        raisons.append(f"{n_err} compte(s) en erreur")
    if n_prive:
        raisons.append(f"{n_prive} compte(s) privé(s)")
    if pct_stats_m is not None and pct_stats_m > S["partiel_si_stats_manquantes_pct"]:
        raisons.append(f"{pct_stats_m} % des posts sans likes ou commentaires")
    if pct_tr is not None and pct_tr < S["partiel_si_transcription_pct_min"]:
        raisons.append(f"seulement {pct_tr} % des vidéos avec voix transcrites")
    if any(p["source"] == "profil-secours" for p in posts):
        raisons.append("une partie des posts récupérée via le filet de secours (profil)")

    accessibles = sum(1 for v in par_compte.values() if v["statut"] in ("ok", "vide"))
    if accessibles == 0 or n_err >= S["echec_si_comptes_en_erreur_min"] or (coll.get("fatal") and n_posts == 0):
        statut = "echouee"
    elif raisons:
        statut = "partielle"
    else:
        statut = "complete"
    fiab = {"complete": "élevée", "echouee": "faible"}.get(statut, "moyenne" if accessibles >= 7 else "faible")
    return {
        "statut": statut, "fiabilite": fiab, "raisons": raisons,
        "periode": {"debut": coll.get("debut"), "fin": coll.get("fin")},
        "totaux": {"posts": n_posts, "videos": n_vids, "videos_transcriptibles": transcriptibles,
                   "transcrites": n_tr, "pct_transcription": pct_tr, "pct_stats_manquantes": pct_stats_m,
                   "comptes_accessibles": accessibles, "comptes_erreur": n_err, "comptes_prives": n_prive,
                   "cout_apify_usd": coll.get("cout_total_usd")},
        "par_compte": par_compte,
    }


if __name__ == "__main__":
    start, end, wdir = resolve_week()
    st = compute(wdir)
    save(wdir / "status.json", st)
    print(st["statut"], "|", st["fiabilite"], "|", "; ".join(st["raisons"]) or "RAS")
