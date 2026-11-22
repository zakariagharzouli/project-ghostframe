# Phase 2 — Protocole et formats

## Reproduire les essais

Le banc de phase 2 utilise Python 3.12, Pillow, OpenCV et NumPy. Le rendu utilise le même pilote CDP que la phase 1, avec Node 22+ et un navigateur Chromium. La page de démonstration utilise uniquement le navigateur.

```sh
python -m pip install -r requirements-phase2.txt
python -m unittest discover -s tests -v
python platform_lab.py --verify --github-raw
python audit_pair.py run/phase2/inputs/apng.png run/phase2/processed/reference.png run/phase2/receipt-reference.json
```

`--browser <chemin>` sélectionne l’exécutable. `--no-browser` produit le journal de transport et de décodage. La colonne de rendu reste indéterminée dans cette exécution. `--verify` exige les résultats attendus pour les témoins locaux en incluant le rendu. Le témoin GitHub est facultatif. En cas d’indisponibilité réseau, sa mesure reste indéterminée sans invalider les parcours locaux.

Les fichiers de `run/phase2/` comprennent les entrées, les réponses HTTP, leur inventaire binaire, une matrice Markdown, les captures dans leur ordre d’acquisition et une démonstration HTML autonome. Chaque capture consigne le temps écoulé et l’empreinte RGBA des régions de mesure. Chaque réponse consigne son type MIME, sa taille, ses dimensions, le mode de couleur, les empreintes des blocs PNG auxiliaires et le calendrier des trames décodées. Pour des dimensions identiques, le journal calcule le nombre de pixels RGBA différents et le plus grand écart par canal. Les SHA-256 permettent de comparer fichiers, rasters et trames indépendamment. [API de prise de capture Chromium](https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-captureScreenshot)

