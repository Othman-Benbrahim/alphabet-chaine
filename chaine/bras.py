"""Les trois bras du banc (protocole §3), sur la même question et le même instantané.

- B : taux de base du banc, compté par le code sur les questions du même type déjà résolues AVANT le relevé ;
- A : le modèle principal, avec les mêmes faits, sans l'alphabet (témoin) ;
- C : le pipeline du bot Metaculus, inchangé, avec vue fixée (B) et relevés fixés (les faits) : le planificateur
  choisit l'événement de carte, la lecture ancre les cartes (règle §30), le moteur calcule (exploratoire, §29).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

Llm = Callable[[str], Awaitable[str]]

RODAGE = 30           # questions résolues du même type avant que B compte comme « établi » (protocole §6)
SEUIL_VIDAGE = 0.20   # R : réserve totale sous 20 % de celle de l'instantané (protocole §2)
HORIZON_H = 24
PROTOCOLE = 4         # B ne compte que les questions du protocole en vigueur (même population de jetons)


def echeance(releve_le: str) -> str:
    t = datetime.fromisoformat(releve_le.replace("Z", "+00:00")) + timedelta(hours=HORIZON_H)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def enonce(typ: str, symbole: str, mint: str, releve_le: str, reserve: float) -> dict:
    fin = echeance(releve_le)
    if typ == "R":
        titre = (f"La réserve totale des pools du jeton Solana {symbole} ({mint}) tombera-t-elle sous 20 % de sa valeur "
                 f"du {releve_le} ({reserve:,.0f} $) au relevé du {fin} ?").replace(",", " ")
        criteres = ("OUI si, au relevé GeckoTerminal fait à l'échéance (pools du jeton, somme de reserve_in_usd), la "
                    f"réserve totale est inférieure à {SEUIL_VIDAGE:.0%} de la réserve de l'instantané ; un jeton "
                    "devenu inconnu de la source ou sans pool compte comme une réserve nulle. NON sinon.")
    else:
        titre = (f"Le jeton Solana {symbole} ({mint}), encore sur sa courbe de lancement au {releve_le}, aura-t-il un "
                 f"pool sur une plateforme d'échange ouverte au relevé du {fin} ?")
        criteres = ("OUI si, au relevé GeckoTerminal fait à l'échéance, le jeton a au moins un pool sur une plateforme "
                    "autre qu'une courbe de lancement (pump-fun, meteora-dbc) : la graduation a eu lieu. NON sinon.")
    return {"titre": titre, "criteres": criteres, "echeance": fin}


# --------------------------------------------------------------------------- B

def taux_de_base(typ: str, releve_le: str, previsions: list[dict], issues: list[dict]) -> dict:
    """Jeffreys (k + ½)/(n + 1) sur les questions du type dont l'issue a été RELEVÉE avant l'instantané : aucune
    information postérieure au relevé n'entre dans B."""
    par_id = {p["id"]: p for p in previsions}
    k = n = 0
    debut = fin = None
    for i in issues:
        p = par_id.get(i.get("id"))
        if (not p or p.get("type") != typ or p.get("protocole", 1) != PROTOCOLE or i.get("issue") not in ("oui", "non")
                or i["releve_le"] >= releve_le):
            continue
        n += 1
        k += i["issue"] == "oui"
        debut = min(debut or p["releve_le"], p["releve_le"])
        fin = max(fin or i["releve_le"], i["releve_le"])
    f = (k + 0.5) / (n + 1)
    return {"p": f, "k": k, "n": n, "rodage": n < RODAGE, "periode": f"{debut or releve_le} – {fin or releve_le}"}


def vue_fixee(typ: str, b: dict, releve_le: str) -> dict:
    """La vue extérieure passée au pipeline du bot (contrôlée par controle_vue)."""
    libelle = {"R": "vidage (réserve < 20 % en 24 h)", "G": "graduation en 24 h"}[typ]
    return {"frequence": b["p"], "compte_calcule": True,
            "classe_de_reference": f"jetons Solana du banc alphabet-chaine, question « {libelle} », résolus avant le relevé",
            "source": "registre du banc alphabet-chaine (issues relevées sur GeckoTerminal)",
            "periode": b["periode"], "disponible_le": releve_le[:10],
            "calcul": f"(k + 0,5)/(n + 1) avec k = {b['k']} OUI sur n = {b['n']} questions (Jeffreys)",
            "classe_alternative": None,
            "motif_sans_alternative": "classe unique fixée par le protocole du banc (protocole §3)"}


