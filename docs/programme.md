# Programme de recherche

1. Isoler quatre observables. Vérifier la structure PNG et le décodage de l’image par défaut, enregistrer l’acceptation HTTP, comparer les images et les délais après traitement, puis mesurer les pixels composités dans un navigateur.
2. Construire les témoins. Utiliser un PNG statique, deux APNG avec image par défaut identique et animations différentes, et un APNG dont l’image par défaut est exclue de la boucle. Servir tous les fichiers en `image/png`.
3. Tester des supports indépendants pour les images d’animation. Mesurer un bloc auxiliaire privé autonome et un atlas de pixels. Comparer leur reconstruction à celle de l’APNG standard, image par image.
4. Appliquer des transformations isolées sur un service local. Tester la copie binaire, le transcodage de toutes les images, la reconstruction du seul raster avec ou sans conservation du bloc auxiliaire, puis le redimensionnement à partir du raster.
5. Mesurer les surfaces séparément. Échantillonner le rendu de `<img>`, d’un arrière-plan CSS, et d’un canvas redessiné à partir de la même image. Évaluer aussi la lecture d’un atlas au moyen d’une animation CSS fournie par la page.
6. Vérifier les échecs. Exiger une collision exacte après aplatissement des deux animations distinctes. Exiger que la récupération refuse un raster modifié ou un bloc incomplet, et qu’un atlas redimensionné échoue à la vérification d’intégrité.
7. Publier les commandes, les octets d’entrée et de sortie, les journaux de mesures, les captures et les limites par surface. Une combinaison réussit seulement quand le service l’accepte et que des images distinctes restent décodables et apparaissent sur la surface mesurée.

## Hypothèses et critères de réfutation

| Hypothèse | Expérience | Réfutation |
| --- | --- | --- |
| H1. Déclarer `image/png` permet le rendu APNG quand le navigateur reçoit l’animation intacte. | Charger les témoins via le serveur local et comparer leurs pixels dans le temps. | Texte MIME et PNG valides, images APNG distinctes intactes, une seule image mesurée sur la surface de rendu. |
| H2. Une copie auxiliaire autonome survit à la suppression sélective de l’APNG. | Reconstruire `IDAT` et recopier uniquement le bloc Ghostframe, puis récupérer un APNG. | Un digest de trame, un délai ou le nombre de lectures diffère après restauration. |
| H3. Un atlas survit à une réécriture sans perte de ses pixels et peut être joué en CSS. | Réencoder en PNG statique, vérifier le raster, puis animer la position de son arrière-plan découpé. | Divergence des pixels restaurés ou rendu CSS statique malgré le raster intact. |
| H4. Un pipeline déterministe qui ne conserve que l’image par défaut peut supprimer irréversiblement une animation. | Comparer les sorties aplaties pour deux animations aux images par défaut identiques. | Les sorties, calculées par le pipeline de référence, diffèrent. |
| H5. La présence de l’animation dans le flux suffit à toutes les surfaces natives. | Comparer `<img>`, arrière-plan CSS et `drawImage` pour la même réponse HTTP intacte. | Une surface reste statique alors qu’une autre montre les trames de la même ressource. |
