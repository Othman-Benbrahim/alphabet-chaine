"""Relevés de la chaîne Solana, en lecture seule, par trois API publiques gratuites et sans clé.

- GeckoTerminal : nouveaux pools, pools d'un jeton (réserve, transactions, variations) — environ 1 requête / 7 s ;
- RugCheck      : rapport de sécurité (détenteurs, autorités, réseaux d'initiés, risques).

Les fonctions de lecture des réponses sont adaptées de MemePilot Auto (J. E. Bearivo, licence MIT, voir
LICENCES-TIERS.md). Règle reprise telle quelle : une donnée qu'aucune source ne fournit reste ABSENTE (None), jamais
0 ni False. Chaque relevé garde son URL et son heure : ce sont la source et la date du fait (skill 0.7.54, §31).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

HOTES: dict[str, tuple[str, float]] = {      # nom → (URL de base, intervalle minimal entre deux requêtes, s)
    "gecko": ("https://api.geckoterminal.com/api/v2", 7.0),
    "rugcheck": ("https://api.rugcheck.xyz/v1", 0.8),
}
MAX_OCTETS = 3_000_000
QUOTE_MINTS = frozenset({
    "So11111111111111111111111111111111111111112",   # SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
})
# Plateformes de lancement à courbe : tant qu'un jeton n'a de pool que sur elles, il n'est pas « gradué ».
COURBES = frozenset({"pump-fun", "meteora-dbc"})


class Absent(Exception):
    """La source répond que l'objet n'existe pas (HTTP 404)."""


class Indisponible(Exception):
    """La source n'a pas répondu utilement (réseau, 429 persistant, 5xx, réponse illisible)."""


