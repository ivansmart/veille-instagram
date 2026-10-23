#!/usr/bin/env bash
# Collecte + transcription + statut + e-mail préparé. L'analyse et l'envoi sont faits par la session Claude (voir ANALYSE.md).
# Codes de sortie : 0 = données prêtes pour l'analyse ; 3 = collecte échouée (email.json = alerte, à envoyer tel quel).
set -uo pipefail
cd "$(dirname "$0")"
ARGS=("$@")
python3 -m pip install -q -r requirements.txt 2>&1 | tail -3
python3 -c "import requests, yaml, reportlab, numpy" || { echo "ERREUR: dépendances Python manquantes après installation" >&2; exit 1; }
python3 collect.py "${ARGS[@]}"; rc=$?
[ $rc -eq 0 ] && { python3 transcribe.py "${ARGS[@]}" || echo "AVERT: transcription en échec, mode dégradé (légendes seules)" >&2; }
python3 status.py "${ARGS[@]}" || exit 1
STATUT=$(python3 -c "import sys;from common import resolve_week,load;s,e,w=resolve_week(sys.argv[1:]);print(load(w/'status.json')['statut'])" "${ARGS[@]}")
if [ "$STATUT" = "echouee" ]; then
  python3 alert.py "${ARGS[@]}"
  exit 3
fi
echo "STATUT=$STATUT : données prêtes, rédiger analysis.json (ANALYSE.md)"
