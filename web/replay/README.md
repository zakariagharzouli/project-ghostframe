# Ghostframe Replay

Créez un JPEG qui montre une capture d’écran et transporte les étapes pour reproduire un bug. L’éditeur et le lecteur fonctionnent dans le navigateur. Les images et leurs annotations restent sur l’appareil.

## Essayer

1. Ouvrir la page et cliquer sur **Lire la séquence** pour voir l’exemple.
2. Dans **Créer**, importer sa propre capture PNG, JPEG ou WebP. Cliquer sur la capture dans l’ordre des actions. Pour chaque repère, modifier l’annotation et la durée.
3. Cliquer sur **Exporter le JPEG**. Sous la capture, la bande noir et blanc transporte les étapes. Quiconque possède ce JPEG peut les lire avec Ghostframe.
4. Dans **Rejouer**, ouvrir le JPEG. Cliquer sur **Lire la séquence**, ou parcourir les étapes une par une.

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

Le premier parcours teste l’import d’une capture, l’ajout au pointeur et au clavier, la modification des notes et du temps, le téléchargement, la récupération après rechargement et la lecture. Il vérifie également l’absence de requête externe et de débordement horizontal à 390 px. Le second coupe le réseau après le chargement du HTML autonome et teste les JPEG suivants.

| JPEG de l’exemple | Dimensions | Résultat dans Chromium |
| --- | --- | --- |
| Export du navigateur | 1 120 × 738 | Trois étapes |
| Pillow qualité 65 | 1 120 × 738 | Trois étapes |
| Réduction à 50 % et qualité 65 | 560 × 369 | Trois étapes |
| Un bord coupé, réduction à 50 %, qualité 65 | 396 × 353 | Trois étapes, une tuile restaurée |
| Même recadrage avec passage en niveaux de gris | 396 × 353 | Trois étapes, une tuile restaurée |
| Perte de deux tuiles, réduction à 50 %, qualité 65 | 280 × 369 | Échec détecté |
| Miniature de 150 px, qualité 65 | 150 × 99 | Échec détecté |

Pour chaque succès, le test vérifie l’ordre, la fidélité des notes et des durées et la position du premier repère à un pixel près. Ces résultats portent sur l’exemple synthétique dans un banc local et sur les transformations indiquées.

## Format GFS1

Le JPEG est produit par `HTMLCanvasElement.toBlob`. Le raster contient la capture puis une bande basse de 88 px, composée de quatre tuiles côte à côte. La capture est ramenée à au maximum 1 600 × 1 440 px et, si nécessaire, centrée sur une largeur minimale de 928 px pour accueillir la bande. La bande reste visible dans une visionneuse d’images et disparaît de l’aperçu quand le lecteur ouvre la séquence.

Les champs multioctets sont en ordre conventionnel réseau. Le flux commence par la largeur et la hauteur du poster (`uint16` chacune), puis le nombre d’étapes (`uint8`). Chaque étape contient `x` et `y` (`uint16`), la durée en unités de 100 ms (`uint8`), la longueur en octets (`uint8`) et la note UTF-8. Les positions sont exprimées dans le raster exporté avant toute transformation.

Le flux est complété par des zéros jusqu’à 243 octets, puis réparti dans trois fragments de 81 octets. Un quatrième fragment contient leur XOR. Chaque tuile forme un paquet de 96 octets avec la signature `GFS1`, le CRC-32 du flux, la longueur utile (`uint16`), l’index (`uint8`), le CRC-32 du paquet calculé avec ce champ à zéro, et le fragment. Le paquet est représenté en bits de poids fort d’abord, en lignes de gauche à droite.

Une tuile mesure 58 × 22 modules de 4 px. Avec des indices de module commençant à zéro, ses deux repères occupent les colonnes 1–2 et 55–56 et les lignes 1–20. Les données occupent les colonnes 5–52 et les lignes 3–18. Les quatre tuiles forment une bande centrée. Le lecteur repère les barres dans la zone basse, estime l’échelle et le décalage, puis vérifie la cohérence des paquets et du flux reconstruit avant de repositionner les repères. La parité permet de récupérer un fragment absent parmi les quatre. Les CRC détectent des pertes et des erreurs de lecture. Ils ne constituent pas une preuve d’origine.

La version actuelle cible les retouches alignées sur les axes. Une rotation, une forte réduction ou le retrait de la bande peuvent empêcher la lecture. Les résultats restent à mesurer sur les circuits de pièces jointes de vrais outils de support.
