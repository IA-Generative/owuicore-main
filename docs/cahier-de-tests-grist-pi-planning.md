# Cahier de tests — Preparation PI Planning avec Grist

Ce cahier couvre les cas d'usage pour un Product Owner preparant le PI8 a partir des donnees du document Grist "Gestion PI SDID".

### Prerequis
- **Modele** : `gpt-oss-120b`
- **Tool a activer** : `grist` (icone outils en bas du chat)
- **Document Grist** : `qXWzdtyGgNh2T64Ti1SQfc` (Gestion PI SDID)
- **Astuce** : Dans le premier message du chat, indiquer le doc_id pour que le LLM puisse ensuite interroger directement les tables sans navigation prealable
- **Nouvelle conversation** pour chaque section

> **Limitation connue** : OWUI ne supporte qu'un seul round de tool calling par message.
> Les prompts qui necessitent un chainage (naviguer puis lire) peuvent echouer.
> Privilegier les prompts qui ciblent directement une table ou un doc_id connu.

---

## 1. Decouverte et navigation

### TG1.1 — Voir l'arborescence Grist
- **Prompt** : `Montre-moi l'organisation de nos donnees sur Grist`
- **Attendu** : Le tool `grist_navigate()` est appele, affiche les organisations (Personal, SDID, templates)
- [ ] OK

### TG1.2 — Voir le schema du document
- **Prompt** : `Quelles sont les tables du document Grist qXWzdtyGgNh2T64Ti1SQfc ? Liste-les avec une breve description`
- **Attendu** : Le tool `grist_schema("qXWzdtyGgNh2T64Ti1SQfc")` est appele, le LLM liste les tables (Epics, Features, Risques, Equipes, Brainstorm_features_grist, etc.) avec une description
- [ ] OK

---

## 2. Etat des lieux du portefeuille Epics

### TG2.1 — Epics actifs
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc et montre-moi les Epics en investissement`
- **Attendu** : Le tool lit la table Epics, le LLM filtre ceux en "1-En investissement" et les presente avec id_Epic et Nom
- [ ] OK

### TG2.2 — Detail d'un Epic
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc et donne-moi le detail de l'Epic E-022 : description, intention pour le prochain increment, product owner`
- **Attendu** : Le LLM restitue les champs de l'Epic MIrAI Agents (E-022)
- [ ] OK

### TG2.3 — Tableau comparatif des Epics
- **Prompt** : `Execute cette requete SQL sur le document Grist qXWzdtyGgNh2T64Ti1SQfc : SELECT id_Epic, Nom, Etat_cycle_de_vie, Type FROM Epics ORDER BY id_Epic`
- **Attendu** : Le tool `grist_query` retourne tous les Epics, le LLM les presente en tableau
- [ ] OK

---

## 3. Preparation du backlog PI8

### TG3.1 — Features prevues pour le PI8
- **Prompt** : `Lis la table Brainstorm_features_grist du document qXWzdtyGgNh2T64Ti1SQfc et liste les features prevues pour le PI-8 avec leur priorite et Epic`
- **Attendu** : Le tool lit la table, le LLM filtre PI_cible = "PI-8" et presente un tableau (36 features attendues)
- [ ] OK

### TG3.2 — Features Must Have du PI8
- **Prompt** : `Execute cette requete SQL sur le document Grist qXWzdtyGgNh2T64Ti1SQfc : SELECT id_Feature, Nom, Epic_rattache, Type FROM Brainstorm_features_grist WHERE PI_cible="PI-8" AND Priorite="Must"`
- **Attendu** : Le tool retourne les 18 features Must, le LLM les presente en distinguant jalons et features
- [ ] OK

### TG3.3 — Repartition par paquet
- **Prompt** : `Execute cette requete SQL sur le document Grist qXWzdtyGgNh2T64Ti1SQfc : SELECT Paquet, COUNT(*) as nb FROM Brainstorm_features_grist WHERE PI_cible="PI-8" GROUP BY Paquet`
- **Attendu** : Le LLM presente la ventilation par paquet (P0, P1, P2, P3, P5) avec le nombre de features
- [ ] OK

### TG3.4 — Features sans Epic
- **Prompt** : `Execute cette requete SQL sur le document Grist qXWzdtyGgNh2T64Ti1SQfc : SELECT id_Feature, Nom, PI_cible FROM Brainstorm_features_grist WHERE Epic_rattache IS NULL OR Epic_rattache=""`
- **Attendu** : Le LLM detecte les features orphelines (ex: F-011 Note strategique, CSIA, Mois Innovation)
- [ ] OK

