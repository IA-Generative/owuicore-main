# Demo MirAI 10-15 min

Support de presentation pour `grafrag-experimentation` et `anef-knowledge-assistant`.

## Slide 1 - MirAI: du graphe documentaire a l'assistant reglementaire

- Support de demonstration 10-15 min
- grafrag-experimentation + anef-knowledge-assistant
- Une meme experience Open WebUI pour deux usages a forte valeur

Notes orateur:
- Ouvrir en rappelant que l'objectif n'est pas de montrer deux prototypes isoles.
- Le message cle: une meme surface conversationnelle peut accueillir un assistant GraphRAG documentaire et un assistant metier reglementaire.
- Positionner la demo comme une experimentation produit, technique et d'industrialisation.

## Slide 2 - L'intention de l'experimentation

- Tester une experience IA plus fiable qu'un simple chat generaliste.
- Combiner retrieval, graphe, citations et outils metier dans une meme interface.
- Prouver qu'on peut faire cohabiter usages generiques et expertise verticale sans forker Open WebUI.
- Valider un chemin reproductible du laptop au cluster Kubernetes.

Notes orateur:
- Cette slide doit sonner produit: on cherche de la confiance, de l'explicabilite et une experience unifiee.
- Insister sur le fait que le repo sert autant a apprendre ce qui marche qu'a derisquer un futur produit.

## Slide 3 - Ce que demontre grafrag-experimentation

- GraphRAG branche derriere Open WebUI via un bridge FastAPI et des pipelines dedies.
- Visualisation du corpus dans un graph viewer interactif, avec lecture documentaire et chronologique.
- Mode resilient: fallback documentaire si l'index complet n'est pas pret.
- Mode multi-corpus: Corpus Manager, versions publiees, ACL, worker d'indexation et sources synchronisees.

Notes orateur:
- Faire passer l'idee que ce repo ne sert pas seulement a indexer un corpus, mais a operer un cycle de vie de corpus.
- Mentionner la valeur demo: meme sans index complet, le viewer et les reponses restent utilisables.

## Slide 4 - Ce que demontre anef-knowledge-assistant

- Transformation d'un Excel metier et du CESEDA en moteur d'eligibilite explicable.
- API FastAPI orientee cas d'usage: eligibility, pieces, conditions, wizard, FAQ, legal search.
- Reponses groundees avec citations CESEDA cliquables et viewer juridique local.
- Surcouche browser legere dans Open WebUI: preview au survol, modal au clic, sans fork frontal lourd.

Notes orateur:
- Positionner ANEF comme la preuve qu'on peut aller au-dela de la recherche documentaire vers la decision assistee.
- Le point fort marketing est l'explication reglementaire, pas seulement la recherche.

## Slide 5 - Pourquoi les deux repos ensemble sont interessants

- Une meme entree utilisateur: Open WebUI, SSO Keycloak, aliases MirAI, pipelines partages.
- Deux moteurs complementaires: exploration documentaire d'un cote, expertise reglementaire de l'autre.
- Un redeploiement partage capable de reprovisionner modeles, grants, loader.js et integrations.
- Une architecture modulaire: chaque domaine evolue sans casser l'autre.

Notes orateur:
- Ici il faut raconter le choix d'architecture: separer les responsabilites, mutualiser l'experience.
- Insister sur la valeur d'une plateforme d'assistants plutot qu'un monolithe.

## Slide 6 - Scenario de demo en 10-15 min

- 1. Ouvrir Open WebUI et presenter les modeles MirAI disponibles.
- 2. Montrer une question historique sur le corpus medieval et la reponse GraphRAG avec sources.
- 3. Ouvrir le graph viewer pour visualiser les noeuds, relations et la chronologie.
- 4. Montrer le Corpus Manager ou au minimum expliquer le workflow sync > index > publish.
- 5. Basculer sur ANEF pour un cas reglementaire concret et afficher les citations CESEDA enrichies.

