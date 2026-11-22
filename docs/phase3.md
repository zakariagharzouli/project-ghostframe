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

Le candidat N01 dérivé de B utilise les rectangles APNG et le RGB opaque. Il pèse **273 140 octets**, contre 321 524 pour B, et conserve exactement les 24 trames RGBA normalisées, les délais et la boucle. Ses 16 états échantillonnés correspondent aussi aux régions attendues dans Chromium. Son import et sa lecture sur les deux plateformes restent à mesurer.

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

### Ordre recommandé pour l’essai humain Instagram

1. Importer `IG01_statique_IDAT_320.png` du kit local, issu exactement du raster encodé de B. Consigner le signal observé dans le client, y compris si l’échec arrive avant ou après l’aperçu.
2. Dans les mêmes conditions, importer `IG02_apng_rgba_320.png`, qui est B octet pour octet. Comparer à V1 (`IG05_apng_gfRs_320.png`) si le même import peut être retenté dans les conditions autorisées.
3. Si l’APNG est rejeté, exercer les témoins rectangles et RGB séparément, puis le candidat combiné si utile. Un APNG accepté doit encore passer la vérification des octets servis et du rendu.

Un IG02 accepté et un IG05 refusé isoleraient une différence liée à l’ajout de `gfRs` sur cet essai. Le poids ajouté resterait à départager du type de bloc. IG01 accepté et IG02 refusé isoleraient un écart lié à la présence de la structure APNG et des octets correspondants. Répéter à client et dimensions stables. Aucun essai Instagram supplémentaire ne figure comme exécuté dans ce rapport.

## Collecter la variante réellement livrée

Sur son propre profil d’essai, utiliser l’onglet Réseau du navigateur standard, filtrer les images et identifier la requête qui correspond à l’image réellement affichée. Consigner le code HTTP et `Content-Type`, puis enregistrer les octets de la réponse sans réexport via un éditeur. Répéter pour la miniature, la photo du profil et l’affichage agrandi si disponibles. Séparer web et mobile. Écarter l’aperçu local avant envoi et les captures de l’image comme méthode d’acquisition des octets. Les captures n’appartiennent qu’à la mesure visuelle. Ne pas partager de HAR complet, de cookies ou d’URL signée.

Le comparateur lit un reçu JSON local. Pour chaque variante, fournir `role`, `file`, `mime`, `client` et `delivery_verified` si la réponse a été identifiée. Pour les captures, ajouter `standard_client`, `capture_box` (x, y, largeur, hauteur), `source_box` si seule une région est visible à l’échelle 1:1, et `captures` avec le fichier PNG et `elapsed_ms`. Les chemins sont relatifs au reçu. Sans octets ou mesures visuelles suffisantes, renseigner l’observation manuelle et garder le diagnostic correspondant indéterminé. Un redimensionnement à l’écran ou une incrustation peut empêcher la comparaison exacte. Le reçu produit par le banc sert d’exemple exécutable.

```sh
python -m pip install -r requirements-phase2.txt
python -m unittest discover -s tests -v
python profile_fixtures.py
python pngcheck.py run/phase3-suite/IG02_apng_rgba_320.png
python profile_lab.py --verify
python profile_diagnosis.py run/phase3-profiles/source-IG02_apng_rgba_320.png run/phase3-profiles/recu-IG02_apng_rgba_320.json
python profile_fixtures.py --out run/kit-local --instagram V1.png --linkedin-b B.png
```

Le validateur vérifie les CRC et l’ordre des blocs essentiels, les combinaisons pixel et profondeur, les palettes, les flux zlib et filtres de ligne, l’entrelacement Adam7, les séquences et rectangles APNG, les délais et le poster décodé par Pillow. Il inventorie aussi les métadonnées et valide la structure ICC embarquée. Il applique les limites de volume Ghostframe et contrôle les blocs décrits dans son périmètre. Le comparateur accepte également JPEG, WebP, GIF et AVIF si le Pillow utilisé fournit leur décodeur. [Spécification PNG 3](https://www.w3.org/TR/png/)
