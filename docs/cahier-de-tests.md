# Cahier de tests — Plateforme MirAI

Ce cahier couvre l'ensemble des fonctionnalites. Chaque test indique le modele a utiliser et le prompt a envoyer. Cocher chaque test une fois valide.

---

## 1. Socle — Connexion et modele par defaut

### T1.1 — Connexion Keycloak
- **Action** : Ouvrir http://localhost:3000, cliquer "Se connecter avec Keycloak"
- **Credentials** : `user1` / `user1password`
- **Attendu** : Redirection vers OWUI, nom "User One" affiche
- [ ] OK

### T1.2 — Modele par defaut
- **Action** : Creer un nouveau chat
- **Attendu** : Le modele pre-selectionne est `gpt-oss-120b`
- [ ] OK

### T1.3 — Conversation basique
- **Modele** : gpt-oss-120b
- **Prompt** : `Bonjour, presente-toi en une phrase.`
- **Attendu** : Reponse en francais mentionnant MirAI
- [ ] OK

---

## 2. Recherche web (SearXNG)

### T2.1 — Recherche simple
- **Modele** : gpt-oss-120b
- **Prompt** : `Quelles sont les dernieres actualites sur l'intelligence artificielle en France ?`
- **Attendu** : Reponse avec des informations recentes et des sources web citees
- [ ] OK

### T2.2 — Recherche factuelle
- **Modele** : gpt-oss-120b
- **Prompt** : `Quel est le cours actuel du Bitcoin en euros ?`
- **Attendu** : Valeur numerique recente avec source
- [ ] OK

---

## 3. Websnap — Extraction web

### T3.1 — Extraction de page
- **Modele** : gpt-oss-120b
- **Prompt** : `Extrais le contenu de https://www.service-public.fr/particuliers/vosdroits/N19804`
- **Attendu** : Contenu texte structure en markdown, le tool websnap est appele
- [ ] OK

### T3.2 — Screenshot
- **Modele** : gpt-oss-120b
- **Prompt** : `Fais une capture d'ecran de https://www.gouvernement.fr`
- **Attendu** : Carte HTML dans le chat avec thumbnail cliquable, titre de la page, lien full-size. Le contenu textuel de la page est disponible dans un volet depliable. Le LLM repond en langage naturel.
- [ ] OK

### T3.3 — Comparaison de sites
- **Modele** : gpt-oss-120b
- **Prompt** : `Compare les pages d'accueil de https://www.lemonde.fr et https://www.lefigaro.fr`
- **Attendu** : Analyse comparative des deux sites
- [ ] OK

### T3.4 — Screenshot avec fermeture automatique de popups
- **Modele** : gpt-oss-120b
- **Prompt** : `Fais une capture d'ecran de https://www.gouvernement.fr`
- **Attendu** : La carte HTML affiche un bandeau jaune "Pop-ups fermes automatiquement" indiquant les actions prises (ex: TarteAuCitron clique). Le screenshot montre la page sans le bandeau cookies.
- [ ] OK

### T3.5 — URL sans schema (domaine nu)
- **Modele** : gpt-oss-120b
- **Prompt** : `Extrais le contenu de www.lemonde.fr`
- **Attendu** : L'URL est auto-prefixee en `https://www.lemonde.fr`. Extraction reussie, pas d'erreur "scheme not allowed".
- [ ] OK

### T3.6 — Screenshot avec contenu textuel
- **Modele** : gpt-oss-120b
- **Prompt** : `Fais une capture de https://example.com et dis-moi ce que contient la page`
- **Attendu** : La carte HTML contient un volet depliable "Contenu textuel de la page". Le LLM repond en se basant sur le texte extrait (page_text dans le contexte JSON).
- [ ] OK

---

## 4. Dataview — Donnees tabulaires

### T4.1 — Apercu de fichier CSV
- **Modele** : gpt-oss-120b
- **Prompt** : `Donne-moi un apercu de ce fichier : https://www.data.gouv.fr/fr/datasets/r/008a2dda-2c60-4b63-b910-998f6f818089`
- **Attendu** : Tableau avec colonnes (Code_commune_INSEE, Nom_de_la_commune, Code_postal, etc.), types et premieres lignes (tool data_preview appele)
- [ ] OK

