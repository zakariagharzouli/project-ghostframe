# GFS2 face aux QR fragmentés à surface égale

## Résultats

| Mesure sur les mêmes 132 cas par filtre | Lanczos | Bicubique |
| --- | ---: | ---: |
| GFS2, octets exacts et tous les clics à 2 px ou moins | **98** | **96** |
| QR carrés, mêmes critères | 30 | 30 |
| rMQR, mêmes critères | 28 | 30 |
| Meilleur témoin parmi QR carrés et rMQR pour chaque cas | 30 | 32 |
| QR carrés avec grille connue, octets exacts | 30 | 30 |
| rMQR avec grille connue, octets exacts | 72 | 71 |

GFS2 a réussi tous les cas où au moins un témoin a réussi, puis 68 cas supplémentaires en Lanczos et 64 en bicubique. Parmi les succès GFS2, la plus grande erreur de placement est de 0,502 px en Lanczos et 0,494 px en bicubique. Les deux filtres sont appliqués aux mêmes captures et aux mêmes transformations, qui incluent des essais communs sans redimensionnement.

Fournir la géométrie exacte aide le rMQR à récupérer davantage de données. Le rMQR assisté reste derrière GFS2 sur ce banc. Dans les bandes retenues, les modules de GFS2 mesurent 4 px à l’export, ceux des témoins carrés au plus 2 px et ceux des témoins rectangulaires au plus 3 px. Ce résultat porte sur l’ensemble de la méthode, de la disposition des modules à la lecture. Le banc ne mesure pas l’effet causal de chaque choix pris isolément.

Les réductions à 35 % et la suppression de la bande font échouer GFS2 sur les quatre captures. Des cas à 40 % et qualité JPEG 30 échouent également. Les résultats décrivent quatre captures synthétiques, des orientations alignées sur les axes et les configurations de témoins testées. Ils établissent un avantage expérimental de robustesse pour ces bandes minces.

## Protocole

Quatre captures synthétiques transportent respectivement 11, 84, 156 et 243 octets. Pour chaque capture, GFS2, QR Code et rMQR reçoivent exactement la même séquence binaire. Les trois disposent de la même bande centrée de 928 px de large et respectivement 40, 56, 72 ou 88 px de haut. La capture sous-jacente est identique. Pillow génère le JPEG initial à qualité 92. Les modules noirs ont la même valeur de gris dans les trois méthodes.

GFS2 utilise l’encodeur et le lecteur de l’application via Node.js. Les témoins utilisent ZXing-C++ en versions carrée et rectangulaire. Chaque famille essaie des groupes de 2, 3 ou 5 fragments de données et un fragment XOR de parité. Les QR carrés couvrent les niveaux L, M, Q et H et les versions 1 à 8. Les rMQR couvrent les niveaux M et H et les 32 versions. Pour chaque combinaison, le banc retient les deux extrêmes d’aire de symbole parmi les versions qui permettent les plus grands modules entiers. Il conserve les zones de silence produites par ZXing. Le témoin reçoit le meilleur résultat de ses variantes pour chaque transformation, même lorsqu’une autre variante gagne sur une autre transformation. [Spécification des QR carrés](https://www.qrcode.com/en/about/standards.html) · [Spécifications rMQR](https://www.qrcode.com/en/codes/rmqr.html) · [Enveloppe Python de ZXing-C++](https://github.com/zxing-cpp/zxing-cpp/tree/master/wrappers/python)

Chaque capture passe par 33 cas. Le JPEG initial sert de contrôle positif. Trente essais croisent trois cadrages, cinq échelles (100, 63, 50, 40 et 35 %) et deux qualités JPEG (65 et 30). Les recadrages enlèvent l’équivalent d’une tuile GFS2 du bord gauche ou droit et 32 px en haut avant la réduction. Les deux autres cas sont un passage en niveaux de gris après recadrage et réduction à 50 % et la suppression complète de la bande. Tous les clics restent dans la zone des recadrages positifs. Le protocole est exécuté une première fois avec la réduction Lanczos et une deuxième fois avec la réduction bicubique.

Tous les lecteurs reçoivent les 96 dernières lignes de la sortie. Un succès exige le retour des octets exacts et le placement de chaque clic visible à 2 px ou moins, en coordonnées du JPEG reçu. Le lecteur de référence obtient la configuration nominale des symboles lorsqu’il a récupéré les données. Il déduit l’échelle et le décalage des coins renvoyés par ZXing. À chaque lecture il peut cumuler les fragments obtenus dans l’image native et dans deux agrandissements à 2×.

Le contrôle complémentaire fournit aux témoins QR la géométrie exacte de la transformation et les centres théoriques de tous leurs modules. Le banc extrait les valeurs aux centres, reconstruit chaque grille et fait lire les symboles à ZXing. La géométrie est fournie de l’extérieur dans cet essai, qui mesure uniquement la récupération des octets.

## Reproduire

Exécution avec Python 3.12 et Node.js 24. Le banc génère les captures, vérifie les contrôles positifs et négatifs et enregistre la plus grande erreur de placement parmi les clics pour chaque cas et chaque configuration.

```sh
python -m pip install -r web/replay/requirements-benchmark.txt
node --test web/replay/codec.test.cjs
python web/replay/benchmark.py --resample lanczos --out run/replay/benchmark-equal-area-lanczos.json
python web/replay/benchmark.py --resample bicubic --out run/replay/benchmark-equal-area-bicubic.json
```
