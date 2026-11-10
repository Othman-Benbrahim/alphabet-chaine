# alphabet-chaine

Banc d'essai de l'**alphabet situationnel** lu **sans texte** : des jetons de la chaîne Solana, lus dans leurs seuls
relevés de données (GeckoTerminal, RugCheck), avec des questions à 24 h scellées avant leur issue. Aucun ordre,
aucun argent, aucune publication : on mesure une prévision. Protocole : [`PROTOCOLE.md`](PROTOCOLE.md).

## Ce que fait un passage

1. relève les issues des questions échues (`registre/issues.jsonl`) ;
2. garnit le vivier des jetons nouveaux (`registre/vivier.jsonl`) ;
3. relève, dans un ordre tiré au hasard, les jetons de 15 min à 4 h jusqu'à 3 jetons actifs (20 détenteurs, 10
   transactions sur 1 h), avec leur série de bougies et la distribution des détenteurs (`registre/instantanes/`) ;
4. pour chaque question (R, et G si le jeton est sur sa courbe) : bras B (compté), A (modèle seul), C (alphabet),
   scellés dans `registre/previsions.jsonl` ;
5. récrit `registre/score.json`.

Le bras C est le pipeline du **bot Metaculus** (`Othman-Benbrahim/metac-bot-template`, 0.9.7 et suivantes) et le
skill qu'il embarque : le banc ne réécrit ni la lecture ni le moteur ; il fournit les faits et le taux de base.

## Lancer

Onglet **Actions** → **Passage du banc** → **Run workflow**. Au premier passage, mettre `attendre` à `oui` : le
vivier est vide, le passage attend 16 minutes que des jetons atteignent l'âge minimal. Les passages horaires
(`schedule` dans `.github/workflows/passage.yaml`) restent désactivés jusqu'à validation d'un premier passage.

Secrets : `FANTASY_API_KEY`, `MISTRAL_API_KEY`. Variables : `ALPHABET_API_BASE`, `ALPHABET_LLM`,
`ALPHABET_PETIT_LLM` (mêmes valeurs que le bot) ; facultatif : `CHAINE_BOT_REF` (version du bot, `main` par défaut).

## Tests hors ligne

Depuis un clone du bot, avec son environnement :

```bash
cd metac-bot-template && ALPHABET_BOT=. uv run python -m unittest discover -s ../alphabet-chaine/tests
```

## Licences

MIT, Othman Ben Brahim. Réponses enregistrées et lecture des API adaptées de MemePilot Auto (J. E. Bearivo, MIT) :
voir [`LICENCES-TIERS.md`](LICENCES-TIERS.md).
