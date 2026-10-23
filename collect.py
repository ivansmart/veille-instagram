"""Collecte des publications de la semaine (samedi -> vendredi, heure de Paris) via Apify.

Écrit dans data/<semaine>/ : raw_posts.json, raw_profils.json, posts.json, comptes.json.
Aucune valeur par défaut : un champ absent reste null.
"""
import sys
import time
from datetime import datetime, timezone

from apify_client import ApifyError, run_actor
from common import CONFIG, apify_token, load, log_event, resolve_week, save

A = CONFIG["apify"]


def _num(v):
    # Apify renvoie -1 ou null quand Instagram masque un compteur
    return v if isinstance(v, (int, float)) and v >= 0 else None


def _type(it):
    if it.get("productType") == "clips":
        return "Reel"
    return {"Video": "Vidéo", "Sidecar": "Carrousel", "Image": "Image"}.get(it.get("type"), it.get("type"))


def account_of(it):
    """Compte surveillé d'où vient l'élément (une collab peut avoir un autre propriétaire)."""
    u = (it.get("inputUrl") or "").rstrip("/").split("/")[-1].lower()
    return u or (it.get("ownerUsername") or "").lower() or None


def normalize(it, source, compte=None):
    owner = (it.get("ownerUsername") or "").lower() or None
    compte = compte or account_of(it)
    return {
        "compte": compte,
        "auteur": owner or compte,
        "collab": bool(owner and owner != compte),
        "shortcode": it.get("shortCode"),
        "url": it.get("url") or (f"https://www.instagram.com/p/{it['shortCode']}/" if it.get("shortCode") else None),
        "date_utc": it.get("timestamp"),
        "type": _type(it),
        "legende": it.get("caption"),
        "hashtags": it.get("hashtags") or [],
        "mentions": it.get("mentions") or [],
        "likes": _num(it.get("likesCount")),
        "commentaires": _num(it.get("commentsCount")),
        "vues": _num(it.get("videoViewCount")),
        "lectures": _num(it.get("videoPlayCount")),
        "duree_video_s": _num(it.get("videoDuration")),
        "video_url": it.get("videoUrl"),
        "audio_url": it.get("audioUrl"),  # Instagram sert parfois la vidéo sans piste audio
        "source": source,
    }


def in_window(p, start, end):
    if not p["date_utc"]:
        return False
    t = datetime.fromisoformat(p["date_utc"].replace("Z", "+00:00"))
    return start <= t <= end


def run_with_retry(actor, run_input, token, wdir, etape):
    last = None
    for n in range(1, A["tentatives"] + 1):
        try:
            items, meta = run_actor(actor, run_input, token, A["max_usd_par_run"], A["timeout_run_s"])
            log_event(wdir, etape, "info", f"{actor} OK (tentative {n}) : {len(items)} éléments", **meta)
            return items, meta
        except ApifyError as e:
            last = e
            log_event(wdir, etape, "erreur", f"tentative {n} : {e}")
            if "401" in str(e) or "402" in str(e):
                break  # inutile de réessayer
            if n < A["tentatives"]:
                time.sleep(A["pause_entre_tentatives_s"])
    raise last


def main():
    start, end, wdir = resolve_week()
    if "--depuis-brut" in sys.argv:  # retraitement sans nouvel appel Apify
        coll = load(wdir / "collecte.json", {})
        return process(start, end, wdir, load(wdir / "raw_profils.json", []), load(wdir / "raw_posts.json", []),
                       coll.get("runs", []), coll.get("fatal"))
    comptes = [c.lower() for c in CONFIG["comptes"]]
    token = apify_token()
    if not token:
        log_event(wdir, "collecte", "fatal", "APIFY_TOKEN absent de l'environnement")
        save(wdir / "comptes.json", {c: {"statut": "erreur", "cause": "APIFY_TOKEN absent de l'environnement", "nb_posts": 0} for c in comptes})
        save(wdir / "posts.json", [])
        save(wdir / "collecte.json", {"debut": start.isoformat(), "fin": end.isoformat(), "fatal": "APIFY_TOKEN absent", "runs": []})
        raise SystemExit(2)

    runs, fatal = [], None
    # 1) profils : statut privé/public, derniers posts (sert aussi de filet de secours)
    try:
        profils, meta = run_with_retry(A["actor_profils"], {"usernames": comptes}, token, wdir, "profils")
        runs.append(meta)
    except ApifyError as e:
        profils, fatal = [], f"profils : {e}"
    save(wdir / "raw_profils.json", profils)
    # 2) publications
    try:
        raw, meta = run_with_retry(A["actor_posts"], {
            "directUrls": [f"https://www.instagram.com/{c}/" for c in comptes],
            "resultsType": "posts",
            "resultsLimit": A["max_posts_par_compte"],
            # date UTC de début (samedi 00:00 Paris = vendredi 22:00/23:00 UTC), filtrage fin ensuite
            "onlyPostsNewerThan": start.astimezone(timezone.utc).date().isoformat(),
            "addParentData": False,
        }, token, wdir, "posts")
        runs.append(meta)
    except ApifyError as e:
        raw, fatal = [], (fatal + " | " if fatal else "") + f"posts : {e}"
    save(wdir / "raw_posts.json", raw)
    process(start, end, wdir, profils, raw, runs, fatal)


