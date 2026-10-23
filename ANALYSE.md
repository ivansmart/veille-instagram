# Procédure de la session hebdomadaire (samedi 07:00, Europe/Paris)

1. `./run_weekly.sh` (ajouter `--semaine AAAA-MM-JJ` pour rejouer une semaine).
   - Code 3 : collecte échouée. `python3 send_email.py` (alerte, sans pièce jointe) ; à défaut, envoyer le contenu de `email.json` via Gmail. Fin.
   - Autre code non nul : envoyer une alerte manuelle avec la sortie d'erreur. Ne jamais produire de PDF.
2. Lire `posts.json`, `transcriptions.json`, `status.json`, puis écrire `analysis.json` (schéma ci-dessous). Règles :
   - Uniquement ce qui est dans les légendes et les transcriptions. Aucune connaissance extérieure présentée comme un fait de la semaine.
   - Chaque élément cite ses `sources` (shortcodes). Les outils et la vigilance portent une `citation` copiée mot pour mot.
   - **Aucun chiffre d'engagement dans le texte** : le PDF les injecte depuis les données.
   - Compte sans post : `theme` = « Non disponible dans les données », `publication_notable` = null.
   - Moins de 5 tendances réelles : n'en pas inventer, expliquer dans `note_volume`.
3. `python3 validate.py` : corriger jusqu'à 0 erreur. Si c'est impossible après 3 essais, retirer les éléments fautifs.
4. `python3 render_pdf.py`, puis `python3 alert.py`, puis `python3 send_email.py --attendre-jusqua 07:00` (API Resend : la pièce jointe est encodée par le code).
   **Ne jamais passer le PDF par le connecteur Gmail** : testé le 23/10/2026, un PDF de 34 Ko devient 46 000 caractères base64 à recopier, ce qui n'est pas fiable.
5. Si `send_email.py` échoue : envoyer via Gmail (`send_message`) un e-mail **texte sans pièce jointe** qui signale l'échec d'envoi et reprend le résumé. Le connecteur Gmail ne sert qu'aux alertes et à ce secours.

## Schéma analysis.json
```json
{
  "resume_executif": "3 phrases max",
  "note_volume": "optionnel, si < 5 tendances",
  "tendances": [{"titre": "", "sujet": "", "comptes": [""], "idees": [""], "pourquoi": "", "a_surveiller": "", "sources": ["shortcode"]}],
  "insights": [{"signal": "", "pourquoi": "", "action": "", "exemple": "", "sources": [""]}],
  "ressources": [{"nom": "", "categorie": "outil|prompt|workflow|ressource", "citation": "mot pour mot", "source": ""}],
  "signaux_emergents": [{"signal": "", "description": "", "sources": [""]}],
  "vigilance": [{"affirmation": "", "citation": "mot pour mot", "source": "", "probleme": ""}],
  "top5": [{"shortcode": "", "raison": ""}],
  "synthese_comptes": {"<compte>": {"theme": "", "publication_notable": "shortcode|null", "interet": ""}},
  "limites": [""],
  "recommandation": "une seule, actionnable"
}
```
