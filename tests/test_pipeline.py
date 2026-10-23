"""Test technique sur données FICTIVES (jamais envoyées) : statut, garde-fou, rendu PDF.

Usage : python3 tests/test_pipeline.py <dossier_temporaire>
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import CONFIG, ND, save  # noqa: E402
import render_pdf  # noqa: E402
import status  # noqa: E402
import validate  # noqa: E402

w = Path(sys.argv[1]); w.mkdir(parents=True, exist_ok=True)
C = [c.lower() for c in CONFIG["comptes"]]


def post(sc, compte, typ, legende, likes=100, com=10, vues=None):
    return {"compte": compte, "shortcode": sc, "url": f"https://www.instagram.com/p/{sc}/", "date_utc": "2026-10-12T09:00:00.000Z",
            "type": typ, "legende": legende, "hashtags": [], "mentions": [], "likes": likes, "commentaires": com,
            "vues": vues, "lectures": None, "duree_video_s": 30, "video_url": "x" if typ == "Reel" else None, "source": "scraper-posts"}


posts = [post("FICTIF1", C[0], "Reel", "Workflow n8n + Claude pour trier ses mails", vues=5000),
         post("FICTIF2", C1 := C[1], "Carrousel", "5 prompts pour ChatGPT. Devenez riche en 30 jours garanti", likes=None),
         post("FICTIF3", C[2], "Reel", "Mon agent IA vend à ma place", vues=1200)]
save(w / "posts.json", posts)
save(w / "transcriptions.json", {"FICTIF1": {"statut": "ok", "texte": "aujourd'hui je vous montre make et n8n"},
                                  "FICTIF3": {"statut": "pas_de_voix", "texte": None}})
comptes = {c: {"statut": "vide", "cause": "Aucune publication", "nb_posts": 0} for c in C}
for p in posts:
    comptes[p["compte"]] = {"statut": "ok", "cause": None, "nb_posts": 1}
comptes[C[9]] = {"statut": "erreur", "cause": "Profil non renvoyé par Apify", "nb_posts": 0}
save(w / "comptes.json", comptes)
save(w / "collecte.json", {"debut": "2026-10-10T00:00:00+02:00", "fin": "2026-10-16T23:59:59+02:00", "fatal": None, "runs": [], "cout_total_usd": 0.12})

st = status.compute(w); save(w / "status.json", st)
assert st["statut"] == "partielle", st
print("statut :", st["statut"], st["raisons"])

ok = {
    "resume_executif": "Semaine fictive centrée sur l'automatisation. Deux comptes parlent d'agents. Données de test.",
    "note_volume": "Seulement 3 publications fictives : 2 tendances possibles sans extrapoler.",
    "tendances": [{"titre": "Automatisation des mails", "sujet": "n8n", "comptes": [C[0]], "idees": ["trier ses mails"],
                   "pourquoi": "test", "a_surveiller": "test", "sources": ["FICTIF1"]},
                  {"titre": "Agents vendeurs", "sujet": "agents IA", "comptes": [C[2]], "idees": ["vente"],
                   "pourquoi": "test", "a_surveiller": "test", "sources": ["FICTIF3"]}],
    "insights": [{"signal": "s", "pourquoi": "p", "action": "a", "exemple": "e", "sources": [s]} for s in ("FICTIF1", "FICTIF2", "FICTIF3")],
    "ressources": [{"nom": "n8n", "categorie": "outil", "citation": "Workflow n8n + Claude", "source": "FICTIF1"},
                   {"nom": "make", "categorie": "outil", "citation": "je vous montre make", "source": "FICTIF1"}],
    "signaux_emergents": [{"signal": "Agents qui vendent", "description": "d", "sources": ["FICTIF3"]}],
    "vigilance": [{"affirmation": "Promesse de richesse", "citation": "Devenez riche en 30 jours garanti", "source": "FICTIF2", "probleme": "Promesse non vérifiable"}],
    "top5": [{"shortcode": "FICTIF1", "raison": "workflow concret"}, {"shortcode": "FICTIF3", "raison": "cas d'usage"}],
    "synthese_comptes": {c: {"theme": ND, "publication_notable": None, "interet": ND} for c in C},
    "limites": ["Données fictives"], "recommandation": "Tester n8n sur sa boîte mail.",
}
ok["synthese_comptes"][C[0]] = {"theme": "Automatisation", "publication_notable": "FICTIF1", "interet": "élevé"}
ok["synthese_comptes"][C[1]] = {"theme": "Prompts", "publication_notable": "FICTIF2", "interet": "moyen"}
ok["synthese_comptes"][C[2]] = {"theme": "Agents", "publication_notable": "FICTIF3", "interet": "moyen"}
E, W = validate.check(ok, posts, {"FICTIF1": {"texte": "aujourd'hui je vous montre make et n8n"}})
assert not E, E
print("analyse valide acceptée ; avertissements :", W)

bad = copy.deepcopy(ok)
bad["tendances"][0]["sources"] = ["INVENTE9"]                       # post inexistant
bad["tendances"][1]["pourquoi"] = "Ce reel a fait 12 000 vues"       # chiffre écrit à la main
bad["ressources"][0]["citation"] = "Workflow n8n + GPT-5 agent"      # citation non textuelle
bad["ressources"].append({"nom": "Zapier", "categorie": "outil", "citation": "Workflow n8n", "source": "FICTIF1"})  # outil non mentionné
bad["synthese_comptes"][C[5]] = {"theme": "IA", "publication_notable": None, "interet": "x"}  # compte sans données
bad["insights"] = bad["insights"][:2]                                # pas exactement 3
E, _ = validate.check(bad, posts, {"FICTIF1": {"texte": "aujourd'hui je vous montre make et n8n"}})
for e in E:
    print("  rejet :", e)
attendus = ["INVENTE9", "12 000 vues", "GPT-5", "Zapier", "vincentleserpent", "exactement 3"]
manquants = [a for a in attendus if not any(a in e for e in E)]
assert not manquants, manquants
print(f"analyse piégée : {len(attendus)}/{len(attendus)} inventions rejetées ({len(E)} erreurs au total)")

save(w / "analysis.json", ok); save(w / "validation.json", {"ok": True})
out = render_pdf.build(w, w / "test.pdf", "DONNÉES FICTIVES : TEST TECHNIQUE DU GÉNÉRATEUR, NE PAS UTILISER")
print("PDF :", out, out.stat().st_size, "octets")
