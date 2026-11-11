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


ETAPES_ILLISIBLES = (("plan corrigé illisible", "plan_corrige"), ("plan illisible", "plan"),
                     ("lecture illisible", "lecture"), ("correction illisible", "correction"))


def _a_illisible(a: dict) -> bool:
    e = str((a or {}).get("erreur") or "")
    return "JSONDecodeError" in e or "aucun objet JSON" in e


def sorties_illisibles(previsions: list[dict]) -> dict | None:
    """Banc 0.4.6 (bot 0.10.14, d'après LLMMatrix) : part des prévisions dont une sortie de modèle était illisible,
    par modèle principal et par étape (bras A ; plan, lecture, correction du bras C). Comptée à part des états nuls ;
    descriptive, sans issue."""
    if not previsions:
        return None
    par: dict[str, dict] = {}
    for p in previsions:
        b = p.get("bras") or {}
        c = b.get("C") or {}
        mod = str((p.get("modeles") or {}).get("principal") or "non_renseigne")
        d = par.setdefault(mod, {"previsions": 0, "illisibles": 0, "etapes": {}})
        d["previsions"] += 1
        textes = f"{c.get('motif') or ''} || {c.get('derniere_erreur') or ''}"
        etapes = [e for motif, e in ETAPES_ILLISIBLES if motif in textes]
        if "plan_corrige" in etapes and "plan" in etapes:
            etapes.remove("plan")
        if _a_illisible(b.get("A")):
            etapes.append("bras_A")
        for e in etapes:
            d["etapes"][e] = d["etapes"].get(e, 0) + 1
        d["illisibles"] += bool(etapes)
    for d in par.values():
        d["part"] = round(d["illisibles"] / d["previsions"], 4)
    tot = sum(d["previsions"] for d in par.values())
    ill = sum(d["illisibles"] for d in par.values())
    return {"previsions": tot, "illisibles": ill, "part": round(ill / tot, 4), "par_modele": par}


def preselection_ombre(previsions: list[dict]) -> dict | None:
    """Banc 0.4.6 (bot 0.10.15) : recouvrement entre la présélection par plongement et les cartes du planificateur."""
    ps = [((p.get("bras") or {}).get("C") or {}).get("preselection") for p in previsions]
    ps = [y for y in ps if isinstance(y, dict)]
    if not ps:
        return None
    ok = [y for y in ps if y.get("statut") == "calcule" and y.get("recouvrement") is not None]
    moy = lambda v: round(sum(v) / len(v), 4) if v else None
    return {"questions": len(ps), "calculees": len(ok), "indisponibles": len(ps) - len(ok),
            "recouvrement_moyen": moy([y["recouvrement"] for y in ok]),
            "jaccard_moyen": moy([y["jaccard"] for y in ok]),
            "rang_moyen_evenement": moy([y["rang_evenement"] for y in ok if isinstance(y.get("rang_evenement"), int)])}


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
                           "C_nor": perte((b["C"].get("ombre_causale") or {}).get("p_noisy_or"), oui),
                           "C_gen": perte(((b["C"].get("ombre_causale") or {}).get("generatif") or {}).get("p"), oui),
                           "C_lp": perte(((b["C"].get("ombre_causale") or {}).get("lecture_probabiliste") or {}).get("p"), oui),
                           "C_spl": perte(((b["C"].get("ombre_causale") or {}).get("sans_plafond") or {}).get("p"), oui),
                           "C_tmp": perte(next((t_["p"] for t_ in (b["C"].get("ombre_causale") or {}).get("tempere") or []
                                                if t_.get("alpha") == 0.5), None), oui),
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
        # Skill 0.7.59 (§36), en ombre : programme génératif (lecteur bruité, rejets comme preuves) contre C.
        gen = [x for x in avec_c if x["C_gen"] is not None]
        if gen:
            d = [x["C_gen"] - x["C"] for x in gen]
            t["C_generatif_moins_C"] = {"n": len(d), "moyenne": round(sum(d) / len(d), 4),
                                        "sequence_confiance": _sequence(d)}
        # Skill 0.7.60 (§37), en ombre : lecture probabiliste (traducteur → instructions → programme génératif).
        lp = [x for x in avec_c if x["C_lp"] is not None]
        if lp:
            d = [x["C_lp"] - x["C"] for x in lp]
            t["C_lecture_probabiliste_moins_C"] = {"n": len(d), "moyenne": round(sum(d) / len(d), 4),
                                                   "sequence_confiance": _sequence(d)}
        # Skill 0.7.61 (§38), en ombre : le même calcul sans troncature du score.
        spl = [x for x in avec_c if x["C_spl"] is not None]
        if spl:
            d = [x["C_spl"] - x["C"] for x in spl]
            t["C_sans_plafond_moins_C"] = {"n": len(d), "moyenne": round(sum(d) / len(d), 4),
                                           "sequence_confiance": _sequence(d)}
        # Skill 0.7.58 (§35), en ombre : produit des λ à la puissance 0,5 (fixée d'avance) contre C.
        tmp = [x for x in avec_c if x["C_tmp"] is not None]
        if tmp:
            d = [x["C_tmp"] - x["C"] for x in tmp]
            t["C_tempere_moins_C"] = {"n": len(d), "moyenne": round(sum(d) / len(d), 4),
                                      "sequence_confiance": _sequence(d)}
        # Skill 0.7.57 (§34), en ombre : les cartes lues comme des causes (noisy-or) contre le produit.
        nor = [x for x in avec_c if x["C_nor"] is not None]
        if nor:
            d = [x["C_nor"] - x["C"] for x in nor]
            t["C_noisy_or_moins_C"] = {"n": len(d), "moyenne": round(sum(d) / len(d), 4),
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
    courantes = [p for p in prev.values() if p.get("protocole", 1) == PROTOCOLE]
    rapport["sorties_illisibles"] = sorties_illisibles(courantes)      # banc 0.4.6, descriptif
    rapport["preselection_ombre"] = preselection_ombre(courantes)      # banc 0.4.6, descriptif
    rapport["lecture"] = ("perte log : plus bas = mieux. C − B < 0 et C − A < 0, verdict « meilleur » des deux "
                          "séquences à 200 questions par type : l'hypothèse tient (protocole §6).")
    return rapport


def ecrire_rapport(racine=None) -> dict:
    r = scorer(racine)
    registre.chemin("score.json", racine).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r