# --------------------------------------------------------------------------- A

def consigne_a(titre: str, criteres: str, faits: str, releve_le: str) -> str:
    return f"""Tu es un prévisionniste. Donne la probabilité que la réponse à la question soit OUI, à partir des seuls
relevés ci-dessous (aucune autre information n'est disponible ; date du relevé : {releve_le}).

QUESTION : {titre}
CRITÈRES : {criteres}

RELEVÉS :
{faits}

Rends UNIQUEMENT un objet JSON : {{"p": nombre entre 0.001 et 0.999, "raison": "deux phrases au plus"}}"""


async def bras_a(llm: Llm, titre: str, criteres: str, faits: str, releve_le: str) -> dict:
    import alphabet_pipeline as ap
    try:
        r = ap.extraire_json(await llm(consigne_a(titre, criteres, faits, releve_le)))
        p = float(r["p"])
        if not 0 < p < 1:
            raise ValueError(f"p hors de ]0, 1[ : {p}")
        return {"p": ap.borner(p), "raison": str(r.get("raison") or "")[:400]}
    except Exception as e:
        return {"p": None, "erreur": f"{type(e).__name__}: {e}"[:300]}


# --------------------------------------------------------------------------- C

async def bras_c(llm: Llm, ident: str, mint: str, titre: str, criteres: str, faits: str, releve_le: str,
                 vue: dict) -> dict:
    import alphabet_pipeline as ap
    from datetime import date

    async def pas_de_recherche(requete: str) -> str:      # le banc ne cherche rien : les faits sont les relevés
        return ""

    q = ap.Question(id=ident, url=f"https://solscan.io/token/{mint}", titre=titre,
                    contexte="Banc « sans texte » : jeton de la chaîne Solana, lu dans ses seuls relevés de données.",
                    criteres=criteres, precisions="Horizon : 24 heures après le relevé.",
                    resolution=date.fromisoformat(echeance(releve_le)[:10]))
    # Protocole 4 : le planificateur voit aussi les équivalents de données (skill 0.7.55, §32), comme la lecture : sans
    # eux, il choisissait des candidates dont les marqueurs de données n'existent pas et omettait celles qui en ont.
    equiv = ap.DOSSIER_SKILL / "references" / "equivalences" / "donnees-chaine.md"
    pour_plan = (equiv.read_text(encoding="utf-8") + "\n\n" if equiv.is_file() else "") + faits
    try:
        c = await ap.alphabet(q, pour_plan, llm, pas_de_recherche, True, releve_le[:10], 1,
                              vue_fixee=vue, donnees_fixees=faits)
    except Exception as e:
        return {"statut": "erreur", "motif": f"{type(e).__name__}: {e}"[:300]}
    ex = c.get("exploratoire") or {}
    p_c = c.get("p_C") if c.get("p_C") is not None else ex.get("p_C")
    plan = c.get("plan") or {}
    sortie = {"statut": ex.get("statut") or c.get("statut"), "p": p_c,
              "motif": (ex.get("motif") or c.get("motif") or "")[:300],
              "evenement": plan.get("evenement"), "candidats": plan.get("candidats"),
              "semantique": plan.get("semantique"), "etat": ex.get("etat") or c.get("etat"),
              "nature_etat_nul": ex.get("nature_etat_nul") or c.get("nature_etat_nul"),
              "p_symetrique": (c.get("symetrique") or {}).get("p"), "drapeaux": ex.get("drapeaux") or c.get("drapeaux"),
              "tentatives": c.get("tentatives"), "reprises_plan": c.get("reprises_plan")}
    d = c.get("dossier")
    if d is not None:
        sortie["dossier"] = {k: v for k, v in d.items() if not str(k).startswith("_")}
    return sortie
