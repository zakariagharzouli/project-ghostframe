# Phase 2 — Rapport du 22 novembre 2026

## Résultats

Le banc utilise les API réelles de Pillow 12.3.0 et OpenCV 5.0.0, puis vérifie la sortie dans Chromium. Sur la référence 96 × 64 px, les deux bibliothèques peuvent conserver l’animation lorsqu’on appelle leur mode multiframe. Leur mode raster a gardé les pixels du poster et supprimé toutes les trames. Les fichiers d’entrée sont acceptés par le même endpoint PNG local dans les deux cas. [API OpenCV](https://docs.opencv.org/4.12.0/d4/da8/group__imgcodecs.html) · [Formats Pillow](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html)

| Hypothèse | Expérience | Verdict mesuré |
|---|---|---|
| Rectangles APNG natifs | Quatre trames 96 × 64 px, mêmes pixels, délais et boucle | **1 025 → 789 octets**, −23,02 %. Quatre états visibles dans Chromium après copie et après réencodage APNG OpenCV. |
| Gain quand le fond est fixe | Six trames 384 × 216 px, fond pseudo-aléatoire déterministe et petit objet mobile | **1 702 543 → 287 172 octets**, −83,13 %. Trames décodées et calendrier identiques. Ce corpus sert à mesurer la taille. |
| Transcodage animé | Entrée APNG de 789 octets, sortie WebP sans perte de 598 octets | MIME de sortie `image/webp`, quatre empreintes RGBA et calendrier identiques. Quatre états distincts reconnus dans Chromium. |
| Capsule à parité | 1 704 × 288 px, trois tuiles de données et une tuile de parité | Récupération exacte après réencodage PNG, réduction à 50 %, recadrage avec perte d’une tuile, JPEG qualité 65 et combinaison des trois transformations. |
| Limites de la capsule | Recadrage central à 50 %, réduction à 12,5 %, conversion en niveaux de gris | Échec de récupération dans les trois cas. Les essais testent respectivement la perte de plus d’une tuile, la résolution des modules et la disparition des repères colorés. |

La combinaison recadrage, réduction et JPEG a produit un fichier **633 × 139 px de 20 305 octets**. Les tuiles 1, 2 et 3 sont lisibles. Le XOR reconstruit la tuile 0, puis le décodeur restitue les quatre trames, les quatre délais de 350 ms et la boucle. Le JPEG n’a montré qu’un état dans le navigateur. Les quatre états ont été mesurés après reconstruction en APNG dans un parcours distinct, avec un restaurateur en amont du spectateur.

OpenCV en mode animé a également conservé un poster exclu de la boucle, sa séquence et son calendrier. Il a réécrit les blocs APNG et supprimé le bloc privé `gfRs` dans les parcours qui le contenaient. Pillow en mode animé a lui aussi supprimé `gfRs` tout en gardant les trames. Le redimensionnement et le recadrage OpenCV opérés sur un seul raster ont produit des PNG fixes. Le journal contient le détail par type de bloc, la présence du profil ICC et le type de couleur PNG.

## Contrôle du rendu

Sur Windows, Chrome 158.0.8127.36 a produit 19 captures pour chacun des deux panneaux, couvrant les 20 parcours HTTP locaux. Le lancement du banc Windows a utilisé `--no-sandbox` dans l’environnement cloisonné. La démo repose uniquement sur les lecteurs natifs du navigateur. Les mesures d’une animation exigent les quatre empreintes attendues, pas une simple variation de l’écran.

Deux images fixes ont produit deux empreintes différentes lors d’un essai préliminaire où Chromium les redimensionnait à 96 × 64 px. À l’échelle 1:1, chacune de leurs régions de mesure est restée fixe. Cet essai montre pourquoi le banc compare les empreintes des états décodés et recadre les captures sans changer l’échelle pixel. Les mesures ne prétendent pas identifier le mécanisme de cette variation de rendu.

Les contrôles HTTP ont donné **415** pour un PNG déclaré en JPEG, **422** pour des octets arbitraires déclarés en PNG et **422** pour un vrai JPEG déclaré en PNG. Ces statuts décrivent le serveur du banc. Ils ne décrivent pas les contrôles d’un réseau social.

## Surfaces tierces

| Surface | Observation | Statut |
|---|---|---|
| GitHub brut, commit de phase 1 | Réponse `200 image/png`, SHA-256 du fichier publié inchangé. Le banc compte cette livraison brute séparément. | Transport vérifié. Rendu distant indéterminé sur le relevé Windows. |
| LinkedIn, bannière personnelle | L’aide indique JPG ou PNG. Aucune mesure des octets après import ni du client standard sur cette surface. | Indéterminé. |
| Facebook, profil et couverture | Les deux surfaces nécessitent leurs propres essais. | Indéterminé. |
| Instagram, photo de profil | Import, variantes livrées et lecture n’ont pas été mesurés. | Indéterminé. |
| WhatsApp Business, profil et couverture | La documentation décrit deux opérations distinctes. Les octets réellement livrés et le rendu n’ont pas été mesurés. | Indéterminé. |

Les essais sociaux exigent des pages ou comptes d’essai autorisés et un observateur indépendant dans le client standard. La distribution brute GitHub autorisée est un chemin de livraison d’octets, sans équivalence démontrée avec une surface de profil. [PNG brut épinglé à son commit](https://raw.githubusercontent.com/zakariagharzouli/project-ghostframe/f803f9373f87be92d74a2bb557f05d8e5528a542/evidence/inputs/apng-a.png) · [Aide LinkedIn](https://www.linkedin.com/help/linkedin/answer/a568217) · [Aide WhatsApp Business](https://faq.whatsapp.com/665179381840568/)

## Frontière démontrée et prochaine hypothèse

Un pipeline qui décode seulement le poster calcule la même sortie pour toute séquence partageant ce poster, comme montré par la collision binaire de phase 1. La capsule modifie ce que transporte le raster et survit à certaines transformations. Une visionneuse dont l’unique entrée est ce raster et dont la règle de rendu est fixe ne peut reconstituer une évolution des pixels dans le temps. [Collision reproductible de phase 1](rapport.md#perte-dinformation-reproductible)

L’hypothèse la plus prometteuse pour une plateforme tierce est **une variante de livraison qui préserve déjà une animation native**, sous forme d’APNG ou de WebP animé, alors qu’une autre variante du même import est fixe. Un test indépendant doit importer un PNG fixe et deux APNG à poster identique sur une surface autorisée. Il doit comparer les octets livrés pour la miniature et la vue complète, sur le web et sur mobile, puis contrôler leurs trames réellement affichées avec le même corpus de référence. Une divergence vérifiée par client et variante suffirait à orienter l’encodeur. Un aplatissement identique dans toutes les variantes testées réfuterait cette hypothèse sur cette surface.

[Matrice mesurée](../evidence/phase2/matrice.md) · [Journal SHA-256](../evidence/phase2/report.json) · [Démo HTML](../evidence/phase2/demo-phase2.html) · [Protocole](phase2.md)
