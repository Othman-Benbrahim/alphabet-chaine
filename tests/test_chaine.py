"""Tests hors ligne du banc : relevés simulés à partir des réponses enregistrées par MemePilot Auto (MIT), modèle
simulé. Lancer depuis le dossier du bot :  ALPHABET_BOT=. uv run python -m unittest discover -s ../tests"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
sys.path.insert(0, str(Path(os.environ.get("ALPHABET_BOT", Path.cwd())).resolve()))
os.environ.setdefault("ALPHABET_EXPLORATOIRE", "1")

import alphabet_pipeline as ap  # noqa: E402

from chaine import bras, instantane, passage, registre, score, sources  # noqa: E402

FIX = ICI / "fixtures"
NOUVEAUX = json.loads((FIX / "gecko_new.json").read_text())
RUG = json.loads((FIX / "rugcheck_report.json").read_text())
PREMIER = sources.nouveaux_jetons(NOUVEAUX)[0]
MINT = PREMIER["mint"]


def pools_de(mint: str, reserve_facteur: float = 1.0, graduer: bool = False) -> dict:
    data = copy.deepcopy([p for p in NOUVEAUX["data"]
                          if p["relationships"]["base_token"]["data"]["id"] == f"solana_{mint}"])
    for p in data:
        p["attributes"]["reserve_in_usd"] = str(float(p["attributes"]["reserve_in_usd"]) * reserve_facteur)
        if graduer:
            p["relationships"]["dex"]["data"]["id"] = "pumpswap"
    return {"data": data}


class Lecteur:
    """Remplace l'accès HTTP : URL → réponse enregistrée."""

    def __init__(self, reserve_facteur=1.0, graduer=False, absent=False):
        self.f, self.g, self.absent, self.urls = reserve_facteur, graduer, absent, []

    def __call__(self, url, timeout):
        self.urls.append(url)
        if "/new_pools" in url:
            return NOUVEAUX
        if "/tokens/" in url and url.endswith("/pools?page=1"):
            if self.absent:
                raise sources.Absent(url)
            return pools_de(url.split("/tokens/")[1].split("/")[0], self.f, self.g)
        if "rugcheck" in url:
            return RUG
        raise AssertionError(url)


def client(**k):
    return sources.Client(lire=Lecteur(**k), dormir=lambda s: None)


PLAN = {"strates": [6], "candidats": ["CRO@6", "RES@6", "HIE@6"], "contre_candidate": ["HIE@6"],
        "evenement": {"carte": "SEU", "strate": 6, "type": "apparait"}, "semantique": "au-moins-une-fois",
        "temporalite": "generique", "pourquoi_evenement": "OUI = basculement irréversible", "recherches": []}


def lecture_vide():
    return {"candidats": PLAN["candidats"], "contre_candidate": PLAN["contre_candidate"],
            "rejets_classes": {c: {"categorie": "marqueur_non_rempli", "motif": "aucun marqueur"} for c in PLAN["candidats"]},
            "mots": [], "liaisons": [], "questions": [], "dynamique_observee": "aucune"}


class LlmSimule:
    def __init__(self, reponses):
        self.reponses, self.consignes = list(reponses), []

    async def __call__(self, consigne):
        self.consignes.append(consigne)
        r = self.reponses.pop(0)
        return "```json\n" + json.dumps(r, ensure_ascii=False) + "\n```"


