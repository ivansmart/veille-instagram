#!/usr/bin/env bash
# Collecte + transcription + statut + e-mail préparé. L'analyse et l'envoi sont faits par la session Claude (voir ANALYSE.md).
# Codes de sortie : 0 = données prêtes pour l'analyse ; 3 = collecte échouée (email.json = alerte, à envoyer tel quel).
set -uo pipefail
cd "$(dirname "$0")"
ARGS=("$@")
pip install -q -r requirements.txt >/dev/null 2>&1 || echo "AVERT: installation des dépendances incomplète" >&2
python3 collect.py "${ARGS[@]}"; rc=$?
[ $rc -eq 0 ] && { python3 transcribe.py "${ARGS[@]}" || echo "AVERT: transcription en échec, mode dégradé (légendes seules)" >&2; }
python3 status.py "${ARGS[@]}" || exit 1
STATUT=$(python3 -c "import sys;from common import resolve_week,load;s,e,w=resolve_week(sys.argv[1:]);print(load(w/'status.json')['statut'])" "${ARGS[@]}")
if [ "$STATUT" = "echouee" ]; then
  python3 alert.py "${ARGS[@]}"
  exit 3
fi
echo "STATUT=$STATUT : données prêtes, rédiger analysis.json (ANALYSE.md)"
