# Phase 3 — Diagnostic des profils

## Ce que les originaux établissent

| Fichier fourni | Structure mesurée | Octets | Trames distinctes | Résultat rapporté par l’utilisateur |
|---|---|---:|---:|---|
| V1 Instagram | 320 × 320, RGBA 8 bits, APNG + `gfRs` | 727 506 | 24 | Import refusé |
| LinkedIn A | 320 × 320, RGBA 8 bits, PNG statique | 15 316 | 0 | Import accepté, rendu fixe |
| LinkedIn B | 320 × 320, RGBA 8 bits, APNG standard | 321 524 | 24 | Import accepté, rendu fixe |
| LinkedIn C | 512 × 512, RGBA 8 bits, PNG statique | 38 430 | 0 | Import accepté, rendu fixe |

Le validateur reconnaît les quatre fichiers et Pillow décode leurs pixels. **Retirer le seul bloc `gfRs` du fichier Instagram produit exactement B**, de SHA-256 `572bae483477ff94e2d66ac265a4a87cbf39949c918459e9289f0256322b8788`. Le bloc ajoute 405 970 octets de données plus 12 octets d’en-tête et CRC. Son archive restitue les mêmes 24 trames que B, à 90 ms chacune, en boucle. A et B ont le même SHA-256 du poster RGBA, avec des flux IDAT différents. A et C sont les témoins statiques.

Toutes les trames de V1 et B sont opaques, avec un canal alpha à 255. Aucun des deux ne contient de profil ICC, de bloc sRGB ou de bloc texte. Cela écarte la présence de pixels transparents ou d’un profil embarqué parmi les propriétés de ces deux fichiers. Le canal alpha RGBA, la taille du fichier, les dimensions, le bloc privé, le décodage APNG et la validation du client restent des facteurs expérimentaux. La différence d’acceptation Instagram–LinkedIn ne désigne aucune cause à elle seule. [Journal technique des originaux](../evidence/phase3/originaux.json)

Le banc Windows a servi les deux originaux par HTTP comme `image/png`. Dans `<img>`, 16 états distincts des régions de mesure correspondent à des trames décodées de chaque fichier sur 19 captures. Le décodage confirme les 24 trames. La cadence des captures est inférieure à celle de la séquence. Ce relevé local établit que les deux entrées peuvent animer un navigateur avant un traitement social.

Le candidat N01 dérivé de B utilise les rectangles APNG et le RGB opaque. Il pèse **273 140 octets**, contre 321 524 pour B, et conserve exactement les 24 trames RGBA normalisées, les délais et la boucle. Ses 16 états échantillonnés correspondent aussi aux régions attendues dans Chromium.

## Nouveaux essais manuels du 22 novembre 2026

| Fichier exact du kit | Instagram, photo de profil | LinkedIn, photo de profil |
|---|---|---|
| IG01, PNG fixe issu du flux `IDAT` de B | Accepté | Accepté, rendu fixe |
| IG02, identique à B, APNG RGBA sans `gfRs` | Le client ne le charge pas | Accepté, rendu fixe |
| N01, APNG RGB à rectangles sans `gfRs` | Le client ne le charge pas | Accepté, rendu fixe |
| IG12, PNG fixe de 13 921 octets | Accepté et ajouté à la photo de profil, rendu fixe | Non testé |
| IG13, APNG à deux trames de 13 921 octets | Le client ne le charge pas | Non testé |
| IG14, APNG à une trame de 13 921 octets | Accepté | Non testé |

Sur Instagram, les refus d’IG02 et de N01 se produisent sans `gfRs`. Un canal alpha n’est pas requis pour reproduire ce comportement. IG12 et IG13 ont la même longueur, le même `IHDR` et le même `IDAT`. La photo de profil est mise à jour avec IG12, tandis qu’IG13 ne se charge pas. Un seuil portant seulement sur le poids total ou les dimensions ne peut expliquer cette différence. Le phénomène est reproduit dès deux trames. Le témoignage ne localise pas le refus entre le client et le serveur.

Sur LinkedIn, l’encodage RGB et les rectangles n’ont pas changé le résultat visible. La capture des octets livrés reste l’expérience qui permet de distinguer aplatissement et rendu fixe. Le journal date ces observations et les associe aux SHA-256 des fichiers effectivement remis à l’utilisateur, indépendamment des analogues synthétiques. [Observations manuelles et identifiants](../evidence/phase3/essais-profils.json)

## Deux manières de rendre B fixe

Le banc effectue des transformations réelles et mesure le rendu à l’échelle 1:1, sur une région de 96 × 64 px de chaque image carrée. La ressource servie, son MIME, les empreintes des données et les captures sont comparés séparément.