def _http_json(url: str, timeout: float) -> Any:
    if not any(url.startswith(base + "/") for base, _ in HOTES.values()):
        raise Indisponible("hôte non autorisé")
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "alphabet-chaine/0.1 (banc de recherche, lecture seule)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — hôtes HTTPS fixes
            corps = r.read(MAX_OCTETS + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise Absent(url) from e
        raise _Statut(e.code) from e
    if len(corps) > MAX_OCTETS:
        raise Indisponible("réponse trop volumineuse")
    return json.loads(corps)


class _Statut(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def maintenant_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Client:
    """Un client par passage : rythme par hôte, un seul réessai après un 429 (pause de 60 s)."""

    def __init__(self, lire: Callable[[str, float], Any] = _http_json, timeout: float = 15.0,
                 dormir: Callable[[float], None] = time.sleep) -> None:
        self._lire, self._timeout, self._dormir = lire, timeout, dormir
        self._dernier = {h: 0.0 for h in HOTES}
        self.appels = {h: 0 for h in HOTES}

    def get(self, hote: str, chemin: str) -> tuple[Any, str, str]:
        """(réponse, URL, heure du relevé en ISO UTC)."""
        base, pas = HOTES[hote]
        url = base + chemin
        for essai in (0, 1):
            attente = pas - (time.monotonic() - self._dernier[hote])
            if attente > 0:
                self._dormir(attente)
            self._dernier[hote] = time.monotonic()
            self.appels[hote] += 1
            try:
                return self._lire(url, self._timeout), url, maintenant_iso()
            except Absent:
                raise
            except _Statut as e:
                if e.code == 429 and essai == 0:
                    self._dormir(60)
                    continue
                raise Indisponible(f"{hote} : HTTP {e.code}") from e
            except (OSError, ValueError, TimeoutError) as e:
                raise Indisponible(f"{hote} : {type(e).__name__}") from e
        raise Indisponible(f"{hote} : 429 persistant")


# --------------------------------------------------------------------------- lecture des réponses

def _f(v: Any) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> int | None:
    f = _f(v)
    return None if f is None else int(f)


def epoch(iso: Any) -> float | None:
    if not isinstance(iso, str):
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def pools_gecko(payload: Any) -> list[dict]:
    """Pools GeckoTerminal (new_pools, ou pools d'un jeton) → lignes neutres, une par pool."""
    if not isinstance(payload, dict):
        return []
    lignes = []
    for p in payload.get("data") or []:
        if not isinstance(p, dict):
            continue
        a = p.get("attributes") or {}
        rel = p.get("relationships") or {}
        base_id = ((rel.get("base_token") or {}).get("data") or {}).get("id") or ""
        mint = base_id.split("_", 1)[1] if "_" in base_id else ""
        chg = a.get("price_change_percentage") or {}
        tx = a.get("transactions") or {}
        vol = a.get("volume_usd") or {}
        ligne = {"mint": mint, "pool": a.get("address"), "nom": a.get("name"),
                 "dex": ((rel.get("dex") or {}).get("data") or {}).get("id"),
                 "cree_le": a.get("pool_created_at"), "reserve_usd": _f(a.get("reserve_in_usd")),
                 "fdv_usd": _f(a.get("fdv_usd")), "capitalisation_usd": _f(a.get("market_cap_usd")),
                 "prix_usd": _f(a.get("base_token_price_usd"))}
        for fen in ("m5", "m15", "m30", "h1", "h6"):
            t = tx.get(fen) or {}
            ligne[f"variation_{fen}_pct"] = _f(chg.get(fen))
            ligne[f"volume_{fen}_usd"] = _f(vol.get(fen))
            for k in ("buys", "sells", "buyers", "sellers"):
                ligne[f"{k}_{fen}"] = _i(t.get(k))
        lignes.append(ligne)
    return lignes


def nouveaux_jetons(payload: Any) -> list[dict]:
    """Nouveaux pools → jetons (hors SOL/USDC/USDT), un par mint, le premier vu."""
    vus, sortie = set(), []
    for r in pools_gecko(payload):
        if not r["mint"] or r["mint"] in QUOTE_MINTS or r["mint"] in vus:
            continue
        vus.add(r["mint"])
        sortie.append(r)
    return sortie


def resume_rugcheck(rapport: dict) -> dict:
    """Champs du rapport RugCheck utiles à la lecture, sans calcul caché : les parts sont celles de la source
    (topHolders[].pct) ou des rapports simples écrits ici (quantité / offre), et la formule est dite."""
    jeton = rapport.get("token") if isinstance(rapport.get("token"), dict) else {}
    offre = _f(jeton.get("supply"))
    exclus = {m.get("pubkey") for m in rapport.get("markets") or [] if isinstance(m, dict)}
    for adr, info in (rapport.get("knownAccounts") or {}).items():
        if isinstance(info, dict) and info.get("type") in ("AMM", "LOCKER"):
            exclus.add(adr)
    detenteurs = [h for h in rapport.get("topHolders") or [] if isinstance(h, dict)]
    gardes = [h for h in detenteurs if h.get("owner") not in exclus and h.get("address") not in exclus]
    top = [round(_f(h.get("pct")) or 0.0, 3) for h in gardes[:10]]
    top20 = [{"part_pct": round(_f(h.get("pct")) or 0.0, 3), "initie": h.get("insider") is True} for h in gardes[:20]]
    reseaux = [n for n in rapport.get("insiderNetworks") or [] if isinstance(n, dict)]
    risques = [r for r in rapport.get("risks") or [] if isinstance(r, dict)]
    createur = _f(rapport.get("creatorBalance"))
    plateforme = rapport.get("launchpad") if isinstance(rapport.get("launchpad"), dict) else {}
    jetons_createur = rapport.get("creatorTokens")
    return {
        "detenteurs_total": _i(rapport.get("totalHolders")),
        "top10_pct_hors_pools": round(sum(top), 3) if gardes else None,
        "top_parts_pct": top,
        "top20": top20,
        "top_initie": sum(1 for h in gardes[:10] if h.get("insider") is True) if gardes else None,
        "createur_part_pct": round(100 * createur / offre, 3) if createur is not None and offre else None,
        "autorite_emission_renoncee": (rapport.get("mintAuthority") is None) if "mintAuthority" in rapport else None,
        "autorite_gel_renoncee": (rapport.get("freezeAuthority") is None) if "freezeAuthority" in rapport else None,
        "reseaux_inities": len(reseaux) if "insiderNetworks" in rapport else None,
        "reseaux_inities_comptes": sum(_i(n.get("activeAccounts")) or 0 for n in reseaux) if reseaux else 0,
        "reseaux_inities_part_pct": (round(100 * sum(_f(n.get("currentHolding")) or 0.0 for n in reseaux) / offre, 3)
                                     if offre and "insiderNetworks" in rapport else None),
        "inities_detectes_graphe": _i(rapport.get("graphInsidersDetected")),
        "risques": [f"{r.get('name')} ({r.get('level')})" for r in risques][:8],
        "marque_rugged": rapport.get("rugged") if isinstance(rapport.get("rugged"), bool) else None,
        "liquidite_marches_usd": _f(rapport.get("totalMarketLiquidity")),
        "marches": len(rapport.get("markets") or []) if "markets" in rapport else None,
        "plateforme": plateforme.get("platform") or rapport.get("deployPlatform"),
        "jetons_du_createur": len(jetons_createur) if isinstance(jetons_createur, list) else None,
    }


def etat_pools(pools: list[dict]) -> dict:
    """Réserve totale et plateformes d'un jeton : ce qui sert à dire R (vidage) et G (graduation)."""
    reserves = [p["reserve_usd"] for p in pools if p.get("reserve_usd") is not None]
    dex = sorted({p["dex"] for p in pools if p.get("dex")})
    return {"reserve_totale_usd": round(sum(reserves), 2) if reserves else (0.0 if not pools else None),
            "dex": dex, "nb_pools": len(pools),
            "sur_courbe": bool(dex) and all(d in COURBES for d in dex),
            "gradue": any(d not in COURBES for d in dex)}


# --------------------------------------------------------------------------- relevés

def releve_nouveaux(client: Client, pages: int = 2) -> list[dict]:
    sortie = []
    for page in range(1, pages + 1):
        data, url, heure = client.get("gecko", f"/networks/solana/new_pools?include=base_token&page={page}")
        for j in nouveaux_jetons(data):
            j.update(vu_le=heure, source_url=url)
            sortie.append(j)
    return sortie


def releve_pools(client: Client, mint: str) -> dict:
    """Pools actuels d'un jeton. Un jeton inconnu (404) ou sans pool rend une réserve nulle : il n'est plus
    échangeable, ce qui compte comme un vidage (protocole §2)."""
    chemin = f"/networks/solana/tokens/{mint}/pools?page=1"
    try:
        data, url, heure = client.get("gecko", chemin)
    except Absent:
        return {"pools": [], "url": HOTES["gecko"][0] + chemin, "releve_le": maintenant_iso(), "absent": True,
                **etat_pools([])}
    pools = [p for p in pools_gecko(data) if p["mint"] == mint]
    return {"pools": pools, "url": url, "releve_le": heure, "absent": False, **etat_pools(pools)}


def bougies(payload: Any) -> list[dict]:
    """OHLCV GeckoTerminal → bougies datées, de la plus ancienne à la plus récente."""
    lignes = (((payload or {}).get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    sortie = []
    for r in lignes:
        if isinstance(r, list) and len(r) >= 6 and _f(r[0]) is not None:
            sortie.append({"t": int(_f(r[0])), "ouverture": _f(r[1]), "haut": _f(r[2]), "bas": _f(r[3]),
                           "cloture": _f(r[4]), "volume_usd": _f(r[5])})
    return sorted(sortie, key=lambda b: b["t"])


def releve_bougies(client: Client, pool: str, limite: int = 48) -> dict:
    """Bougies de 5 minutes du pool principal (au plus 4 h) : une série de mesures datées (prix, volume)."""
    data, url, heure = client.get("gecko", f"/networks/solana/pools/{pool}/ohlcv/minute?aggregate=5&limit={limite}"
                                           "&currency=usd")
    return {"bougies": bougies(data), "url": url, "releve_le": heure}


def releve_rugcheck(client: Client, mint: str) -> dict:
    data, url, heure = client.get("rugcheck", f"/tokens/{mint}/report")
    if not isinstance(data, dict):
        raise Indisponible("rugcheck : rapport illisible")
    return {"resume": resume_rugcheck(data), "url": url, "releve_le": heure}