### T4.2 — Schema detaille
- **Modele** : gpt-oss-120b
- **Prompt** : `Quel est le schema detaille de ce fichier ? https://www.data.gouv.fr/fr/datasets/r/008a2dda-2c60-4b63-b910-998f6f818089`
- **Attendu** : Colonnes, types, statistiques, valeurs uniques
- [ ] OK

### T4.3 — Requete en langage naturel
- **Modele** : gpt-oss-120b
- **Prompt** : `Dans ce fichier https://www.data.gouv.fr/fr/datasets/r/008a2dda-2c60-4b63-b910-998f6f818089 quelles sont les 5 premieres lignes triees par ordre alphabetique ?`
- **Attendu** : Resultat tabulaire avec les 5 lignes
- [ ] OK

### T4.4 — Upload fichier Excel
- **Modele** : gpt-oss-120b
- **Action** : Uploader un fichier .xlsx dans la conversation
- **Prompt** : `Donne-moi un apercu de ce fichier`
- **Attendu** : data_preview appele sans url, fichier uploade detecte et analyse
- [ ] OK

### T4.5 — Recherche open data (prompt generique)
- **Modele** : gpt-oss-120b
- **Prompt** : `Peux-tu lister la liste des donnees open data ?`
- **Attendu** : Tool data_search appele, retourne des datasets depuis data.gouv.fr
- [ ] OK

### T4.6 — Recherche open data thematique
- **Modele** : gpt-oss-120b
- **Prompt** : `Trouve-moi des jeux de donnees sur la qualite de l'air en Ile-de-France`
- **Attendu** : data_search("qualite air Ile-de-France"), liste de datasets avec URLs
- [ ] OK

### T4.7 — Chaine recherche + apercu
- **Modele** : gpt-oss-120b
- **Prompt** : `Cherche sur data.gouv.fr un fichier CSV sur les prenoms donnes en France, puis donne-moi un apercu des donnees`
- **Attendu** : Le modele enchaine data_search puis data_preview
- [ ] OK

---

## 6. Generation d'images

### T6.1 — Generation simple
- **Modele** : gpt-oss-120b
- **Prompt** : `Genere une image d'un chat astronaute sur la Lune`
- **Attendu** : Image generee affichee dans le chat (FLUX.1-schnell)
- [ ] OK

---

## 7. Vision / VLM (pixtral-12b)

### T7.1 — Analyse d'image avec texte
- **Modele** : pixtral-12b-2409
- **Action** : Uploader une photo d'un document imprime (facture, courrier, formulaire)
- **Prompt** : `Que contient ce document ?`
- **Attendu** : Extraction OCR du texte en priorite, breve mention du format visuel
- [ ] OK

### T7.2 — Ecriture manuscrite
- **Modele** : pixtral-12b-2409
- **Action** : Uploader une photo de notes manuscrites
- **Prompt** : `Transcris ce texte manuscrit`
- **Attendu** : Transcription avec [illisible] ou [incertain: mot] si necessaire
- [ ] OK

### T7.3 — Image sans texte
- **Modele** : pixtral-12b-2409
- **Action** : Uploader une photo (paysage, objet, personne)
- **Prompt** : `Decris cette image`
- **Attendu** : Description detaillee du contenu visuel
- [ ] OK

---

## 8. Extraction documentaire (RAG + Tika)

### T8.1 — Upload et question sur un PDF
- **Modele** : gpt-oss-120b
- **Action** : Uploader un fichier PDF dans le chat
- **Prompt** : `Resume ce document en 5 points cles`
- **Attendu** : Resume structure base sur le contenu extrait par Tika
- [ ] OK

### T8.2 — Question precise sur un document
- **Modele** : gpt-oss-120b
- **Action** : Uploader un document (PDF, DOCX)
- **Prompt** : `Quelles sont les dates mentionnees dans ce document ?`
- **Attendu** : Liste des dates extraites du document
- [ ] OK

