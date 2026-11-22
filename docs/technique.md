# Documentation technique

## Trois représentations

**APNG.** Le générateur écrit des PNG RGBA 8 bits, non entrelacés. `IHDR` donne les dimensions, `acTL` annonce le nombre de trames et de lectures, `fcTL` décrit chaque trame et `fdAT` contient ses données, sauf si la première trame est portée par `IDAT`. Quand le poster est distinct, `IDAT` précède le premier `fcTL`. Toutes les trames occupent le canevas entier et remplacent ses pixels, avec les opérations APNG `NONE` et `SOURCE`. Le délai est un entier positif en millisecondes avec dénominateur 1000. La CLI accepte des PNG statiques de dimensions identiques et normalise les pixels en RGBA 8 bits. [Spécification W3C PNG](https://www.w3.org/TR/png/)

**Ghostframe.** `gfRs` est un bloc auxiliaire privé, réservé à cette expérience. Le premier caractère minuscule autorise son omission par un décodeur PNG. Le deuxième indique un nom privé, le troisième majuscule respecte le bit réservé et le quatrième minuscule permet à un éditeur de copier ce bloc inconnu après modification des données essentielles. Cette permission de copie dépend de l’éditeur. Le générateur écrit `gfRs` après les données d’image. Le bloc contient une copie indépendante de la séquence, dont la récupération est soumise à la vérification du poster. [Convention des blocs PNG](https://www.w3.org/TR/png/#5Chunk-naming-conventions) · [Règles de copie](https://www.w3.org/TR/png/#14Editor-behaviour)

**Atlas.** Les rasters RGBA complets sont empilés verticalement en un seul `IDAT`. Le manifeste donne les dimensions d’une trame, les SHA-256 du raster entier et de chaque trame, les délais en millisecondes et le nombre de lectures. La reconstruction vérifie ces empreintes avant de générer un APNG. Le CSS de la démo cible quatre trames de 350 ms et utilise une fenêtre à la taille d’une trame. `steps(4, end)` fait avancer la position de l’arrière-plan d’une hauteur de trame par pas. Une application qui génère le CSS pour d’autres atlas doit fournir les dimensions et le calendrier correspondants.

## Bloc privé `gfRs`, version GFR1

Tous les champs entiers sont non signés et en ordre réseau. La longueur et le CRC32 extérieurs suivent le format de bloc PNG.

| Décalage | Taille | Champ |
| ---: | ---: | --- |
| 0 | 4 | ASCII `GFR1` |
| 4 | 2 | Largeur |
| 6 | 2 | Hauteur |
| 8 | 2 | Nombre de trames `N` |
| 10 | 4 | Nombre de lectures, 0 pour une boucle infinie |
| 14 | 32 | SHA-256 binaire du raster par défaut en RGBA, ordre des lignes |
| 46 | variable | Un flux zlib contenant le tableau temporel suivi des pixels |

Le flux décompressé commence par `N` délais de 2 octets chacun. Viennent ensuite les pixels RGBA contigus de la première trame et `N−1` résidus XOR calculés par rapport à la trame précédente. Chaque raster occupe exactement `largeur × hauteur × 4` octets. La lecture exige la fin du flux zlib, sa longueur exacte et un bloc unique. Le CRC et les SHA-256 vérifient la cohérence des données. Ils ne constituent pas une signature de provenance.

Le restaurateur refuse les posters modifiés, même si le contenu autonome demeure décodable. Le mode à poster séparé est utilisé lorsque ses pixels diffèrent de la première trame. Une entrée où les deux rasters sont identiques peut devenir un APNG qui partage le poster et la première trame. La représentation ne cherche pas à recréer les blocs d’origine, les métadonnées colorimétriques ni les rectangles internes d’un APNG externe.

## Protocole expérimental

1. Générer les entrées dans `run/inputs/`. `apng-a.png` et `apng-b.png` ont les mêmes pixels par défaut et un ordre différent pour les trames suivantes.
2. Envoyer un `POST /upload/<profil>` avec `Content-Type: image/png`. Le laboratoire vérifie la structure de blocs et les CRC, puis charge effectivement les pixels dans Pillow. Il répond `201` avec une URL indexée par SHA-256. Un GET renvoie les octets stockés et l’en-tête `image/png`.
3. Enregistrer les fichiers de sortie, les tailles, les listes de blocs et les empreintes des fichiers et des pixels. Pour l’animation native, inclure le SHA-256 de chaque trame, les délais et le compteur de lectures.
4. Charger la page de mesure en HTTP et capturer 19 images de la surface compositée. Le script Node utilise CDP uniquement pour piloter le navigateur de test et récupérer les captures. Chaque crop de 96 × 64 pixels est comparé aux SHA-256 des trames attendues. La page `<img>` et l’arrière-plan APNG utilisent les mécanismes natifs. Le canvas appelle `drawImage` à chaque rafraîchissement. [Capture de surface Chromium](https://chromedevtools.github.io/devtools-protocol/tot/Page/#method-captureScreenshot) · [Règle HTML pour les images animées dans canvas](https://html.spec.whatwg.org/multipage/canvas.html#drawing-images)
5. Générer `report.json`, les captures PNG, `render.gif` qui reprend quatre régions de ces captures et la page indépendante `demo.html`. Le GIF sert de résumé de la mesure. L’animation de la page HTML provient des PNG qu’elle contient.

Les profils sont `copy`, `all-frames` avec Pillow, `raster` qui ne réencode que le poster, `safe-copy` qui réencode le poster et recopie expressément `gfRs`, et `resize` qui rééchantillonne le poster à la moitié des dimensions avant réencodage. Le serveur stocke les résultats en mémoire pour la durée d’un essai. Les garde-fous du prototype limitent les fichiers à 32 Mio, les rasters à 4 millions de pixels, et les trames à 120 et 32 Mio décompressés.

En environnement cloisonné où le navigateur échoue au lancement, le banc accepte `GHOSTFRAME_TEST_NO_SANDBOX=1` pour ouvrir exclusivement la page du banc sur `127.0.0.1` avec un profil jetable. Les mesures de référence Windows ont utilisé cette option de lancement. Elle est enregistrée dans les traces et n’est requise ni par le PNG ni par la démonstration.
