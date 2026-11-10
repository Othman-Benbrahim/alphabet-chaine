"""Score du banc (protocole §6) : score logarithmique par question, C contre B et C contre A sur les MÊMES questions.

- Les questions en rodage (B fondé sur moins de 30 issues du type) sont comptées à part, jamais dans le critère.
- Pas de C = B : une question sans chiffre C (état nul, refus) n'entre pas dans la comparaison de C ; sa
  fréquence est publiée (couverture).
- Verdict : séquence de confiance du skill (`moteur.sequence_confiance`), appliquée à d = (perte log de C − perte
  log de la référence) / (2 ln 1000), ramené dans [−½, ½] puisque les probabilités sont bornées à 0,001–0,999 ;
  le signe, donc le verdict, ne dépend pas de ce facteur.
"""
from __future__ import annotations

import json
import math

from . import registre

PROTOCOLE = 4     # seules les questions du protocole en vigueur entrent dans le score ; les autres sont comptées à part
CRITERE = 200     # questions résolues par type (protocole §6)
ETAPE = 30        # bilan d'étape, sans conclusion
ECHELLE = 2 * math.log(1000)


def perte(p: float | None, oui: bool) -> float | None:
    if p is None:
        return None
    p = min(0.999, max(0.001, float(p)))
    return -math.log(p if oui else 1 - p)


def _sequence(d: list[float]) -> dict | None:
    try:
        import alphabet_pipeline as ap
        return ap._moteur().sequence_confiance([x / ECHELLE for x in d])
    except Exception as e:
        return {"erreur": f"{type(e).__name__}: {e}"[:200]}


def complements(paires: list[tuple[float, bool]]) -> dict | None:
    """Brier moyen et calibration par tranche de probabilité (0–0,1, …, 0,9–1) : effectif, prévision moyenne,
    fréquence observée."""
    if not paires:
        return None
    brier = sum((p - (1.0 if o else 0.0)) ** 2 for p, o in paires) / len(paires)
    tranches: dict[str, list] = {}
    for p, o in paires:
        k = min(9, int(float(p) * 10))
        tranches.setdefault(f"{k / 10:.1f}–{(k + 1) / 10:.1f}", []).append((p, o))
    return {"n": len(paires), "brier": round(brier, 4),
            "calibration": {k: {"n": len(v), "prevu": round(sum(p for p, _ in v) / len(v), 3),
                                "observe": round(sum(o for _, o in v) / len(v), 3)} for k, v in sorted(tranches.items())}}


def scorer(racine=None) -> dict:
    prev = {p["id"]: p for p in registre.lire("previsions.jsonl", racine)}
    rapport: dict = {"par_type": {}}
    for typ in ("R", "G"):
        lignes = []
        for i in registre.lire("issues.jsonl", racine):
            p = prev.get(i["id"])
            if not p or p["type"] != typ or i.get("issue") not in ("oui", "non"):
                continue
            if p.get("protocole", 1) != PROTOCOLE:
                rapport.setdefault("hors_protocole", {}).setdefault(typ, 0)
                rapport["hors_protocole"][typ] += 1
                continue
            oui = i["issue"] == "oui"
            b = p["bras"]
            lignes.append({"rodage": b["B"].get("rodage", True), "oui": oui,
                           "p": {k: b[k].get("p") for k in ("A", "B", "C")},
                           "C_med": perte((b["C"].get("ombre_causale") or {}).get("p_mediation"), oui),
                           "A": perte(b["A"].get("p"), oui), "B": perte(b["B"].get("p"), oui),
                           "C": perte(b["C"].get("p"), oui), "statut_C": b["C"].get("statut")})
        comptees = [x for x in lignes if not x["rodage"]]
        avec_c = [x for x in comptees if x["C"] is not None]
        t: dict = {"resolues": len(lignes), "rodage": len(lignes) - len(comptees), "comptees": len(comptees),
                   "taux_oui": round(sum(x["oui"] for x in comptees) / len(comptees), 3) if comptees else None,
                   "couverture_C": round(len(avec_c) / len(comptees), 3) if comptees else None,
                   "statuts_C": {}}
        for x in comptees:
            t["statuts_C"][x["statut_C"]] = t["statuts_C"].get(x["statut_C"], 0) + 1
        for bras_ in ("A", "B"):
            vals = [x[bras_] for x in comptees if x[bras_] is not None]
            t[f"perte_{bras_}"] = round(sum(vals) / len(vals), 4) if vals else None
        if avec_c:
            t["perte_C_sur_ses_questions"] = round(sum(x["C"] for x in avec_c) / len(avec_c), 4)
            for ref in ("B", "A"):
                d = [x["C"] - x[ref] for x in avec_c if x[ref] is not None]
                t[f"C_moins_{ref}"] = {"n": len(d), "moyenne": round(sum(d) / len(d), 4) if d else None,
                                       "sequence_confiance": _sequence(d) if d else None}
        # Skill 0.7.56 (§33), en ombre : la règle des médiateurs contre le calcul actuel, sur les mêmes questions.
        med = [x for x in avec_c if x["C_med"] is not None]
        if med:
            d = [x["C_med"] - x["C"] for x in med]
            t["C_mediation_moins_C"] = {"n": len(d), "moyenne": round(sum(d) / len(d), 4),
                                        "sequence_confiance": _sequence(d)}
        # Complément descriptif (Paleka et al., ICLR 2026 : chaque métrique a son défaut ; rapporter log, Brier et
        # calibration ensemble). Le critère du protocole reste la perte log (§5) ; ces chiffres ne le remplacent pas.
        t["complements"] = {k: complements([(x["p"][k], x["oui"]) for x in comptees if x["p"][k] is not None])
                            for k in ("A", "B", "C")}
        n = len(comptees)
        t["etape"] = ("critère atteint : verdict lisible" if n >= CRITERE else
                      "bilan d'étape : contrôle de fonctionnement, aucune conclusion" if n >= ETAPE else
                      "trop tôt")
        rapport["par_type"][typ] = t
    rapport["lecture"] = ("perte log : plus bas = mieux. C − B < 0 et C − A < 0, verdict « meilleur » des deux "
                          "séquences à 200 questions par type : l'hypothèse tient (protocole §6).")
    return rapport


def ecrire_rapport(racine=None) -> dict:
    r = scorer(racine)
    registre.chemin("score.json", racine).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r
