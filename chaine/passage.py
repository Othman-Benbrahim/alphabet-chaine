"""Un passage du banc : relever les issues échues, garnir le vivier, échantillonner, prévoir, sceller.

    python chaine/passage.py [--par-passage 3] [--attendre] [--sans-prevision]

À lancer depuis le dossier du bot Metaculus (son environnement : `uv run`), le dossier du bot étant dans
sys.path (variable ALPHABET_BOT, par défaut ../bot ou le dossier courant).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
BOT = Path(os.environ.get("ALPHABET_BOT", Path.cwd())).resolve()
sys.path.insert(0, str(BOT))
os.environ.setdefault("ALPHABET_EXPLORATOIRE", "1")
os.environ.setdefault("ALPHABET_EQUIV_DONNEES", "1")    # skill 0.7.55, §32

from chaine import bras, instantane, registre, sources  # noqa: E402
from chaine.sources import epoch  # noqa: E402

VERSION = "0.4.3"
PROTOCOLE = bras.PROTOCOLE
AGE_MIN, AGE_MAX = 15, 240          # minutes (protocole §2)
RESERVE_MIN = 1000.0                # $ : éligibilité minimale (décision du 2026-11-10)
DETENTEURS_MIN = 20                 # protocole 2 : un jeton sans activité n'a pas de structure à lire
TRANSACTIONS_H1_MIN = 10
DELAI_ABANDON_H = 48                # une issue impossible à relever 48 h après l'échéance : « non_resolue »
PREFIXE_LECTEUR = os.environ.get("CHAINE_PREFIXE_LECTEUR", "openai/")   # la passerelle Fantasy


def maintenant() -> str:
    return sources.maintenant_iso()


# --------------------------------------------------------------------------- issues

def relever_issues(client: sources.Client, racine=None, heure: str | None = None) -> list[dict]:
    heure = heure or maintenant()
    faites = {i["id"] for i in registre.lire("issues.jsonl", racine)}
    nouvelles = []
    for p in registre.lire("previsions.jsonl", racine):
        if p["id"] in faites or p["echeance"] > heure:
            continue
        try:
            po = sources.releve_pools(client, p["mint"])
        except sources.Indisponible as e:
            if (epoch(heure) or 0) - (epoch(p["echeance"]) or 0) > DELAI_ABANDON_H * 3600:
                nouvelles.append(registre.ajouter("issues.jsonl", {"id": p["id"], "issue": "non_resolue",
                                                                  "motif": str(e), "releve_le": heure}, racine))
            continue
        if p["type"] == "R":
            issue = po["reserve_totale_usd"] is not None and po["reserve_totale_usd"] < bras.SEUIL_VIDAGE * p["reserve_initiale"]
            if po["reserve_totale_usd"] is None:
                continue
        else:
            issue = po["gradue"]
        nouvelles.append(registre.ajouter("issues.jsonl", {
            "id": p["id"], "type": p["type"], "issue": "oui" if issue else "non", "releve_le": po["releve_le"],
            "reserve_finale_usd": po["reserve_totale_usd"], "dex": po["dex"], "absent": po["absent"],
            "source_url": po["url"], "en_retard_h": round(((epoch(po["releve_le"]) or 0) - (epoch(p["echeance"]) or 0)) / 3600, 2)},
            racine))
        faites.add(p["id"])
    return nouvelles


# --------------------------------------------------------------------------- vivier et échantillon

def garnir_vivier(client: sources.Client, racine=None) -> int:
    connus = {v["mint"] for v in registre.lire("vivier.jsonl", racine)}
    n = 0
    for j in sources.releve_nouveaux(client):
        if j["mint"] in connus:
            continue
        connus.add(j["mint"])
        registre.ajouter("vivier.jsonl", {k: j.get(k) for k in ("mint", "pool", "nom", "dex", "cree_le", "vu_le",
                                                                 "reserve_usd", "source_url")}, racine, sceller=False)
        n += 1
    return n


def candidats(racine=None, heure: str | None = None) -> list[dict]:
    heure = heure or maintenant()
    deja = {p["mint"] for p in registre.lire("previsions.jsonl", racine)}
    deja |= {e["mint"] for e in registre.lire("ecartes.jsonl", racine)}
    t = epoch(heure) or time.time()
    sortie = []
    for v in registre.lire("vivier.jsonl", racine):
        c = epoch(v.get("cree_le"))
        if v["mint"] in deja or c is None:
            continue
        if AGE_MIN <= (t - c) / 60 <= AGE_MAX:
            sortie.append(v)
    return sortie


# --------------------------------------------------------------------------- prévision

async def prevoir_jeton(v: dict, client: sources.Client, llm, racine=None, modeles: dict | None = None) -> list[dict]:
    mint = v["mint"]
    try:
        po = sources.releve_pools(client, mint)
        rc = sources.releve_rugcheck(client, mint)
    except (sources.Indisponible, sources.Absent) as e:
        registre.ajouter("ecartes.jsonl", {"mint": mint, "motif": f"relevé impossible : {e}", "le": maintenant()},
                         racine, sceller=False)
        return []
    motif = ecarter(po, rc)
    if motif:
        registre.ajouter("ecartes.jsonl", {"mint": mint, "motif": motif, "le": po["releve_le"]}, racine, sceller=False)
        return []
    principal = instantane.pool_principal(po["pools"])
    try:
        bg = sources.releve_bougies(client, principal["pool"]) if principal and principal.get("pool") else None
    except (sources.Indisponible, sources.Absent):
        bg = None
    releve_le = max(po["releve_le"], rc["releve_le"])
    inst = {"mint": mint, "symbole": (v.get("nom") or mint[:6]).split(" / ")[0], "releve_le": releve_le,
            "pools": po, "rugcheck": rc, "bougies": bg, "vivier": v}
    fs = instantane.faits(inst)
    texte = instantane.texte_faits(fs)
    nom_inst = f"instantanes/{mint}-{releve_le.replace(':', '')}.json"
    sceau_inst = registre.ecrire_json(nom_inst, dict(inst, faits=fs), racine)
    previsions = registre.lire("previsions.jsonl", racine)
    issues = registre.lire("issues.jsonl", racine)
    lignes = []
    for typ in (("R", "G") if po["sur_courbe"] else ("R",)):
        e = bras.enonce(typ, inst["symbole"], mint, releve_le, po["reserve_totale_usd"])
        ident = f"{mint}-{typ}-{releve_le}"
        b = bras.taux_de_base(typ, releve_le, previsions, issues)
        a = await bras.bras_a(llm, e["titre"], e["criteres"], texte, releve_le)
        c = await bras.bras_c(llm, ident, mint, e["titre"], e["criteres"], texte, releve_le,
                              bras.vue_fixee(typ, b, releve_le))
        lignes.append(registre.ajouter("previsions.jsonl", {
            "version_banc": VERSION, "protocole": PROTOCOLE, "id": ident, "mint": mint, "type": typ, "releve_le": releve_le,
            "echeance": e["echeance"], "titre": e["titre"], "reserve_initiale": po["reserve_totale_usd"],
            "sur_courbe": po["sur_courbe"], "instantane": nom_inst, "instantane_sha256": sceau_inst,
            "modeles": modeles, "bras": {"A": a, "B": b, "C": c}}, racine))
    return lignes


def ecarter(po: dict, rc: dict) -> str | None:
    """Éligibilité (protocole 2) : réserve, détenteurs, transactions de la dernière heure sur le pool principal."""
    if (po["reserve_totale_usd"] or 0) < RESERVE_MIN:
        return f"réserve {po['reserve_totale_usd']} < {RESERVE_MIN}"
    d = rc["resume"].get("detenteurs_total")
    if d is None or d < DETENTEURS_MIN:
        return f"détenteurs {d} < {DETENTEURS_MIN}"
    p = instantane.pool_principal(po["pools"]) or {}
    tx = (p.get("buys_h1") or 0) + (p.get("sells_h1") or 0)
    if tx < TRANSACTIONS_H1_MIN:
        return f"transactions sur 1 h {tx} < {TRANSACTIONS_H1_MIN}"
    return None


def lancer_llm():
    """Modèle principal du passage, choisi comme dans le bot (premier de la suite ALPHABET_LLM qui répond)."""
    import alphabet_modeles as am
    from alphabet_bot import configuration
    # Un seul lecteur pour tout le banc : les modèles de la passerelle (préfixe « openai/ »), jamais le secours
    # d'un autre fournisseur (le 2026-11-10, Mistral Large en secours a inventé l'issue comme fait). Si la passerelle
    # est saturée, on l'attend (sondes espacées de 1 à 5 min, environ 15 min au plus) au lieu de changer de lecteur.
    for var in ("ALPHABET_LLM", "ALPHABET_PETIT_LLM"):
        gardes = [m for m in am.suite(os.environ.get(var)) if m.startswith(PREFIXE_LECTEUR)]
        os.environ[var] = ",".join(gardes)
    os.environ.setdefault("ALPHABET_SONDE_TOURS", "6")
    choix, essais = asyncio.run(am.choisir())
    for e_ in essais:
        print(f"{'✅' if e_['json_ok'] else '❌'}  {e_['role']} : {e_['modele']}" + (f" — {e_['erreur']}" if e_['erreur'] else ""))
    if not choix["principal"]:
        return None, choix
    am.appliquer(choix)
    modele = configuration()["default"]

    async def llm(consigne: str) -> str:
        return await modele.invoke(consigne)
    return llm, choix


def main() -> int:
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--par-passage", type=int, default=int(os.environ.get("CHAINE_PAR_PASSAGE") or "3"))
    ap_.add_argument("--attendre", action="store_true", help="vivier vide d'éligibles : attendre 16 min puis échantillonner")
    ap_.add_argument("--sans-prevision", action="store_true")
    args = ap_.parse_args()
    client = sources.Client()
    debut = maintenant()
    passage = {"version_banc": VERSION, "debut": debut, "statut": "lance"}
    try:
        issues = relever_issues(client)
        print(f"📥  issues relevées : {len(issues)}")
        n = garnir_vivier(client)
        print(f"🌱  vivier : {n} jeton(s) nouveau(x)")
        cands = candidats()
        if not cands and args.attendre and not args.sans_prevision:
            print("⏳  aucun jeton de 15 min à 4 h : attente de 16 minutes")
            time.sleep(16 * 60)
            cands = candidats()
        graine = int(time.time())
        # Ordre aléatoire ; on relève les jetons dans cet ordre jusqu'à en avoir `par_passage` éligibles (protocole 2),
        # au plus 10 fois plus de relevés : le tirage reste uniforme parmi les jetons éligibles.
        lot = random.Random(graine).sample(cands, min(10 * args.par_passage, len(cands)))
        print(f"🎲  éligibles par l'âge : {len(cands)} ; ordre tiré (graine {graine}), {len(lot)} relevés au plus")
        prevues: list[dict] = []
        modeles = None
        if lot and not args.sans_prevision:
            llm, modeles = lancer_llm()
            if llm is None:
                print("⏸️  passerelle saturée après ~15 min d'attente : aucune prévision ce passage (issues relevées)")
                passage.update(statut="sans_modele", issues=len(issues), vivier_ajouts=n, eligibles=len(cands))
                return 0

            async def tous() -> list[dict]:
                sortie, retenus = [], 0
                for v in lot:
                    if retenus >= args.par_passage:
                        break
                    lignes = await prevoir_jeton(v, client, llm, modeles=modeles)
                    retenus += bool(lignes)
                    sortie += lignes
                return sortie
            prevues = asyncio.run(tous())
        for p in prevues:
            print(f"🔮  {p['type']} {p['mint'][:8]}… B={p['bras']['B']['p']:.3f} A={p['bras']['A'].get('p')} "
                  f"C={p['bras']['C'].get('p')} ({p['bras']['C'].get('statut')})")
        passage.update(statut="fin", issues=len(issues), vivier_ajouts=n, eligibles=len(cands), tires=len(lot),
                       graine=graine, questions=len(prevues), modeles=modeles, appels=client.appels)
        return 0
    finally:
        passage["fin"] = maintenant()
        registre.ajouter("passages.jsonl", passage)
        from chaine import score
        score.ecrire_rapport()


if __name__ == "__main__":
    sys.exit(main())