| Parcours contrôlé | Trames de la réponse | États de la région | Attribution |
|---|---:|---:|---|
| APNG copié, `<img>` | 4 | 4 | Lecture native |
| Même source réencodée via le seul raster, `<img>` | 0 | 1 | Animation absente dès la livraison |
| Même APNG copié, redessiné dans `canvas` | 4 | 1 | Animation intacte, rendu fixe |
| APNG réencodé via OpenCV multiframe, `<img>` | 4 | 4 | Lecture native |
| WebP multiframe après import PNG, `<img>` | 4 | 4 | Lecture native après changement de format |
| APNG RGB à rectangles, `<img>` | 4 | 4 | Lecture native du candidat carré |

Le `canvas` utilise le comportement standard de `drawImage`. Les captures répétées couvrent deux boucles avec des intervalles inférieurs à un délai de trame avant de classer un rendu fixe malgré la présence d’une animation. Plusieurs empreintes reconnues suffisent pour démontrer du mouvement. Le lancement Chromium dans le banc Windows a utilisé `--no-sandbox`. Le workflow Linux exécute la suite de témoins avec son sandbox actif. [Rendu d’images animées dans canvas](https://html.spec.whatwg.org/multipage/canvas.html#drawing-images)

Si une variante servie par LinkedIn est fixe, son MIME, ses dimensions et l’identité de son poster peuvent établir que l’animation a disparu avant affichage. Ces indices ne désignent pas à eux seuls le logiciel de conversion. Si la variante réellement utilisée contient encore des trames distinctes, un rendu fixe documenté isole un écart côté client ou surface. À ce jour, A, B et C sont les fichiers **d’entrée** fournis. Leurs octets servis après import restent à collecter.

Pour un traitement déterministe `T(F) = E(poster(F))`, deux animations partageant leur poster donnent la même sortie, même si leurs suites temporelles diffèrent. De plus, un lecteur qui ne peint qu’un raster constant réalise `R(T(F), t) = R(T(F))`. Le fichier seul ne peut faire évoluer le rendu de ce lecteur. Un canal de stockage comme `gfRs` n’y ajoute aucun mécanisme temporel. Les chemins les plus proches de l’objectif sont ceux où la variante livrée garde un APNG ou un WebP animé et où le client standard le joue. Cela reste une hypothèse sur LinkedIn et Instagram. [Collision mesurée en phase 1](rapport.md#perte-dinformation-reproductible)

## Suite de compatibilité

Le générateur emploie la même animation carrée et des variantes appariées. La suite publique utilise des formes synthétiques. Les deux originaux fournis construisent une deuxième suite locale sur les 24 trames de B. Le tableau CSV distingue les résultats rapportés par l’utilisateur et les nouveaux essais marqués `non testé`.

| Essais | Facteur principal |
|---|---|
| IG01 / IG02 | Raster fixe extrait de l’IDAT, puis APNG RGBA complet |
| IG03 / IG04 / IG05 / IG06 | Rectangles, organisation du poster, bloc privé, RGB opaque |
| IG07 / IG08 / IG09 / IG10 / IG11 | Pixels transparents, sRGB, ICC sRGB, texte, poids via compression |
| LI01 / LI02 et LI03 / LI04 | Paires fixe et animée à 400 et 512 px |
| N01 | Candidat combiné RGB à rectangles |

Ajouter un bloc change naturellement le poids. Réencoder le même film avec un autre niveau zlib donne un témoin séparé pour le poids, sans garantie d’explorer tous les seuils possibles. Redimensionner conserve la séquence et les délais, mais modifie les échantillons et généralement le poids. Dans l’essai sur le poster distinct, l’IDAT est hors de la boucle tout en conservant exactement l’apparence de la première trame. LinkedIn documente JPG ou PNG et une taille d’au moins 400 × 400 px pour la photo de profil. Les acceptations à 320 px rapportées restent des observations sur les sessions testées. Utiliser une image et un compte d’essai autorisés et conformes aux règles de la surface. [Conditions de la photo de profil LinkedIn](https://www.linkedin.com/help/linkedin/answer/a549049?lang=en)

### Contrôles à poids égal sur Instagram

IG12 est un PNG fixe et IG13 un APNG à deux trames avec un point visible qui clignote. Dans le kit local, tous deux font 13 921 octets et reprennent le même `IHDR` et le même flux `IDAT` qu’IG01. IG12 ajoute un bloc `tEXt` de taille calculée. IG13 ajoute les blocs nécessaires à la boucle APNG. Sur 19 captures du banc Chromium, IG12 montre un état et IG13 les deux états décodés. L’essai Instagram rapporté porte sur le chargement et l’ajout au profil. Il ne contient pas de trace HTTP.

IG14 garde le poids de 13 921 octets et le même poster. Il déclare une seule trame APNG avec `acTL` et `fcTL`, sans `fdAT`. Comme IG12, il emploie `tEXt` pour compléter sa longueur. **Instagram accepte IG14 dans l’essai rapporté.** La seule présence des blocs `acTL` et `fcTL` ne suffit donc pas à provoquer le refus. IG13 ajoute une deuxième trame encodée par `fdAT` dans un rectangle décalé de 32 × 32 px. La réponse du client à ces différences reste à attribuer. [Spécification PNG 3](https://www.w3.org/TR/png/)

### Deux trames en rectangle ou en plein cadre

IG15 et IG16 gardent le poster encodé d’IG01, les mêmes deux trames décodées et les mêmes délais de 500 ms. Tous deux utilisent `OVER` et un bloc `fdAT` pour la deuxième trame. IG15 encode cette trame sur un rectangle décalé de 32 × 32 px. IG16 encode le même signal sur une trame complète de 320 × 320 px en remplissant les pixels autour du point avec de la transparence. Les deux fichiers utilisent le même texte `tEXt` avec une quantité de remplissage calculée pour égaliser le poids. Ils font chacun 14 379 octets dans le kit local. Chromium affiche les deux mêmes états dans les deux cas.

Tester d’abord IG16. Un refus reproduirait le problème avec seulement deux trames et une deuxième trame en plein cadre. Si IG16 est accepté, tester IG15 permet de comparer le rectangle à poids, poster, délai et rendu d’origine égaux. Une acceptation n’établit la lecture animée qu’après observation du profil standard. [Contrôles synthétiques reproductibles](../evidence/phase3/controle-cadre/)

## Collecter la variante réellement livrée

Sur son propre profil d’essai, utiliser l’onglet Réseau du navigateur standard, filtrer les images et identifier la requête qui correspond à l’image réellement affichée. Consigner le code HTTP et `Content-Type`, puis enregistrer les octets de la réponse sans réexport via un éditeur. Répéter pour la miniature, la photo du profil et l’affichage agrandi si disponibles. Séparer web et mobile. Écarter l’aperçu local avant envoi et les captures de l’image comme méthode d’acquisition des octets. Les captures n’appartiennent qu’à la mesure visuelle. Ne pas partager de HAR complet, de cookies ou d’URL signée.

Le comparateur lit un reçu JSON local. Pour chaque variante, fournir `role`, `file`, `mime`, `client` et `delivery_verified` si la réponse a été identifiée. Pour les captures, ajouter `standard_client`, `capture_box` (x, y, largeur, hauteur), `source_box` si seule une région est visible à l’échelle 1:1, et `captures` avec le fichier PNG et `elapsed_ms`. Les chemins sont relatifs au reçu. Sans octets ou mesures visuelles suffisantes, renseigner l’observation manuelle et garder le diagnostic correspondant indéterminé. Un redimensionnement à l’écran ou une incrustation peut empêcher la comparaison exacte. Le reçu produit par le banc sert d’exemple exécutable.

```sh
python -m pip install -r requirements-phase2.txt
python -m unittest discover -s tests -v
python profile_fixtures.py
python profile_weight_pair.py run/phase3-suite/IG01_statique_IDAT_320.png
python profile_weight_pair.py run/phase3-suite/IG01_statique_IDAT_320.png --frame-bounds --out run/phase3-frame-bounds
python pngcheck.py run/phase3-suite/IG02_apng_rgba_320.png
python profile_lab.py --verify
python profile_diagnosis.py run/phase3-profiles/source-IG02_apng_rgba_320.png run/phase3-profiles/recu-IG02_apng_rgba_320.json
python profile_fixtures.py --out run/kit-local --instagram V1.png --linkedin-b B.png
```

Le validateur vérifie les CRC et l’ordre des blocs essentiels, les combinaisons pixel et profondeur, les palettes, les flux zlib et filtres de ligne, l’entrelacement Adam7, les séquences et rectangles APNG, les délais et le poster décodé par Pillow. Il inventorie aussi les métadonnées et valide la structure ICC embarquée. Il applique les limites de volume Ghostframe et contrôle les blocs décrits dans son périmètre. Le comparateur accepte également JPEG, WebP, GIF et AVIF si le Pillow utilisé fournit leur décodeur. [Spécification PNG 3](https://www.w3.org/TR/png/)
