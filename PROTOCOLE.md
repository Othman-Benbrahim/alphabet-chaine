# Protocole du banc — l'alphabet sans texte

> Version 1, fixée le 2026-11-10 avant toute donnée. Toute modification = nouvelle version, scorée à part
> (`version_banc` dans chaque ligne du registre).

## 1. Hypothèse

L'alphabet situationnel est structurel : chaque carte est une structure mathématique. Le bot Metaculus ne la lit
que dans des faits rédigés. **H** : lue directement dans des données structurées (la chaîne Solana), la lecture
alphabet prévoit des événements mieux que le taux de base **et** qu'un modèle qui voit les mêmes données sans
l'alphabet. Le banc prévoit des **événements**, pas des prix, et ne vise aucune rentabilité (aucun ordre, aucun
argent ; voir MemePilot Auto, qui a montré l'imprévisibilité des prix de 5 min à 4 h avec des signaux techniques).

## 2. Questions

Jetons tirés au hasard parmi les jetons vus par GeckoTerminal (`new_pools`), âgés de **15 min à 4 h** au tirage,
réserve totale **≥ 1 000 $** au relevé, rapport RugCheck disponible (éligibilité minimale, décision du
2026-11-10 : pas de préfiltre de sécurité, qui écarterait les structures risquées). À **24 h** :

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

Les faits sont des **faits de série** (skill 0.7.54, §31) : champ, valeur, producteur, URL, heure du relevé.
Pas de C = B : sans carte ancrée, pas de chiffre C.

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
