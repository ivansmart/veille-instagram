"""Client minimal de l'API Apify : lancer un actor, attendre, récupérer le dataset."""
import time

import requests

API = "https://api.apify.com/v2"


class ApifyError(RuntimeError):
    pass


def run_actor(actor: str, run_input: dict, token: str, max_usd: float, timeout_s: int):
    h = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{API}/acts/{actor}/runs", headers=h, json=run_input, timeout=60,
                      params={"timeout": timeout_s, "maxTotalChargeUsd": max_usd})
    if r.status_code == 401:
        raise ApifyError("Jeton Apify refusé (401) : jeton invalide ou révoqué")
    if r.status_code == 402:
        raise ApifyError("Crédit Apify épuisé (402)")
    if not r.ok:
        raise ApifyError(f"Lancement de {actor} refusé : HTTP {r.status_code} {r.text[:300]}")
    run = r.json()["data"]
    deadline = time.time() + timeout_s + 120
    while run["status"] in ("READY", "RUNNING"):
        if time.time() > deadline:
            raise ApifyError(f"{actor} : dépassement du délai ({timeout_s}s)")
        r = requests.get(f"{API}/actor-runs/{run['id']}", headers=h,
                         params={"waitForFinish": 60}, timeout=90)
        r.raise_for_status()
        run = r.json()["data"]
    if run["status"] != "SUCCEEDED":
        raise ApifyError(f"{actor} : run {run['id']} terminé avec le statut {run['status']} "
                         f"({run.get('statusMessage') or 'sans message'})")
    items = requests.get(f"{API}/datasets/{run['defaultDatasetId']}/items", headers=h,
                         params={"clean": "true", "format": "json"}, timeout=120)
    items.raise_for_status()
    meta = {"run_id": run["id"], "actor": actor,
            "cout_usd": run.get("usageTotalUsd"),
            "duree_s": (run.get("stats") or {}).get("runTimeSecs")}
    return items.json(), meta
