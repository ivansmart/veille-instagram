"""Utilitaires partagés : configuration, fenêtre hebdomadaire, fichiers de la semaine."""
import json
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
TZ = ZoneInfo(CONFIG["fuseau"])
ND = "Non disponible dans les données"


def week_window(ref: date | None = None):
    """Dernière semaine complète samedi 00:00 -> vendredi 23:59:59 (heure de Paris) avant `ref`."""
    ref = ref or datetime.now(TZ).date()
    # vendredi le plus récent strictement antérieur à ref (ref samedi => la veille)
    delta = (ref.weekday() - 4) % 7 or 7
    friday = ref - timedelta(days=delta)
    saturday = friday - timedelta(days=6)
    start = datetime.combine(saturday, time(0, 0), TZ)
    end = datetime.combine(friday, time(23, 59, 59), TZ)
    return start, end


def week_dir(start: datetime) -> Path:
    d = ROOT / "data" / start.strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_week(argv=None):
    """`--semaine AAAA-MM-JJ` (n'importe quel jour postérieur à la semaine visée) ou semaine écoulée."""
    argv = argv if argv is not None else sys.argv[1:]
    ref = None
    if "--semaine" in argv:
        ref = date.fromisoformat(argv[argv.index("--semaine") + 1])
    start, end = week_window(ref)
    return start, end, week_dir(start)


def load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def log_event(wdir: Path, etape: str, niveau: str, message: str, **extra):
    """Journal append-only : tout ce qui a été tenté, réussi ou échoué."""
    entry = {"ts": datetime.now(TZ).isoformat(timespec="seconds"), "etape": etape,
             "niveau": niveau, "message": message, **extra}
    with open(wdir / "journal.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{etape}] {niveau}: {message}", file=sys.stderr)


def apify_token():
    tok = os.environ.get("APIFY_TOKEN", "").strip()
    return tok or None