class Tests(unittest.TestCase):
    def setUp(self):
        self.reg = Path(tempfile.mkdtemp(prefix="registre-chaine-"))

    def test_lecture_des_reponses(self):
        self.assertTrue(MINT and MINT not in sources.QUOTE_MINTS)
        r = sources.resume_rugcheck(RUG)
        self.assertEqual(r["detenteurs_total"], 9049)
        self.assertEqual(r["reseaux_inities"], 2)
        self.assertTrue(r["autorite_gel_renoncee"])
        self.assertIsNotNone(r["top10_pct_hors_pools"])
        e = sources.etat_pools(sources.pools_gecko(pools_de(MINT)))
        self.assertTrue(e["sur_courbe"])
        self.assertFalse(e["gradue"])
        self.assertTrue(sources.etat_pools(sources.pools_gecko(pools_de(MINT, graduer=True)))["gradue"])

    def test_faits_cites(self):
        c = client()
        inst = {"mint": MINT, "symbole": "X", "releve_le": "2026-11-01T07:40:00Z",
                "pools": sources.releve_pools(c, MINT), "rugcheck": sources.releve_rugcheck(c, MINT)}
        t = instantane.texte_faits(instantane.faits(inst))
        self.assertIn("[D1] réserve totale", t)
        self.assertIn("https://api.rugcheck.xyz/v1/tokens/", t)
        self.assertIn("relevé le", t)
        self.assertNotIn("None", t)

    def test_taux_de_base_sans_avenir(self):
        prev = [{"id": "a", "type": "R", "releve_le": "2026-11-01T00:00:00Z"},
                {"id": "b", "type": "R", "releve_le": "2026-11-01T01:00:00Z"}]
        iss = [{"id": "a", "issue": "oui", "releve_le": "2026-11-02T00:00:00Z"},
               {"id": "b", "issue": "non", "releve_le": "2026-11-02T05:00:00Z"}]
        b = bras.taux_de_base("R", "2026-11-02T03:00:00Z", prev, iss)   # l'issue de b, relevée après, n'entre pas
        self.assertEqual((b["k"], b["n"]), (1, 1))
        self.assertAlmostEqual(b["p"], 0.75)
        self.assertTrue(b["rodage"])
        self.assertIsNone(ap.controle_vue(bras.vue_fixee("R", b, "2026-11-02T03:00:00Z"), "2026-11-02"))

    def test_passage_complet_hors_ligne(self):
        c = client()
        self.assertGreater(passage.garnir_vivier(c, self.reg), 0)
        cands = passage.candidats(self.reg, heure="2026-11-01T08:00:00Z")    # pools créés vers 07:22 : 38 min
        self.assertIn(MINT, {v["mint"] for v in cands})
        v = next(x for x in cands if x["mint"] == MINT)
        # R et G (jeton sur courbe) : A, puis C (plan + lecture), pour chacune.
        llm = LlmSimule([{"p": 0.3, "raison": "r"}, PLAN, lecture_vide(), {"p": 0.2, "raison": "g"}, PLAN, lecture_vide()])
        lignes = asyncio.run(passage.prevoir_jeton(v, c, llm, self.reg))
        reserve = sources.etat_pools(sources.pools_gecko(pools_de(MINT)))["reserve_totale_usd"]
        if reserve < passage.RESERVE_MIN:
            self.assertEqual(lignes, [])
            self.skipTest("réserve du jeton enregistré sous le seuil d'éligibilité")
        self.assertEqual([x["type"] for x in lignes], ["R", "G"])
        r = lignes[0]
        self.assertEqual(len(r["sceau"]), 64)
        self.assertAlmostEqual(r["bras"]["A"]["p"], 0.3)
        self.assertAlmostEqual(r["bras"]["B"]["p"], 0.5)           # aucune issue encore : Jeffreys 0,5, rodage
        self.assertEqual(r["bras"]["C"]["statut"], "etat_nul")
        self.assertIsNone(r["bras"]["C"]["p"])                     # pas de C = B
        self.assertIn("[D1]", llm.consignes[2])                    # la lecture voit les relevés
        self.assertTrue((self.reg / r["instantane"]).is_file())
        # Issues 24 h plus tard : réserve divisée par 10 (vidage), graduation.
        c2 = client(reserve_facteur=0.1, graduer=True)
        iss = passage.relever_issues(c2, self.reg, heure="2030-01-01T00:00:00Z")
        self.assertEqual({i["type"]: i["issue"] for i in iss}, {"R": "oui", "G": "oui"})
        self.assertEqual(passage.relever_issues(c2, self.reg, heure="2030-01-01T00:00:00Z"), [])   # une seule fois
        s = score.scorer(self.reg)
        self.assertEqual(s["par_type"]["R"]["resolues"], 1)
        self.assertEqual(s["par_type"]["R"]["rodage"], 1)          # rodage : hors critère

    def test_jeton_disparu_compte_comme_vidage(self):
        registre.ajouter("previsions.jsonl", {"id": "x", "mint": MINT, "type": "R", "releve_le": "2026-11-01T00:00:00Z",
                                              "echeance": "2026-11-02T00:00:00Z", "reserve_initiale": 5000.0,
                                              "bras": {"A": {"p": 0.5}, "B": {"p": 0.5, "rodage": True}, "C": {}}},
                         self.reg)
        iss = passage.relever_issues(client(absent=True), self.reg, heure="2026-11-02T01:00:00Z")
        self.assertEqual(iss[0]["issue"], "oui")
        self.assertTrue(iss[0]["absent"])

    def test_score_sequence(self):
        prev, iss = [], []
        for n in range(40):
            oui = n % 4 == 0
            prev.append({"id": str(n), "type": "R", "releve_le": f"2026-11-01T{n % 24:02d}:00:00Z",
                         "bras": {"A": {"p": 0.5}, "B": {"p": 0.25, "rodage": False},
                                  "C": {"p": 0.6 if oui else 0.1, "statut": "estime"}}})
            iss.append({"id": str(n), "issue": "oui" if oui else "non", "releve_le": "2026-11-05T00:00:00Z"})
        for p in prev:
            registre.ajouter("previsions.jsonl", p, self.reg)
        for i in iss:
            registre.ajouter("issues.jsonl", i, self.reg)
        t = score.scorer(self.reg)["par_type"]["R"]
        self.assertEqual(t["comptees"], 40)
        self.assertLess(t["C_moins_B"]["moyenne"], 0)
        self.assertIn("verdict", t["C_moins_B"]["sequence_confiance"])
        self.assertEqual(t["etape"], "bilan d'étape : contrôle de fonctionnement, aucune conclusion")


if __name__ == "__main__":
    unittest.main()
