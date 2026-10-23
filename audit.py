"""Audit de faisabilité compte par compte (profil + posts récents), sans rien supposer."""
from datetime import datetime, timezone

from apify_client import ApifyError, run_actor
from common import CONFIG, ROOT, apify_token, save

A = CONFIG["apify"]


def classify(p):
    if p is None:
        return "à exclure", "Profil introuvable ou non renvoyé par le scraper"
    if p.get("private"):
        return "à exclure", "Compte privé : aucune publication accessible sans abonnement"
    posts = p.get("latestPosts") or []
    if not posts:
        return "partielle", "Profil accessible mais aucune publication renvoyée"
    videos = [x for x in posts if x.get("type") == "Video"]
    manques = []
    if any((x.get("likesCount") is None or x.get("likesCount", 0) < 0) for x in posts):
        manques.append("likes masqués sur certains posts")
    if videos and not any(x.get("videoUrl") for x in videos):
        manques.append("URL vidéo absente (transcription impossible)")
    if videos and not any(x.get("videoViewCount") or x.get("videoPlayCount") for x in videos):
        manques.append("vues des vidéos absentes")
    return ("partielle", "; ".join(manques)) if manques else ("fiable", "Aucune limite détectée sur les posts récents")


def main():
    token = apify_token()
    if not token:
        raise SystemExit("APIFY_TOKEN absent : audit impossible")
    comptes = CONFIG["comptes"]
    items, meta = run_actor(A["actor_profils"], {"usernames": comptes}, token, 0.50, 600)
    by_user = {(i.get("username") or "").lower(): i for i in items if i.get("username")}
    rows = []
    for c in comptes:
        p = by_user.get(c.lower())
        reco, raison = classify(p)
        posts = (p or {}).get("latestPosts") or []
        last = max((x.get("timestamp") for x in posts if x.get("timestamp")), default=None)
        rows.append({
            "compte": c, "accessible": p is not None and not (p or {}).get("private"),
            "prive": (p or {}).get("private"), "pro": (p or {}).get("isBusinessAccount"),
            "abonnes": (p or {}).get("followersCount"), "nb_posts_total": (p or {}).get("postsCount"),
            "posts_recents_recuperes": len(posts),
            "videos_recentes": sum(1 for x in posts if x.get("type") == "Video"),
            "videos_avec_url": sum(1 for x in posts if x.get("type") == "Video" and x.get("videoUrl")),
            "dernier_post": last, "recommandation": reco, "raison": raison,
        })
    save(ROOT / "data" / "audit.json", {"date": datetime.now(timezone.utc).isoformat(), "apify": meta, "comptes": rows})
    for r in rows:
        print(f"{r['compte']:<20} {r['recommandation']:<11} posts={r['posts_recents_recuperes']:<3} "
              f"vidéos={r['videos_recentes']}/{r['videos_avec_url']} url  dernier={r['dernier_post']}  {r['raison']}")
    print("coût Apify :", meta["cout_usd"])


if __name__ == "__main__":
    try:
        main()
    except ApifyError as e:
        raise SystemExit(f"Audit échoué : {e}")