---

## 4. Analyse des equipes et de la capacite

### TG4.1 — Composition d'une equipe
- **Prompt** : `Lis la table Equipes du document qXWzdtyGgNh2T64Ti1SQfc et montre-moi la composition de l'equipe R&D`
- **Attendu** : Le tool lit la table Equipes, le LLM presente les membres, PO, PM et les Epics rattaches
- [ ] OK

### TG4.2 — Collaborateurs en surcharge
- **Prompt** : `Execute cette requete SQL sur le document Grist qXWzdtyGgNh2T64Ti1SQfc : SELECT Collaborateur, Capacite_Allouee, Capacite_Totale FROM Personnes WHERE Capacite_Allouee > 80`
- **Attendu** : Le LLM liste les personnes surchargees et alerte sur les risques
- [ ] OK

### TG4.3 — Affectations croisees
- **Prompt** : `Lis la table Affectations du document qXWzdtyGgNh2T64Ti1SQfc et identifie les personnes affectees a plusieurs Epics`
- **Attendu** : Le LLM croise les donnees et signale les points de contention
- [ ] OK

---

## 5. Gestion des risques et dependances

### TG5.1 — Risques du PI courant
- **Prompt** : `Lis la table Risques du document qXWzdtyGgNh2T64Ti1SQfc et donne-moi les risques du PI7 avec leur statut ROAM`
- **Attendu** : Le tool lit la table Risques, le LLM filtre sur pi_Num = 7 et presente les risques classes par ROAM
- [ ] OK

### TG5.2 — Dependances inter-equipes
- **Prompt** : `Lis la table Dependances du document qXWzdtyGgNh2T64Ti1SQfc et identifie les dependances critiques`
- **Attendu** : Le LLM presente les dependances avec leur impact et les Epics concernes
- [ ] OK

---

## 6. Retrospective PI7 et transition vers PI8

### TG6.1 — Bilan des features PI7
- **Prompt** : `Execute cette requete SQL sur le document Grist qXWzdtyGgNh2T64Ti1SQfc : SELECT Statut, COUNT(*) as nb FROM Features WHERE pi_Num="7" GROUP BY Statut`
- **Attendu** : Le LLM presente le bilan par statut (DOD atteint, En cours, reportee, etc.)
- [ ] OK

### TG6.2 — Objectives PI6
- **Prompt** : `Execute cette requete SQL sur le document Grist qXWzdtyGgNh2T64Ti1SQfc : SELECT Nom, Committed FROM Objectives WHERE pi_Num="6"`
- **Attendu** : Le LLM liste les objectives et leur engagement (Committed vs Uncommitted)
- [ ] OK

### TG6.3 — Features reportees
- **Prompt** : `Execute cette requete SQL sur le document Grist qXWzdtyGgNh2T64Ti1SQfc : SELECT id_Objet, Nom, Statut FROM Features WHERE pi_Num="7" AND Statut="reportée"`
- **Attendu** : Le LLM liste les features reportees et propose de les reprendre dans le PI8
- [ ] OK

---

## 7. Ateliers collaboratifs : brainstorm et priorisation

### TG7.1 — Synthese pour un atelier de priorisation
- **Prompt** : `Lis la table Brainstorm_features_grist du document qXWzdtyGgNh2T64Ti1SQfc et prepare-moi une synthese pour un atelier de priorisation du PI8 : liste les features par priorite (Must, Should, Could) groupees par Epic`
- **Attendu** : Le LLM structure une synthese lisible pour un workshop, avec des tableaux par niveau de priorite
- [ ] OK

### TG7.2 — Roadmap sur 3 PI
- **Prompt** : `Lis la table Brainstorm_features_grist du document qXWzdtyGgNh2T64Ti1SQfc et propose-moi une roadmap synthetique sur les 3 prochains increments (PI8, PI9, PI10)`
- **Attendu** : Le LLM agrege par PI_cible et presente une timeline avec les jalons et features cles
- [ ] OK

### TG7.3 — Signaux d'emergence
- **Prompt** : `Lis la table Emergence du document qXWzdtyGgNh2T64Ti1SQfc et identifie les sujets qui meritent d'etre discutes pour le PI8`
- **Attendu** : Le LLM presente les sujets emergents avec leur phase et les parties prenantes
- [ ] OK

---

## 8. Conformite et suivi transverse