def process(start, end, wdir, profils, raw, runs, fatal):
    comptes = [c.lower() for c in CONFIG["comptes"]]
    erreurs_scraper = {}
    posts = {}
    for it in raw:
        if it.get("error"):
            u = (it.get("url") or it.get("inputUrl") or "").rstrip("/").split("/")[-1].lower()
            erreurs_scraper[u] = f"{it.get('error')} {it.get('errorDescription') or ''}".strip()
            continue
        p = normalize(it, "scraper-posts")
        if p["shortcode"] and p["compte"] in comptes and in_window(p, start, end):
            posts[p["shortcode"]] = p

    by_user = {(p.get("username") or "").lower(): p for p in profils if p.get("username")}
    etat = {}
    for c in comptes:
        prof = by_user.get(c)
        mine = [p for p in posts.values() if p["compte"] == c]
        # filet de secours : posts de la fenêtre vus dans le profil mais absents du scraper de posts
        if prof:
            for lp in prof.get("latestPosts") or []:
                p = normalize(lp, "profil-secours", compte=c)
                if p["shortcode"] and p["shortcode"] not in posts and in_window(p, start, end):
                    posts[p["shortcode"]] = p
                    mine.append(p)
        recents = [lp.get("timestamp") for lp in (prof or {}).get("latestPosts") or [] if lp.get("timestamp")]
        dernier = max(recents, default=None)
        # un post non épinglé antérieur à la semaine dans les 12 derniers prouve que la fenêtre est couverte
        non_epingles = [datetime.fromisoformat(lp["timestamp"].replace("Z", "+00:00"))
                        for lp in (prof or {}).get("latestPosts") or [] if lp.get("timestamp") and not lp.get("isPinned")]
        couverte = any(t < start for t in non_epingles)
        if prof and prof.get("private"):
            etat[c] = {"statut": "privé", "cause": "Compte privé", "nb_posts": 0}
        elif mine:
            src = {p["source"] for p in mine}
            etat[c] = {"statut": "ok", "cause": None if src == {"scraper-posts"} else
                       "Récupéré en partie via le profil (12 derniers posts max), le scraper de posts n'a pas tout renvoyé",
                       "nb_posts": len(mine)}
        elif prof and couverte:
            etat[c] = {"statut": "vide", "cause": f"Aucune publication dans la semaine (dernier post connu : {dernier[:10]})", "nb_posts": 0}
        elif c in erreurs_scraper:
            etat[c] = {"statut": "erreur", "cause": erreurs_scraper[c], "nb_posts": 0}
        elif not prof:
            etat[c] = {"statut": "erreur", "cause": "Profil non renvoyé par Apify (bloqué, renommé ou supprimé ?)", "nb_posts": 0}
        else:
            etat[c] = {"statut": "erreur", "cause": "Aucune publication renvoyée, impossible de confirmer que le compte n'a rien publié", "nb_posts": 0}
        etat[c]["dernier_post_connu"] = dernier

    # le scraper de posts renvoie les lectures (videoPlayCount), le profil les vues (videoViewCount) :
    # deux métriques distinctes, on complète les vues sans jamais les confondre avec les lectures
    vues_profil = {lp.get("shortCode"): _num(lp.get("videoViewCount")) for pr in profils for lp in pr.get("latestPosts") or []}
    for p in posts.values():
        if p["vues"] is None and vues_profil.get(p["shortcode"]) is not None:
            p["vues"] = vues_profil[p["shortcode"]]

    plist = sorted(posts.values(), key=lambda p: p["date_utc"])
    save(wdir / "posts.json", plist)
    save(wdir / "comptes.json", etat)
    save(wdir / "collecte.json", {"debut": start.isoformat(), "fin": end.isoformat(), "fatal": fatal, "runs": runs,
                                  "cout_total_usd": round(sum(r.get("cout_usd") or 0 for r in runs), 4)})
    log_event(wdir, "collecte", "info" if not fatal else "erreur",
              f"{len(plist)} posts dans la fenêtre ; " + ", ".join(f"{c}={v['statut']}" for c, v in etat.items()))
    if fatal and not plist:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
