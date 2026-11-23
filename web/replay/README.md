# Ghostframe Replay

Français · [English](README.en.md) · [Installation](../../README.fr.md#installation)

Créez un JPEG qui montre une capture d’écran et transporte les étapes pour reproduire un bug. L’éditeur et le lecteur fonctionnent dans le navigateur. Les images et leurs annotations restent sur l’appareil.

## Essayer

1. Ouvrir la page et cliquer sur **Lire la séquence** pour voir l’exemple.
2. Dans **Créer**, coller sa capture depuis le presse-papiers, déposer le fichier ou l’importer en PNG, JPEG ou WebP. Cliquer dans l’ordre des actions. Pour chaque repère, modifier l’annotation et la durée.
3. Cliquer sur **Exporter le JPEG**. Ghostframe relit le fichier généré avant de le télécharger et vérifie que les quatre tuiles et les données des étapes sont récupérables.
4. Dans **Rejouer**, ouvrir le JPEG. Cliquer sur **Lire la séquence**, ou parcourir les étapes une par une. **Copier les étapes** génère aussi une liste à coller dans le ticket. Si le presse-papiers est indisponible, le navigateur sélectionne le texte pour permettre une copie manuelle.

La lecture superpose les repères et leurs textes à une seule capture. L’éditeur enregistre les étapes saisies par l’auteur. Il peut stocker jusqu’à 12 étapes si l’ensemble des notes tient dans le budget de 243 octets, en-têtes compris. Une note UTF-8 peut occuper jusqu’à 96 octets. La durée d’une étape est comprise entre 0,1 et 10 secondes, par pas de 0,1 seconde.

## Exécuter et vérifier

Le projet n’a ni serveur applicatif ni dépendance à installer pour l’exécuter. Utiliser Node.js pour produire un HTML autonome.

```sh
node web/replay/build.cjs
node --test web/replay/codec.test.cjs
```

Ouvrir `web/replay/dist/index.html` comme fichier local. Pour développer et tester par HTTP, lancer depuis la racine du dépôt.

```sh
mkdir -p output/playwright
python -m http.server 8764 --bind 127.0.0.1 --directory web/replay
```

Dans un autre terminal, lancer les commandes ci-dessous. Playwright CLI nécessite un Chromium compatible. L’option `--config` permet d’indiquer son chemin. Pillow est nécessaire à la génération des contrôles JPEG.

```sh
npx --package @playwright/cli playwright-cli -s=ghostframe open http://127.0.0.1:8764/
npx --package @playwright/cli playwright-cli -s=ghostframe run-code --filename web/replay/browser-test.js
python web/replay/transforms.py output/playwright/ghostframe-example.jpg output/playwright
npx --package @playwright/cli playwright-cli -s=ghostframe goto http://127.0.0.1:8764/dist/index.html
npx --package @playwright/cli playwright-cli -s=ghostframe run-code --filename web/replay/offline-test.js
npx --package @playwright/cli playwright-cli -s=ghostframe close
```

Le premier parcours teste l’import, le collage et le dépôt, l’ajout au pointeur et au clavier, l’export vérifié, la lecture et la copie des étapes. Pour tester la copie et son repli sans modifier le presse-papiers du système, le test remplace localement l’API Clipboard. Il vérifie également l’absence de requête externe et de débordement horizontal à 390 px. Le second coupe le réseau après le chargement du HTML autonome et teste les JPEG suivants.

| JPEG de l’exemple | Dimensions | Résultat dans Chromium |
| --- | --- | --- |
| Export du navigateur | 1 120 × 706 | Trois étapes |
| Pillow qualité 65 | 1 120 × 706 | Trois étapes |
| Réduction à 50 % et qualité 65 | 560 × 353 | Trois étapes |
| Réduction à 63 % et qualité 65 | 706 × 445 | Trois étapes |
| Un bord coupé, réduction à 50 %, qualité 65 | 396 × 337 | Trois étapes, une tuile restaurée |
| Même recadrage avec passage en niveaux de gris | 396 × 337 | Trois étapes, une tuile restaurée |
| Perte de deux tuiles, réduction à 50 %, qualité 65 | 280 × 353 | Échec détecté |
| Miniature de 150 px, qualité 65 | 150 × 95 | Échec détecté |

Pour chaque succès, le test vérifie l’ordre, la fidélité des notes et des durées et la position du premier repère à un pixel près. Ces résultats portent sur l’exemple synthétique dans un banc local et sur les transformations indiquées.

### Comparaison des deux formats

Le [banc à surface égale](benchmark.md) compare aussi GFS2 à des QR et rMQR fragmentés sur les mêmes captures et données.

La [validation sur ScreenSpot-Pro](holdout.md) teste des captures issues d’un corpus public, une chaîne OpenCV et un témoin Data Matrix rectangulaire.

L’exemple contient 84 octets d’étapes. Sa bande passe de 88 à 56 px et son export JPEG de **69 782 à 65 985 octets** dans le même Chromium, avec les mêmes réglages d’export. La hauteur de la bande diminue de 36 %. Le JPEG complet diminue de 5,4 %.

Le lecteur actuel a récupéré les mêmes trois étapes dans **31 des 32 transformations de chaque format**. La matrice croise quatre échelles (63, 50, 45 et 40 %), quatre qualités JPEG (85, 65, 45 et 30) et deux cadrages (intact ou 328 px coupés à gauche et 32 px en haut avant réduction). Le cas combinant le recadrage, 40 % et la qualité 30 échoue pour les deux formats. Ce comparatif s’applique à l’exemple, avec un lecteur identique pour les deux formats.

Pour reproduire la matrice, exporter l’exemple de la révision `a751958` comme `output/playwright/ghostframe-legacy.jpg` et conserver l’export courant sous `output/playwright/ghostframe-example.jpg`. Avec le serveur local démarré, lancer les commandes suivantes.

```sh
python web/replay/transforms.py output/playwright/ghostframe-example.jpg output/playwright --compare output/playwright/ghostframe-legacy.jpg
npx --package @playwright/cli playwright-cli -s=ghostframe open http://127.0.0.1:8764/dist/index.html
npx --package @playwright/cli playwright-cli -s=ghostframe run-code --filename web/replay/matrix-test.js
npx --package @playwright/cli playwright-cli -s=ghostframe close
```

## Formats GFS2 et GFS1

Le JPEG est produit par `HTMLCanvasElement.toBlob`. Le raster contient la capture puis une bande basse de **40 à 88 px**, composée de quatre tuiles côte à côte. La capture est ramenée à au maximum 1 600 × 1 440 px et, si nécessaire, centrée sur une largeur minimale de 928 px pour accueillir la bande. La bande reste visible dans une visionneuse d’images et disparaît de l’aperçu quand le lecteur ouvre la séquence.

Les champs multioctets sont en ordre conventionnel réseau. Le flux commence par la largeur et la hauteur du poster (`uint16` chacune), puis le nombre d’étapes (`uint8`). Chaque étape contient `x` et `y` (`uint16`), la durée en unités de 100 ms (`uint8`), la longueur en octets (`uint8`) et la note UTF-8. Les positions sont exprimées dans le raster exporté avant toute transformation.

Chaque tuile forme un paquet de 6 octets par ligne dont les 15 premiers octets contiennent la signature `GFS2`, le CRC-32 du flux, la longueur utile (`uint16`), l’index (`uint8`) et le CRC-32 du paquet calculé avec ce champ à zéro. Le nombre de lignes utiles `r` est `ceil((15 + ceil(longueur / 3)) / 6)`. Le flux est complété par des zéros pour former trois fragments de `6r − 15` octets. Le quatrième fragment contient leur XOR. Le paquet est représenté en bits de poids fort d’abord, en lignes de gauche à droite. Les exports historiques `GFS1` utilisent la même structure avec `r = 16`, et restent lisibles avec le lecteur actuel.

Une tuile mesure `58 × (r + 6)` modules de 4 px. Avec des indices de module commençant à zéro, ses deux repères occupent les colonnes 1–2 et 55–56 et les lignes 1 à `r + 4`. Les données occupent les colonnes 5–52 et les lignes 3 à `r + 2`. Les quatre tuiles forment une bande centrée. Le lecteur examine la zone basse et interpole la position des transitions des barres pour estimer l’échelle et le décalage, même lorsque les bords tombent entre deux pixels. Il vérifie la cohérence des paquets et du flux avant de repositionner les repères. La parité permet de récupérer un fragment absent parmi les quatre. Les CRC détectent des pertes et des erreurs de lecture. Ils ne constituent pas une preuve d’origine.

La version actuelle cible les retouches alignées sur les axes. Une rotation, une forte réduction ou le retrait de la bande peuvent empêcher la lecture. Les résultats restent à mesurer sur les circuits de pièces jointes de vrais outils de support.
