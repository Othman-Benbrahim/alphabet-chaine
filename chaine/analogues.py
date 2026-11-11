"""Bras D, EN OMBRE (banc 0.4.7) : la prévision par trajectoires analogues, sans modèle de langage.

Idée reprise de la prévision par lots (Bayntel, MMTS ; regroupement de trajectoires de Tokotoko et al.) : comparer le
début de trajectoire d'un jeton à ceux des jetons passés dont on connaît l'issue, et prendre la fréquence de l'issue
parmi les plus proches. C'est une référence plus exigeante que B (taux de base du type) : si C ne bat pas D, la lecture
des structures n'apporte rien de plus qu'une comparaison de courbes.

Calcul, sans aucune information postérieure au relevé :
  - candidats : questions du même type et du protocole en vigueur dont l'issue a été RELEVÉE avant l'instantané ;
  - vecteur numérique tiré de l'instantané brut (réserve, âge, valorisation, activité, variations de prix,
    concentration, part du créateur, détenteurs, initiés, risques, pente des bougies) ; chaque composante est
    centrée-réduite sur les candidats, une valeur manquante vaut 0 (la moyenne) ;
  - les k = 10 plus proches (distance euclidienne) ; p = (oui + m·p_B) / (k + m), m = 2 : rétréci vers B quand les
    voisins sont peu nombreux.
D n'entre ni dans C ni dans le critère du protocole ; le rapport compare C à D et D à B.
"""
from __future__ import annotations

import json
import math

from . import registre

K = 10
M = 2.0


def _f(x) -> float | None:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _log(x) -> float | None:
    v = _f(x)
    return None if v is None or v < 0 else math.log1p(v)


def _ratio(a, b) -> float | None:
    a, b = _f(a), _f(b)
    return None if a is None or b is None or a + b == 0 else a / (a + b)


def vecteur(inst: dict) -> list[float | None]:
    from .instantane import age_minutes, pool_principal
    po = inst.get("pools") or {}
    p = pool_principal(po.get("pools") or []) or {}
    r = (inst.get("rugcheck") or {}).get("resume") or {}
    bg = [b for b in ((inst.get("bougies") or {}).get("bougies") or []) if _f(b.get("cloture"))]
    pente = None
    if len(bg) >= 2 and _f(bg[0]["cloture"]) > 0:
        pente = math.log(_f(bg[-1]["cloture"]) / _f(bg[0]["cloture"]))
    return [_log(po.get("reserve_totale_usd")), 1.0 if po.get("sur_courbe") else 0.0,
            _log(age_minutes(p.get("cree_le"), po.get("releve_le") or inst.get("releve_le"))),
            _log(p.get("fdv_usd")),
            _ratio(p.get("buys_h1"), p.get("sells_h1")), _log(p.get("volume_h1_usd")),
            _f(p.get("variation_m5_pct")), _f(p.get("variation_h1_pct")), _f(p.get("variation_h6_pct")),
            _f(r.get("top10_pct_hors_pools")), _f(r.get("createur_part_pct")), _log(r.get("detenteurs_total")),
            _f(r.get("reseaux_inities_part_pct")), float(len(r.get("risques") or [])), pente]


def _instantane(nom: str | None, racine) -> dict | None:
    if not nom:
        return None
    try:
        return json.loads(registre.chemin(nom, racine).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def bras_d(typ: str, inst: dict, releve_le: str, p_b: float, previsions: list[dict], issues: list[dict],
           protocole: int, racine=None) -> dict:
    par_id = {p["id"]: p for p in previsions}
    cands = []
    for i in issues:
        p = par_id.get(i.get("id"))
        if (not p or p.get("type") != typ or p.get("protocole", 1) != protocole or i.get("issue") not in ("oui", "non")
                or i["releve_le"] >= releve_le):
            continue
        x = _instantane(p.get("instantane"), racine)
        if x is not None:
            cands.append((p["id"], vecteur(x), i["issue"] == "oui"))
    if not cands:
        return {"p": p_b, "k": 0, "n": 0, "voisins": [], "motif": "aucun jeton passé résolu : D = B"}
    v0 = vecteur(inst)
    dims = len(v0)
    moy, et = [], []
    for j in range(dims):
        vals = [c[1][j] for c in cands if c[1][j] is not None]
        m_ = sum(vals) / len(vals) if vals else 0.0
        s_ = math.sqrt(sum((v - m_) ** 2 for v in vals) / len(vals)) if len(vals) > 1 else 0.0
        moy.append(m_)
        et.append(s_)
    z = lambda v: [0.0 if v[j] is None or not et[j] else (v[j] - moy[j]) / et[j] for j in range(dims)]
    z0 = z(v0)
    dist = sorted(((math.dist(z0, z(c[1])), c[0], c[2]) for c in cands), key=lambda t: t[0])[:K]
    oui = sum(1 for _, _, o in dist if o)
    p = (oui + M * p_b) / (len(dist) + M)
    return {"p": round(min(0.999, max(0.001, p)), 4), "k": len(dist), "n": len(cands), "oui_parmi_voisins": oui,
            "distance_moyenne": round(sum(d for d, _, _ in dist) / len(dist), 4),
            "voisins": [ident for _, ident, _ in dist]}
