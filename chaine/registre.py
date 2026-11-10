"""Le registre du banc : fichiers JSONL scellés, dans le dépôt. Aucune ligne n'est réécrite ; une issue est une
ligne à part, écrite après l'échéance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

RACINE = Path(os.environ.get("CHAINE_REGISTRE", Path(__file__).resolve().parent.parent / "registre"))


def sceau(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def chemin(nom: str, racine: Path | None = None) -> Path:
    r = Path(racine or RACINE)
    r.mkdir(parents=True, exist_ok=True)
    return r / nom


def lire(nom: str, racine: Path | None = None) -> list[dict]:
    p = chemin(nom, racine)
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def ajouter(nom: str, ligne: dict, racine: Path | None = None, sceller: bool = True) -> dict:
    if sceller:
        ligne = dict(ligne, sceau=sceau({k: v for k, v in ligne.items() if k != "sceau"}))
    with chemin(nom, racine).open("a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    return ligne


def ecrire_json(relatif: str, obj: dict, racine: Path | None = None) -> str:
    p = chemin(relatif, racine)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return sceau(obj)