Notes orateur:
- Garder un rythme dynamique: 2 a 3 min GraphRAG, 2 min viewer, 2 min cycle de corpus, 3 min ANEF, 1 min conclusion.
- Ne pas faire toute l'admin en live si l'indexation est longue: montrer les etapes, puis basculer sur un resultat prepare.

## Slide 7 - Deroule de test recommande

- Prompt GraphRAG: Donne-moi une chronologie synthetique de la guerre de Cent Ans avec les batailles pivots.
- Prompt GraphRAG: Quels acteurs relient Crecy, Poitiers, Azincourt et le traite de Troyes ?
- Prompt ANEF: Pour un CST salarie - L. 421-1, quelles pieces et quels points de vigilance ?
- Interaction ANEF: survoler un lien CESEDA, ouvrir la modale, verifier la citation et le permalink.

Notes orateur:
- Si le mode multi-corpus est actif, prefixer le prompt GraphRAG avec [[corpus:<id>]].
- Si l'index n'est pas termine, utiliser le mode fallback et assumer que la demonstration porte aussi sur la resilience.
- Pour ANEF, viser une reponse qui montre pieces, conditions, citations, vigilance et revue humaine.

## Slide 8 - Messages techniques a faire passer

- Le bridge GraphRAG impose des timeouts et un fallback pour garder l'UI reactive.
- Le viewer reste disponible meme sans artefacts complets grace au document-map fallback.
- Le moteur ANEF garde les citations et l'explicabilite comme premier livrable, pas comme post-traitement cosmetique.
- Le loader.js ANEF est persiste declarativement via ConfigMap, contrairement aux aliases Open WebUI rejoues par script.

Notes orateur:
- Cette slide sert a rassurer un public technique ou sponsor: la demo n'est pas un bricolage ponctuel.
- Mettre en avant les choix d'operabilite: reprovisioning, resilience, separation des concerns.

## Slide 9 - Valeur metier et valeur de plateforme

- Pour l'utilisateur: reponses plus actionnables, plus sourcables, plus navigables.
- Pour l'equipe produit: experimentation rapide sur plusieurs UX sans reecrire toute la stack.
- Pour l'IT: local Docker et Kubernetes partagent une logique d'integration coherente.
- Pour le sponsor: preuve qu'un assistant de confiance peut mixer retrieval, graphe, moteur metier et UX augmentee.

Notes orateur:
- C'est la slide la plus marketing. Parler resultat et non seulement composants.
- Le message final: on construit une base pour des assistants specialises, pas une simple demo technique.

## Slide 10 - Limites assumees a verbaliser

- GraphRAG peut etre long a indexer sur des corpus reels: la demo doit montrer le workflow, pas promettre l'instantane.
- Les aliases Open WebUI restent rejouables apres rollout si webui.db est volatil.
- Le mode multi-corpus existe, mais n'est pas encore une plateforme de gouvernance a grande echelle.
- ANEF assiste la decision et met en avant les zones d'incertitude; il ne remplace pas une validation humaine.

Notes orateur:
- Bien formuler les limites augmente la credibilite de la demo.
- Le bon ton: nous savons ou sont les bords du systeme et nous avons des garde-fous.

## Slide 11 - Conclusion et ouverture

- Ce que nous testons: une plateforme d'assistants specialises, demonstrable et industrialisable.
- Ce que nous prouvons: Open WebUI peut devenir une couche d'experience commune pour plusieurs moteurs IA.
- Ce que nous ouvrons: nouveaux corpus, nouveaux moteurs metier, nouveaux workflows de publication et de controle.
- Prochaine etape possible: choisir 1 ou 2 cas d'usage prioritaires et durcir la boucle de validation.

Notes orateur:
- Fermer en revenant a la these initiale: une meme experience, plusieurs intelligences specialisees.
- Inviter la discussion sur les cas d'usage a prioriser apres la demo.