---

## 9. Pipeline ANEF — Reglementaire

### T9.1 — Recherche de titre de sejour
- **Modele** : ANEF Regulatory Assistant
- **Prompt** : `Quelles sont les pieces justificatives pour un titre de sejour salarie ?`
- **Attendu** : Liste de pieces avec base legale CESEDA
- [ ] OK

### T9.2 — Verification d'eligibilite
- **Modele** : ANEF Regulatory Assistant
- **Prompt** : `Je suis un ressortissant algerien avec un CDI depuis 2 ans. Suis-je eligible a une carte de sejour pluriannuelle salarie ?`
- **Attendu** : Analyse d'eligibilite avec conditions, points de vigilance et citations legales
- [ ] OK

### T9.3 — Recherche juridique
- **Modele** : ANEF Regulatory Legal
- **Prompt** : `Que dit l'article L421-1 du CESEDA ?`
- **Attendu** : Contenu de l'article avec lien cliquable vers le viewer
- [ ] OK

### T9.4 — Cas Mayotte
- **Modele** : ANEF Regulatory Assistant
- **Prompt** : `Quelles sont les specificites pour un titre de sejour a Mayotte ?`
- **Attendu** : Reponse distinguant les regles specifiques Mayotte vs metropole
- [ ] OK

---

## 10. Pipeline GraphRAG

### T10.1 — Recherche locale
- **Modele** : GraphRAG Local
- **Prompt** : `Quels sont les principaux acteurs mentionnes dans le corpus ?`
- **Attendu** : Liste d'acteurs avec citations et sources
- **Note** : Necessite un corpus indexe dans le bridge
- [ ] OK

### T10.2 — Synthese globale
- **Modele** : GraphRAG Global
- **Prompt** : `Quels sont les themes dominants du corpus ?`
- **Attendu** : Synthese thematique transversale
- [ ] OK

---

## 11. Tchap — Messagerie (si configure)

### T11.1 — Connexion
- **Modele** : gpt-oss-120b
- **Prerequis** : Avoir un compte Tchap
- **Action** : Dans les parametres du tool Tchap, renseigner email et mot de passe
- **Prompt** : `Connecte-moi a Tchap`
- **Attendu** : Message de confirmation de connexion
- [ ] OK

### T11.2 — Lister les salons
- **Modele** : gpt-oss-120b
- **Prompt** : `Quels sont mes salons Tchap ?`
- **Attendu** : Liste des salons suivis avec statistiques
- [ ] OK

### T11.3 — Analyser un salon
- **Modele** : gpt-oss-120b
- **Prompt** : `Analyse les messages du salon [nom_du_salon] de la derniere semaine. Quels sont les sujets dominants et les irritants ?`
- **Attendu** : Synthese structuree avec themes, irritants, signaux faibles. Noms pseudonymises.
- [ ] OK

---

## 12. Multi-modele et changement de contexte

### T12.1 — Changement de modele en cours de chat
- **Action** : Commencer un chat avec gpt-oss-120b, puis changer pour mistral-small
- **Prompt** : `Continue la conversation precedente`
- **Attendu** : Le nouveau modele a le contexte du chat
- [ ] OK

### T12.2 — Acces global verifie
- **Action** : Se connecter avec `user2` / `user2password`
- **Attendu** : Tous les modeles, tools et pipelines sont visibles
- [ ] OK

---

## Resume des resultats

| Section | Tests | Passes |
|---|---|---|
| 1. Socle | 3 | /3 |
| 2. Recherche web | 2 | /2 |
| 3. Websnap | 6 | /6 |
| 4. Dataview | 3 | /3 |
| 5. MCP data.gouv.fr | 2 | /2 |
| 6. Generation images | 1 | /1 |
| 7. Vision VLM | 3 | /3 |
| 8. RAG + Tika | 2 | /2 |
| 9. ANEF Pipeline | 4 | /4 |
| 10. GraphRAG Pipeline | 2 | /2 |
| 11. Tchap | 3 | /3 |
| 12. Multi-modele | 2 | /2 |
| **Total** | **33** | **/33** |
