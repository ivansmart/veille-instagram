# Veille Instagram hebdomadaire

Chaîne : `collect.py` (Apify) → `transcribe.py` (faster-whisper local) → `status.py` (complète / partielle / échouée) → analyse Claude (`ANALYSE.md`) → `validate.py` (garde-fou anti-invention) → `render_pdf.py` → `alert.py` → envoi via le connecteur Gmail.

- Prérequis : variable d'environnement `APIFY_TOKEN`.
- Audit des comptes : `python3 audit.py`.
- Semaine écoulée : `./run_weekly.sh` ; rejouer une semaine : `./run_weekly.sh --semaine AAAA-MM-JJ`.
- Test technique (données fictives, jamais envoyées) : `python3 tests/test_pipeline.py /tmp/x`.
- Tout ce qui est tenté est consigné dans `data/<semaine>/journal.jsonl`.

| Symptôme | Cause probable | Correction |
|---|---|---|
| Alerte « APIFY_TOKEN absent » | Jeton non configuré | L'ajouter dans les paramètres de l'environnement |
| Alerte 401 ou 402 | Jeton révoqué ou crédit épuisé | Nouveau jeton ou recharge sur console.apify.com |
| Tous les comptes en erreur | Actor Apify cassé par Instagram | Vérifier l'onglet Issues de apify/instagram-scraper ; relancer plus tard |
| Un compte en erreur chaque semaine | Compte renommé ou supprimé | Vérifier à la main, mettre à jour `config.yaml` |
| Transcriptions à 0 % | URL vidéo expirée ou absente | Vérifier le champ `videoUrl` dans `raw_posts.json` |