Le banc POST exige `Content-Type: image/png` et décode effectivement un PNG avant de le transmettre au profil choisi. Il sert le format produit sous son MIME réel. Les contrôles utilisent uniquement les fichiers de test générés par Ghostframe. Les profils OpenCV exécutent les API de la bibliothèque dans le banc local. Ils ne représentent pas les réglages de Facebook ou d’un autre réseau social. [Documentation OpenCV](https://docs.opencv.org/4.12.0/d4/da8/group__imgcodecs.html) · [Formats de fichier Pillow](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html)

## H1 — Rectangles APNG natifs

`ghostframe.py encode --sparse` conserve une trame initiale complète. Pour chaque trame suivante, l’encodeur calcule la boîte englobant les différences sur les quatre canaux RGBA. Il encode le rectangle et le raster complet et retient l’option la plus petite. Un cadre de 1 × 1 px à l’identique représente une trame répétée si sa compression est plus courte. Le mode de fusion APNG `SOURCE` remplace le rectangle, notamment lorsqu’une région doit devenir transparente. La disposition `NONE` garde le canvas résultant pour l’étape suivante. Le premier rectangle d’animation reste complet en présence d’un poster séparé. [Spécification PNG 3, contrôle d’une trame APNG](https://www.w3.org/TR/png/)

La condition de lecture native est un pipeline qui conserve les trames ou les réencode en un format animé que la surface de rendu joue. Les tests comparent les pixels, le poster, l’ordre, les délais et la boucle. Un profil de lecture statique ne reçoit qu’un raster depuis son décodeur, même quand les trames d’entrée occupent peu de place.

## H2 — Transcodage animé vers WebP

Le profil `pillow-webp` décode l’APNG, encode les trames en WebP sans perte et sert la réponse en `image/webp`. Il conserve les délais de la séquence et son compteur de lectures. Le prototype exige un poster commun à la première trame. Le client qui reçoit la sortie doit autoriser la lecture native du WebP animé. Le test compare la séquence décodée et tous les états visibles dans Chromium. [Options de lecture et d’écriture WebP de Pillow](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#webp)

## H3 — Capsule visible à effacement d’une tuile

```sh
python capsule.py pack run/phase2/inputs/apng.png capsule.png
python capsule.py unpack run/phase2/processed/capsule-combined.jpg restaure.png
```

Le PNG de transport est une planche lisible comme image fixe avec trois repères chromatiques visibles par tuile. Contrairement à l’atlas de phase 1, ses pixels représentent les bits d’un flux GFR1 et des données de correction. Il faut un traitement explicite en amont pour convertir ce flux en APNG.

Chaque tuile contient une grille de 56 × 32 modules, lue en rangées et bit de poids fort d’abord, soit 224 octets. L’en-tête suivant est en ordre réseau.

| Décalage | Taille | Champ |
|---:|---:|---|
| 0 | 4 | ASCII `GFC1` |
| 4 | 1 | Index de la tuile |
| 5 | 1 | Nombre `k` de tuiles de données |
| 6 | 2 | Longueur exacte du flux GFR1 |
| 8 | 8 | Préfixe SHA-256 du flux |
| 16 | 4 | CRC32 du bloc de données de cette tuile |
| 20 | 204 | Bloc de données |

Le flux GFR1 utilise la première trame comme poster de référence. Le flux est séparé en `k` blocs de 204 octets avec remplissage à zéro. La tuile d’index `k` est le XOR de toutes les autres. Si un bloc `Dj` manque, le restaurateur le calcule en faisant le XOR de la parité et de tous les blocs valides. Une deuxième perte indépendante laisse plusieurs solutions. Les contrôles d’intégrité détectent les erreurs sans authentifier l’origine des images.

Les centres magenta, cyan et vert servent à recalculer la translation et l’échelle de chaque tuile sur les deux axes. La différence de position des repères rapporte chaque centre de module à la grille. Un seuil de luminance de 125 échantillonne les données et le CRC32 écarte les blocs corrompus. Chaque axe doit conserver au moins 1,5 px par module estimés. Les rotations, transformations projectives et conversions éliminant les couleurs des repères sortent de la géométrie prise en charge. La limite est de huit tuiles de données, soit 1 632 octets GFR1 utiles, plus une tuile de parité.

## Mesures indépendantes sur une surface autorisée

Pour chaque surface, préparer un PNG fixe et deux APNG avec poster identique et des états distincts. Utiliser un compte ou une page d’essai autorisée et les fonctions d’import ordinaires. Consigner l’identifiant du client, sa version, le contexte de consultation, les réglages d’animation et l’heure de capture. Import, lecture sur une fiche et lecture dans une miniature sont des observations distinctes.

1. Consigner le résultat de l’envoi et le type déclaré. Si la surface permet de lire la ressource réellement livrée au client, conserver ses octets exacts et le type MIME de cette réponse. Séparer chaque variante de taille.
2. Prendre des captures PNG dans le client standard avec une zone stable qui couvre l’image en coordonnées physiques. Pour conclure par correspondance exacte, utiliser une surface à l’échelle 1:1, un environnement sans superposition et des intervalles assez rapprochés pour échantillonner tous les états sur plusieurs boucles.
3. Créer un reçu avec les champs `surface`, `accepted_as_png`, `delivery_mime`, `standard_client`, `box` facultatif `[x,y,largeur,hauteur]` et `captures`, un tableau d’objets `file` et `elapsed_ms` strictement croissants. Les chemins de capture sont relatifs au reçu. Le reçu produit par le banc est un exemple exécutable.
4. Exécuter `python audit_pair.py entre.png sortie.png reçu.json`. Le script compare les octets et les captures consignés. Il classe en succès seulement une animation d’origine préservée dont les états sont tous retrouvés dans les captures exactes. Un client à une autre échelle peut montrer du mouvement tout en donnant un résultat indéterminé dans cet outil. Le reçu provient de l’opérateur et mérite une réplication indépendante.

Pour tester la ressource GitHub publique déjà publiée par le projet, `--github-raw` lit un URL épinglé par commit et vérifie son SHA-256. Avec le sandbox Chromium actif, le navigateur peut charger la ressource distante directement dans le banc de capture. Cette mesure cible la distribution brute d’un blob et ne renseigne ni sur l’import d’une photo de profil ni sur les variantes d’images d’un réseau social.
