# Rapport expérimental — 22 novembre 2026

## Résultat principal

Un pipeline PNG peut perdre son animation native et garder de quoi la reconstruire. Ghostframe a conservé quatre trames, leurs délais de 350 ms et leur boucle grâce à un bloc auxiliaire conservé par le pipeline. Une fois restauré sur le serveur, l’APNG a joué dans Chrome par le mécanisme ordinaire de `<img>`. La version qui contenait uniquement le bloc auxiliaire est restée fixe dans la même surface.

Un atlas a également conservé les quatre trames dans les pixels du PNG. Après un réencodage statique sans perte, le CSS de la page a affiché les quatre trames en déplaçant la fenêtre de lecture. La restauration hors ligne à partir de l’atlas et de son manifeste a aussi produit un APNG natif.

## Environnements et preuves

Le service de traitement est un serveur HTTP local. Les mesures datent du 22 novembre 2026 sous Windows, avec Python 3.12.10, Pillow 12.3.0, Node.js 24.18.0 et Chromium 158.0.8127.36. Deux exécutions, Chrome complet en mode headless et Chrome Headless Shell, ont chacune couvert 15 parcours HTTP et 14 mesures de rendu. Elles partagent la même version du moteur. Les deux suites de captures utilisent un profil neuf et le banc local avec son option de lancement documentée. La démo HTML ne charge aucune extension et ne fait appel à aucun serveur.

Chaque parcours réussi a reçu `201` à l’envoi puis `200 image/png` à la lecture. Tous les exemples retournés ont satisfait la vérification des blocs et ont été décodés par Pillow. Un test supplémentaire a vérifié le rejet d’un mauvais type déclaré et d’une fausse signature. Les 12 tests unitaires et HTTP sont passés.

| Expérience | Taille entrée → sortie | Animation après traitement | Rendu mesuré |
| --- | ---: | --- | --- |
| APNG par copie binaire | 1 025 → 1 025 octets | 4 trames, délais et boucle identiques | 4 images distinctes dans `<img>` et dans le fond CSS |
| Réencodage APNG de toutes les trames | 1 025 → 1 010 | 4 trames, délais et boucle identiques | 4 dans `<img>` |
| APNG par réencodage du raster par défaut | 1 025 → 326 | 0 trame animée | 1 dans `<img>` |
| Ghostframe par réencodage du raster avec conservation sélective de `gfRs` | 1 570 → 871 | 0 trame native, 4 récupérables | 1 dans `<img>` |
| Reconstruction à partir du bloc conservé | 871 → 1 025 | 4 trames, délais et boucle identiques | 4 dans `<img>` |
| Atlas par réencodage statique sans perte | 655 → 932 | 4 rasters empilés | 1 dans `<img>`, 4 avec la règle CSS |
| Reconstruction à partir de l’atlas et du manifeste | 932 → 1 025 | 4 trames, délais et boucle identiques | 4 dans `<img>` |
| Atlas après redimensionnement à 50 % | 655 → 2 237 | Grille modifiée, restauration exacte refusée | Surface non mesurée |
| Ghostframe par réencodage du raster seul | 1 570 → 326 | Bloc effacé, restauration refusée | Même sortie binaire que le raster aplati |

Les deux reconstructions ont produit octet pour octet l’APNG de référence sur ce corpus. L’empreinte des trames et le calendrier sont les invariants de l’outil. L’identité de fichier est un résultat du corpus et de l’encodeur. Le bloc `gfRs` a ajouté 545 octets à cet APNG, soit 53,2 %. La mesure concerne quatre images synthétiques de 96 × 64 pixels.

### Échec sur canvas

Le même APNG intact a donné une seule image sur le canvas, malgré un appel à `drawImage` à chaque rafraîchissement. Avec un APNG à poster distinct, la première trame animée apparaît dans les 19 captures des deux exécutables. Son SHA-256 diffère de celui du poster décodé par Pillow. Cet écart observé avec le texte WHATWG sur l’image par défaut mérite une reproduction dans d’autres moteurs. L’assertion du banc sur l’absence de mouvement passe et le champ `matches_html_default_image` reste faux. [Règle WHATWG pour `drawImage`](https://html.spec.whatwg.org/multipage/canvas.html#drawing-images)

### Perte d’information reproductible

`apng-a.png` contient une séquence `F0, F1, F2, F3`. `apng-b.png` contient `F0, F3, F2, F1`. Les deux ont le même raster par défaut `F0`. La transformation testée décode ce raster, l’encode en PNG RGBA et écarte les données auxiliaires. Les deux entrées produisent les mêmes 326 octets, de SHA-256 `cdc560d9f3ab06a0b2b81593952c9748ee802bf241d02f0353da4d0c6eb71798`.

Pour retrouver l’animation originale depuis ces seuls octets, un même fichier de sortie devrait désigner à la fois deux séquences différentes. Cette collision démontre la perte pour une chaîne qui conserve uniquement le raster par défaut. Une deuxième contrainte s’applique à l’affichage. Une surface dont le seul état d’entrée est un raster unique et dont la règle de rendu est fixe ne change pas de pixels dans le temps. L’atlas contourne la première contrainte en conservant toutes les trames dans le raster. Il a besoin d’une règle de rendu temporelle fournie par la page pour satisfaire la deuxième.

## Limites et travaux ouverts

- L’essai `safe-copy` exerce une politique explicite du service de référence. Le bit de copie autorise la conservation du bloc par un éditeur, et un service qui le supprime rend cette récupération impossible.
- La restauration vérifie exactement les pixels du poster ou de l’atlas. Le recadrage, le changement de dimensions et toute conversion qui altère ces pixels peuvent faire échouer cette vérification. La première version ne définit pas de correction d’erreur pour ces transformations.
- Un atlas affiche une planche de trames dans une visionneuse statique. Le CSS coopératif ou la reconstruction par le serveur sont nécessaires pour l’animer. Un APNG restauré exige une surface de rendu qui joue l’APNG natif.
- Les tailles et taux de compression sont mesurés sur une seule famille d’images. La comparaison doit être étendue à des séquences photographiques, à des images transparentes et à des délais irréguliers avant d’en tirer une conclusion de compression.
- Les mesures concernent les surfaces identifiées et le service local sous contrôle. Les lecteurs système, Firefox, WebKit et les plateformes de publication tierces restent à mesurer séparément.

Les [entrées et sorties](../evidence/), [traces Chrome](../evidence/chrome/report.json), [traces Chrome Headless Shell](../evidence/chromium/report.json) et [captures de rendu](../evidence/chrome/captures/) permettent de contrôler ces résultats.
