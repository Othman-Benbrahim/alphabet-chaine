# Protocole du banc — l'alphabet sans texte

> Version 4, fixée le 2026-11-10 après trois passages de rodage (questions des versions 1 à 3, scorées à part et
> exclues du taux de base ; aucune issue relevée encore). Version 3 : la lecture reçoit les équivalents de données
> (skill 0.7.55, §32). Version 4 : le planificateur les reçoit aussi ; consigne de lecture du bot 0.9.9 (marqueurs
> alternatifs, ancrage indépendant de l'objet de la question). Toute modification = nouvelle version, scorée à part
> (`version_banc` dans chaque ligne du registre).

## 1. Hypothèse

L'alphabet situationnel est structurel : chaque carte est une structure mathématique. Le bot Metaculus ne la lit
que dans des faits rédigés. **H** : lue directement dans des données structurées (la chaîne Solana), la lecture
alphabet prévoit des événements mieux que le taux de base **et** qu'un modèle qui voit les mêmes données sans
l'alphabet. Le banc prévoit des **événements**, pas des prix, et ne vise aucune rentabilité (aucun ordre, aucun
argent ; voir MemePilot Auto, qui a montré l'imprévisibilité des prix de 5 min à 4 h avec des signaux techniques).

## 2. Questions

Jetons tirés au hasard parmi les jetons vus par GeckoTerminal (`new_pools`), âgés de **15 min à 4 h** au tirage,
réserve totale **≥ 1 000 $** au relevé, rapport RugCheck disponible, et **actifs** : au moins **20 détenteurs** et
**10 transactions** sur la dernière heure du pool principal (version 2 : sur pump.fun, la réserve virtuelle de
départ, environ 2 500 $, laissait passer des jetons sans aucune activité). Pas de préfiltre de sécurité, qui
écarterait les structures risquées (décision du 2026-11-10). Les jetons sont relevés dans un ordre tiré au hasard
jusqu'à 3 jetons éligibles par passage. À **24 h** :

- **R (vidage)** : la réserve totale des pools du jeton (somme de `reserve_in_usd`, GeckoTerminal) est-elle sous
  **20 %** de celle de l'instantané ? Un jeton devenu inconnu de la source ou sans pool compte comme réserve nulle.
- **G (graduation)**, posée seulement si tous les pools du jeton sont sur une courbe de lancement (`pump-fun`,
  `meteora-dbc`) : le jeton a-t-il un pool sur une autre plateforme ?

Issue relevée au premier passage après l'échéance ; une issue impossible à relever 48 h après est « non résolue ».

## 3. Bras

| Bras | Ce qu'il voit | Rôle |
|---|---|---|
| **B** | (k + ½)/(n + 1) sur les questions du même type dont l'issue a été relevée **avant** l'instantané | à battre |
| **A** | modèle principal, **mêmes faits**, sans alphabet | témoin : l'alphabet ajoute-t-il, ou nomme-t-il ? |
| **C** | pipeline du bot Metaculus inchangé : le **planificateur choisit l'événement** de carte (décision du 2026-11-10), lecture des faits (règle §30 du skill), moteur en exploratoire (§29), vue = B | testé |

Les faits sont des **faits de série** (skill 0.7.54, §31) : champ, valeur, producteur, URL, heure du relevé. Version 2 :
les relevés comprennent la **série des bougies de 5 minutes** du pool principal (prix, volume, depuis la création,
au plus 4 h), les **fenêtres de transactions** de 5 min à 6 h et la **distribution des 20 premiers portefeuilles** ;
un en-tête neutre dit que les relevés [Dn] sont les seuls faits, sans nommer aucune carte.
Version 3 : la lecture reçoit aussi `references/equivalences/donnees-chaine.md` (skill 0.7.55, §32), qui dit
quel relevé vaut marqueur pour dix cartes et laisse six cartes Vides.
Pas de C = B : sans carte ancrée, pas de chiffre C.
En ombre (skill 0.7.56, §33), jamais dans le critère : la règle des médiateurs (`C_mediation`) et l'ablation carte
par carte, comparées au C actuel sur les mêmes questions ; l'écart C − B est un contraste du dispositif, pas un
contrefactuel. Depuis la version 0.4.1 du banc (skill 0.7.57, §34), en ombre aussi : les cartes lues comme des causes
(`C_noisy_or`) et la borne de la valeur de l'information, enregistrées avec C ; depuis 0.4.2 (skill 0.7.58, §35), C
tempéré (α = 0,5, fixé d'avance) ; depuis 0.4.3 (skill 0.7.59, §36), le programme génératif ; depuis 0.4.4 (skill 0.7.60,
§37), la lecture probabiliste, allumée par défaut (variable `ALPHABET_TRADUCTION` à « 0 » pour l'éteindre ; un appel de plus par jeton lu). Le
protocole 4 ne change pas.

## 4. Intégrité

Instantané et prévisions scellés (SHA-256) avant toute issue ; aucun rétrospectif ; registre propre au banc.

## 5. Critère

Perte logarithmique par question. Rodage : tant que B repose sur moins de **30** issues du type, la question est
comptée à part, hors critère. À **200 questions comptées par type** : H soutenue si C bat A **et** B (séquence de
confiance du skill, verdict « meilleur »). C ≈ A : l'alphabet nomme seulement. C < B : la lecture structurelle des
données échoue dans cette strate, pas l'alphabet en général. Bilan d'étape à 30 : contrôle de fonctionnement.

## 6. Volume

**3 jetons par passage horaire** (environ 70 par jour, répartis sur toutes les heures pour ne pas biaiser l'heure
du jour), soit 1 à 2 questions par jeton : 200 questions par type en 3 à 6 jours après le rodage.