### TG8.1 — Etat de conformite
- **Prompt** : `Lis la table Suivi_Conformites du document qXWzdtyGgNh2T64Ti1SQfc et fais-moi un bilan : quelles applications ne sont pas homologuees ou n'ont pas de declaration d'accessibilite ?`
- **Attendu** : Le LLM presente les ecarts de conformite par application
- [ ] OK

### TG8.2 — Issues ouvertes
- **Prompt** : `Lis la table Issues du document qXWzdtyGgNh2T64Ti1SQfc et liste les issues ouvertes avec leur Epic`
- **Attendu** : Le tool lit la table Issues et le LLM les presente avec contexte
- [ ] OK

---

## 9. Scenario de bout en bout — Workshop PO

### TG9.1 — Preparation de backlog pour un PO
- **Prompt** : `Je suis PO de l'Epic MIrAI Agents (E-022). A partir du document Grist qXWzdtyGgNh2T64Ti1SQfc, execute cette requete : SELECT id_Feature, Nom, Priorite, Type FROM Brainstorm_features_grist WHERE Epic_rattache="E-022" AND PI_cible="PI-8". Puis donne-moi une synthese pour preparer mon backlog PI8.`
- **Attendu** : Le tool execute la requete, le LLM synthetise les 5 features E-022 du PI8 avec recommandations
- [ ] OK

### TG9.2 — Aide a la redaction d'une nouvelle feature
- **Prompt** : `A partir de la table Brainstorm_features_grist du document qXWzdtyGgNh2T64Ti1SQfc, lis les features existantes pour t'inspirer du format. Puis aide-moi a rediger une nouvelle feature pour le PI8 sur l'Epic E-022 : un systeme de notifications push quand un agent IA a termine une tache longue. Propose un nom, une description, des criteres d'acceptation et une priorite.`
- **Attendu** : Le LLM lit les features existantes et propose une fiche structuree au meme format
- [ ] OK

---

## 10. Intention et pertinence strategique des Epics

### TG10.1 — Audit des intentions de chaque Epic
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc. Pour chaque Epic en investissement, montre-moi son intention pour le prochain increment et dis-moi si cette intention est claire, mesurable et actionnable. Pour ceux dont l'intention est faible, propose 2 a 3 reformulations alternatives classees de la plus prudente a la plus ambitieuse.`
- **Attendu** : Le LLM liste les intentions, critique leur qualite, et propose des options de reformulation pour les Epics faibles
- [ ] OK

### TG10.2 — Critique constructive d'une intention
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc et concentre-toi sur l'Epic E-022 (MIrAI Agents). Quelle est son intention pour le prochain PI ? Analyse ses forces et faiblesses, puis propose 3 options de reformulation : une version conservatrice (continuite), une version ambitieuse (croissance), et une version exploratoire (pivot). Pour chaque option, explique ce que ca change pour l'equipe.`
- **Attendu** : Le LLM produit 3 intentions alternatives avec une analyse d'impact pour chaque
- [ ] OK

### TG10.3 — Detecter les Epics sans cap
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc. Quels Epics en investissement n'ont pas d'intention definie pour le prochain increment ? Pour chacun, propose 2 intentions possibles basees sur sa description et ses hypotheses de gains, en expliquant ta logique.`
- **Attendu** : Le LLM identifie les Epics sans intention et genere des propositions argumentees
- [ ] OK

---

## 11. Probleme a resoudre et proposition de valeur

### TG11.1 — Reformuler le probleme utilisateur
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc et analyse l'Epic E-025 (MIrAI Compte Rendu). A partir de sa description et de ses hypotheses de gains, propose 3 formulations du probleme utilisateur que cet Epic resout : une version courte (1 phrase pitch), une version structuree (Qui / Souffre de quoi / Parce que / Alors que), et une version orientee impact (chiffree si possible).`
- **Attendu** : Le LLM produit 3 "problem statements" de niveaux differents, du pitch a l'analyse chiffree
- [ ] OK

### TG11.2 — Coherence entre description et hypotheses de gains
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc. Pour les 5 premiers Epics en investissement, compare la description de l'Epic avec ses hypotheses de gains. Quand tu detectes une incoherence ou une derive, propose 2 pistes de realignement : soit recentrer la description, soit adapter les gains.`
- **Attendu** : Le LLM croise les deux champs, signale les incoherences et propose des pistes concretes
- [ ] OK

---

## 12. KPI, OKR et mesure de la valeur

