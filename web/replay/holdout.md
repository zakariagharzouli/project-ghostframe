# Validation sur ScreenSpot-Pro

## Première tranche

| Mesure sur les 252 cas | Succès |
| --- | ---: |
| GFS2, lecture ordinaire | **226** |
| Meilleur témoin QR, rMQR ou Data Matrix par cas | 195 |
| QR carré | 12 |
| rMQR | 18 |
| Data Matrix rectangulaire | 195 |

Le gain apparié est de **12,3 points**, avec un intervalle descriptif de **6,0 à 18,3 points**. GFS2 gagne sur neuf captures, fait jeu égal sur deux et perd sur la capture DaVinci Resolve. La borne inférieure est positive. Le nombre de captures gagnantes reste sous le seuil fixé de dix. À 63 % et à 50 %, les deux méthodes réussissent les mêmes cas. À 40 %, GFS2 réussit 58 cas sur 72 et le témoin combiné en réussit 27.

Avec les coordonnées exactes de la grille, la lecture au pixel le plus proche restitue au moins trois tuiles sans erreur dans 3 des 14 cas difficiles échoués par GFS2. L’interpolation bilinéaire y arrive dans 13 cas. Les contrôles où la bande est supprimée sont exclus de ce diagnostic. Sur les deux défaites face au Data Matrix, le diagnostic trouve respectivement deux et une erreurs de bit avec le pixel le plus proche, et zéro avec l’interpolation. Cette mesure utilise la grille réelle. Le lecteur expérimental, qui doit retrouver la grille lui-même, récupère **12 des 14** échecs de cette tranche, dont les deux cas DaVinci. Le format, la surface et les octets transmis restent identiques dans cette comparaison du lecteur.

## Résultats de la deuxième tranche

| Mesure sur les 240 cas avec bande | Succès |
| --- | ---: |
| GFS2, lecture ordinaire | 227 |
| GFS2, lecture ordinaire puis interpolation en cas d’échec | **240** |
| Meilleur témoin QR, rMQR ou Data Matrix par cas | 190 |
| Data Matrix rectangulaire avec grille fournie, octets exacts seuls | 189 |

La seconde passe récupère 13 cas supplémentaires sur neuf des douze nouvelles captures, sans modification du JPEG. La plus grande erreur de placement du lecteur à deux passes est de 0,7631 px. Les douze contrôles sans bande sont rejetés par tous les lecteurs.

Sur les 252 cas, le gain apparié du lecteur à deux passes sur le meilleur témoin est de **19,8 points**, avec un intervalle descriptif de **12,7 à 25,8 points**. GFS2 réussit 50 cas que le témoin ne retrouve pas. Le témoin réussit tous ses cas en commun avec GFS2. Au niveau des captures, GFS2 gagne neuf fois et fait jeu égal trois fois. Les trois égalités sont au plafond, avec vingt succès sur vingt des deux côtés. Le critère de dix captures gagnantes n’est pas franchi.

Le changement isolé et confirmé est un gain de décodage à format, image et surface constants. Le résultat couvre deux tranches disjointes d’un même corpus, centrées sur les mêmes douze applications et mesurées dans une chaîne OpenCV locale. Le protocole privilégie les cibles conservées par les deux recadrages. L’interpolation classique est évaluée ici comme une stratégie de lecture des modules GFS2. Le gain ne mesure ni les délais de résolution de tickets, ni les transformations d’une plateforme de support en production.

## Protocole fixé avant la mesure

Le codec GFS2 est celui du banc publié au commit `bf7125a`. L’expérience teste une autre provenance des images et une autre chaîne de transformation. Les captures viennent de ScreenSpot-Pro à la révision `210e78d3844251110bff86c95835ebd37a6930fa`. Les douze applications et la règle de sélection figurent dans `holdout.py`. Une capture par application est choisie par le plus petit SHA-256 calculé sur la graine `ghostframe-replay-holdout-1`, l’application et le chemin de la capture. L’éligibilité exige un centre de cible visible après les deux recadrages du banc. On retient jusqu’à trois annotations éligibles par capture dans l’ordre des identifiants. Leurs textes publics et la position des cibles servent de charges utiles. Les durées sont fixées par le banc. Les annotations représentent des cibles d’interface individuelles. [Article ScreenSpot-Pro](https://arxiv.org/abs/2504.07981) · [Données source](https://huggingface.co/datasets/likaixin/ScreenSpot-Pro/tree/210e78d3844251110bff86c95835ebd37a6930fa)

La vérification initiale des annotations a trouvé zéro capture AutoCAD éligible. Avant de mesurer la récupération, EViews l’a remplacée selon l’ordre alphabétique des applications éligibles hors liste.

Le banc utilise OpenCV pour le JPEG initial à qualité 92, le décodage, le redimensionnement `INTER_AREA` et le JPEG final. Chaque capture fournit 21 cas appariés. Dix-huit croisent trois cadrages, trois échelles (63, 50 et 40 %) et deux qualités JPEG (65 et 30). Le JPEG original, une conversion en niveaux de gris avec recadrage et la suppression de la bande servent de contrôles complémentaires. [Documentation OpenCV](https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html)

Les mêmes octets, le même fond et la même surface sont alloués à GFS2, au QR, au rMQR et au Data Matrix rectangulaire. Le QR carré couvre les versions 1 à 15. Le Data Matrix rectangulaire couvre les variantes Zint 25 à 48, dont DMRE. Chaque famille de référence dispose de ses meilleures variantes testées par cas et du contrôle supplémentaire avec grille connue. [Variantes Data Matrix dans le manuel Zint](https://github.com/zint/zint/blob/master/docs/manual.pmd)

La mesure principale associe la restitution exacte des octets et le placement de toutes les cibles à 2 px ou moins. Le témoin combiné réussit si au moins une des trois familles de référence réussit. La différence de taux est appariée par capture. L’intervalle descriptif de rééchantillonnage à 95 % est calculé avec 20 000 tirages de captures entières. Les transformations d’une même capture restent ensemble. Un avantage dans cette sélection exige une borne inférieure positive et un avantage sur au moins dix des douze captures. Ce seuil est propre au protocole et ne décrit pas une population aléatoire d’applications.

## Deuxième tranche fixée avant sa mesure

Le diagnostic sur la première tranche a motivé un lecteur à deux passes. Il conserve le résultat de la lecture ordinaire. En cas d’échec, il relit les modules par interpolation bilinéaire aux positions estimées par le lecteur, sans connaître la transformation d’avance. Cette variante est évaluée sur douze autres captures des mêmes applications, suivant la même règle avec la graine `ghostframe-replay-holdout-2` et en excluant les captures de la première tranche. Les conditions, les témoins et le seuil restent identiques. Pour isoler l’effet du second passage, le journal conserve aussi le résultat du lecteur ordinaire sur chacune de ces douze nouvelles captures.

## Reproduire

```sh
python -m pip install -r web/replay/requirements-holdout.txt
python web/replay/holdout.py --cache run/replay/screenspot-cache --out run/replay/holdout.json
python web/replay/holdout.py --followup-from run/replay/holdout.json --out run/replay/holdout-bilinear.json
```

Le journal indique la révision, les identifiants d’annotation et les empreintes des fichiers sources. Les captures restent dans le cache local. Le dépôt contient le code et les mesures.
