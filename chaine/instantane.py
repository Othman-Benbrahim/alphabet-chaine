"""L'instantané d'un jeton : les relevés bruts, puis les FAITS DE SÉRIE numérotés [Dn] (skill 0.7.54, §31).

Un fait = champ, valeur, producteur, point d'accès (URL), heure du relevé, emplacement dans la réponse. Les bras A
et C lisent exactement le même texte : seule la lecture alphabet distingue C de A (protocole §3).
"""
from __future__ import annotations

from datetime import datetime, timezone

from .sources import epoch


def _v(x, suffixe: str = "") -> str:
    if x is None:
        return "non fourni par la source"
    if isinstance(x, bool):
        return "oui" if x else "non"
    if isinstance(x, float):
        return f"{x:,.4g}".replace(",", " ") + suffixe
    return f"{x}{suffixe}"


def pool_principal(pools: list[dict]) -> dict | None:
    gardes = [p for p in pools if p.get("reserve_usd") is not None]
    return max(gardes, key=lambda p: p["reserve_usd"]) if gardes else (pools[0] if pools else None)


def age_minutes(cree_le: str | None, heure: str) -> float | None:
    a, b = epoch(cree_le), epoch(heure)
    return None if a is None or b is None else round((b - a) / 60, 1)


def faits(inst: dict) -> list[dict]:
    """Liste ordonnée de faits : {n, producteur, url, releve_le, champ, texte}."""
    sortie: list[dict] = []

    def ajouter(producteur: str, url: str, heure: str, champ: str, texte: str) -> None:
        sortie.append({"n": len(sortie) + 1, "producteur": producteur, "url": url, "releve_le": heure,
                       "champ": champ, "texte": texte})

    po = inst["pools"]
    g, u, h = "GeckoTerminal", po["url"], po["releve_le"]
    ajouter(g, u, h, "data[].attributes.reserve_in_usd",
            f"réserve totale des pools du jeton : {_v(po['reserve_totale_usd'], ' $')} ({po['nb_pools']} pool(s) ; "
            f"plateformes : {', '.join(po['dex']) or 'aucune'} ; encore sur courbe de lancement : {_v(po['sur_courbe'])})")
    p = pool_principal(po["pools"])
    if p:
        ajouter(g, u, h, "data[].attributes.pool_created_at",
                f"pool principal ({p.get('dex')}) créé le {p.get('cree_le')} ; âge au relevé : "
                f"{_v(age_minutes(p.get('cree_le'), h), ' min')}")
        ajouter(g, u, h, "data[].attributes.fdv_usd",
                f"valorisation totale diluée : {_v(p.get('fdv_usd'), ' $')} ; prix : {_v(p.get('prix_usd'), ' $')}")
        for fen, nom in (("m5", "les 5 dernières minutes"), ("m15", "les 15 dernières minutes"),
                         ("m30", "les 30 dernières minutes"), ("h1", "la dernière heure"), ("h6", "les 6 dernières heures")):
            ajouter(g, u, h, f"data[].attributes.transactions.{fen}",
                    f"sur {nom} : {_v(p.get(f'buys_{fen}'))} achats par {_v(p.get(f'buyers_{fen}'))} acheteurs, "
                    f"{_v(p.get(f'sells_{fen}'))} ventes par {_v(p.get(f'sellers_{fen}'))} vendeurs ; volume "
                    f"{_v(p.get(f'volume_{fen}_usd'), ' $')} ; variation du prix {_v(p.get(f'variation_{fen}_pct'), ' %')}")
    bg = inst.get("bougies")
    if bg and bg.get("bougies"):
        serie = " ; ".join(f"{datetime.fromtimestamp(b['t'], timezone.utc):%H:%M} {_v(b['cloture'])} $ / {_v(b['volume_usd'])} $"
                           for b in bg["bougies"])
        ajouter("GeckoTerminal", bg["url"], bg["releve_le"], "data.attributes.ohlcv_list",
                f"série des bougies de 5 minutes du pool principal, de la plus ancienne à la plus récente "
                f"({len(bg['bougies'])} mesures ; heure UTC, prix de clôture / volume) : {serie}")
    rc = inst["rugcheck"]
    r, g, u, h = rc["resume"], "RugCheck", rc["url"], rc["releve_le"]
    ajouter(g, u, h, "totalHolders", f"nombre de détenteurs : {_v(r['detenteurs_total'])}")
    ajouter(g, u, h, "topHolders[].pct",
            f"les 10 premiers portefeuilles (pools et verrous exclus) détiennent {_v(r['top10_pct_hors_pools'], ' %')} "
            f"de l'offre ; parts une à une (%) : {r['top_parts_pct'] or 'non fournies'} ; dont marqués initiés : "
            f"{_v(r['top_initie'])}")
    if r.get("top20"):
        ajouter(g, u, h, "topHolders[].pct, topHolders[].insider",
                "distribution des 20 premiers portefeuilles (pools et verrous exclus), part de l'offre en % "
                "(* = marqué initié) : " + ", ".join(f"{x['part_pct']}{'*' if x['initie'] else ''}" for x in r["top20"]))
    ajouter(g, u, h, "creatorBalance / token.supply",
            f"part de l'offre encore détenue par le créateur : {_v(r['createur_part_pct'], ' %')} "
            "(creatorBalance / supply, calculé par le banc)")
    ajouter(g, u, h, "mintAuthority, freezeAuthority",
            f"autorité d'émission renoncée : {_v(r['autorite_emission_renoncee'])} ; autorité de gel renoncée : "
            f"{_v(r['autorite_gel_renoncee'])}")
    ajouter(g, u, h, "insiderNetworks[], graphInsidersDetected",
            f"réseaux d'initiés détectés : {_v(r['reseaux_inities'])} ({_v(r['reseaux_inities_comptes'])} comptes "
            f"actifs ; part de l'offre : {_v(r['reseaux_inities_part_pct'], ' %')}) ; initiés détectés par le graphe "
            f"des transferts : {_v(r['inities_detectes_graphe'])}")
    ajouter(g, u, h, "risks[]", f"risques signalés : {', '.join(r['risques']) or 'aucun'}")
    ajouter(g, u, h, "launchpad, creatorTokens",
            f"plateforme de lancement : {_v(r['plateforme'])} ; autres jetons lancés par le créateur : "
            f"{_v(r['jetons_du_createur'])}")
    ajouter(g, u, h, "rugged, totalMarketLiquidity, markets",
            f"marqué « rugged » par la source : {_v(r['marque_rugged'])} ; liquidité de marché selon RugCheck : "
            f"{_v(r['liquidite_marches_usd'], ' $')} sur {_v(r['marches'])} marché(s)")
    return sortie


EN_TETE = ("RELEVÉS DE DONNÉES (banc sans texte). Il n'y a ni article ni résultat de recherche : les seuls faits sont "
           "les relevés [Dn] ci-dessous, chacun daté et sourcé (producteur, URL, champ). Ce sont des faits au sens de la "
           "règle d'ancrage (faits de série). Une série de bougies est une suite de mesures datées d'une même grandeur ; "
           "une distribution de portefeuilles décrit des positions et leurs parts ; des fenêtres de transactions de "
           "5 minutes à 6 heures décrivent l'évolution de l'activité. Cite les relevés par leur numéro [Dn].")


def texte_faits(liste: list[dict]) -> str:
    return EN_TETE + "\n\n" + "\n".join(f"[D{x['n']}] {x['texte']} — source : {x['producteur']}, {x['url']} (champ {x['champ']}), "
                     f"relevé le {x['releve_le']}" for x in liste)