### TG12.1 — Tableau de bord des indicateurs
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc. Fais-moi un tableau des OKR/KPI de chaque Epic en investissement. Pour ceux qui n'en ont pas, propose 2 a 3 indicateurs pertinents en t'inspirant du contexte de l'Epic (description, gains, intention).`
- **Attendu** : Le LLM produit un tableau synthetique et complete les trous avec des propositions d'indicateurs
- [ ] OK

### TG12.2 — Analyse SMART des KPI
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc et concentre-toi sur l'Epic E-022 (MIrAI Agents). Pour chaque KPI existant, evalue s'il est SMART (Specifique, Mesurable, Atteignable, Realiste, Temporel). Puis propose 3 versions ameliorees : une version "quick win" facile a mesurer des le PI8, une version "north star" ambitieuse a 6 mois, et une version "leading indicator" qui predit le succes avant qu'il arrive.`
- **Attendu** : Le LLM analyse chaque KPI et propose 3 alternatives par categorie
- [ ] OK

### TG12.3 — Hypotheses de gains vs gains mesures
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc. Compare les hypotheses de gains avec les gains reellement mesures. Pour les Epics sans gains mesures, propose 2 a 3 metriques concretes qu'on pourrait commencer a collecter des le PI8 pour verifier les hypotheses.`
- **Attendu** : Le LLM identifie les trous de mesure et propose des metriques actionnables
- [ ] OK

---

## 13. Roadmap et alignement strategique

### TG13.1 — Vision a moyen terme
- **Prompt** : `Lis la table Epics du document qXWzdtyGgNh2T64Ti1SQfc. Quels Epics ont une roadmap a 2 PI definie ? Pour ceux qui n'en ont pas, propose 2 scenarios de roadmap : un scenario "consolidation" qui renforce l'existant, et un scenario "acceleration" qui pousse de nouvelles capacites.`
- **Attendu** : Le LLM synthetise les roadmaps existantes et propose des alternatives pour les manquantes
- [ ] OK

### TG13.2 — Alignement strategie et backlog
- **Prompt** : `Lis les tables Epics et Brainstorm_features_grist du document qXWzdtyGgNh2T64Ti1SQfc. Pour l'Epic E-022, croise son intention strategique avec les features PI8 prevues. Les features couvrent-elles bien l'intention ? S'il y a des trous, propose 2 a 3 features complementaires qui renforceraient l'alignement.`
- **Attendu** : Le LLM identifie les ecarts et propose des features complementaires argumentees
- [ ] OK

---

## 14. Preparation du workshop PI Planning

### TG14.1 — Draft d'objectives pour le PI8
- **Prompt** : `Lis les tables Epics et Objectives du document qXWzdtyGgNh2T64Ti1SQfc. A partir des objectives du PI6, propose un draft d'objectives pour le PI8 de l'Epic E-022. Pour chaque objectif, donne 2 formulations : une version Committed (engagement ferme) et une version Uncommitted (aspirationnelle). Utilise le format "En tant que..., je souhaite..." comme dans les objectives existants.`
- **Attendu** : Le LLM propose des paires Committed/Uncommitted realistes, au format existant
- [ ] OK

### TG14.2 — One-pager pour le PI Planning
- **Prompt** : `Lis les tables Epics, Brainstorm_features_grist et Risques du document qXWzdtyGgNh2T64Ti1SQfc. Je suis PM de l'Epic E-022. Prepare-moi un one-pager pour le PI Planning avec : rappel de l'intention (+ 2 reformulations au choix de l'equipe), features PI8 priorisees, risques identifies, KPI recommandes (propose 3 options), et 3 questions ouvertes a trancher en seance.`
- **Attendu** : Le LLM produit un document structure avec des options a chaque niveau pour alimenter la discussion
- [ ] OK

---

## Resume des resultats

| Section | Tests | Passes |
|---|---|---|
| 1. Decouverte et navigation | 2 | /2 |
| 2. Portefeuille Epics | 3 | /3 |
| 3. Backlog PI8 | 4 | /4 |
| 4. Equipes et capacite | 3 | /3 |
| 5. Risques et dependances | 2 | /2 |
| 6. Retro PI7 et transition | 3 | /3 |
| 7. Ateliers collaboratifs | 3 | /3 |
| 8. Conformite et suivi | 2 | /2 |
| 9. Scenario bout en bout | 2 | /2 |
| 10. Intention et pertinence | 3 | /3 |
| 11. Probleme et proposition de valeur | 2 | /2 |
| 12. KPI, OKR et mesure | 3 | /3 |
| 13. Roadmap et alignement | 2 | /2 |
| 14. Preparation workshop | 2 | /2 |
| **Total** | **36** | **/36** |
