# Matrice Phase 2

| Cas | HTTP envoi / lecture | MIME sortie | Octets | Image par défaut | Dimensions | Trames décodées | États rendus | Natif | Récupération |
| --- | --- | --- | ---: | --- | --- | ---: | ---: | --- | --- |
| reference | 201 / 200 | image/png | 1025 | identique | 96 × 64 | 4 | 4 | succès | — |
| sparse-copy | 201 / 200 | image/png | 789 | identique | 96 × 64 | 4 | 4 | succès | — |
| dual-pillow-raster | 201 / 200 | image/png | 326 | identique | 96 × 64 | 0 | 1 | échec | — |
| dual-pillow-animation | 201 / 200 | image/png | 1010 | identique | 96 × 64 | 4 | 4 | succès | — |
| dual-opencv-raster | 201 / 200 | image/png | 976 | identique | 96 × 64 | 0 | 1 | échec | — |
| dual-opencv-animation | 201 / 200 | image/png | 1346 | identique | 96 × 64 | 4 | 4 | succès | — |
| poster-opencv-animation | 201 / 200 | image/png | 2520 | identique | 96 × 64 | 4 | 4 | succès | — |
| sparse-opencv-animation | 201 / 200 | image/png | 1346 | identique | 96 × 64 | 4 | 4 | succès | — |
| sparse-opencv-resize | 201 / 200 | image/png | 698 | modifiée | 48 × 32 | 0 | 1 | échec | — |
| sparse-opencv-crop | 201 / 200 | image/png | 582 | modifiée | 63 × 54 | 0 | 1 | échec | — |
| sparse-webp | 201 / 200 | image/webp | 598 | identique | 96 × 64 | 4 | 4 | succès | — |
| capsule-png | 201 / 200 | image/png | 39654 | identique | 1704 × 288 | 0 | 1 | échec | succès |
| capsule-resize | 201 / 200 | image/png | 18363 | modifiée | 852 × 144 | 0 | 1 | échec | succès |
| capsule-crop | 201 / 200 | image/png | 28626 | modifiée | 1267 × 278 | 0 | 1 | échec | succès |
| capsule-jpeg | 201 / 200 | image/jpeg | 80234 | modifiée | 1704 × 288 | 0 | 1 | échec | succès |
| capsule-combined | 201 / 200 | image/jpeg | 20305 | modifiée | 633 × 139 | 0 | 1 | échec | succès |
| capsule-half | 201 / 200 | image/png | 17643 | modifiée | 852 × 288 | 0 | 1 | échec | échec |
| capsule-tiny | 201 / 200 | image/png | 7834 | modifiée | 213 × 36 | 0 | 1 | échec | échec |
| capsule-gray | 201 / 200 | image/png | 24469 | modifiée | 1704 × 288 | 0 | 1 | échec | échec |
| capsule-reconstructed | 201 / 200 | image/png | 789 | identique | 96 × 64 | 4 | 4 | succès | — |
| github-raw | — / 200 | image/png | 1025 | identique | 96 × 64 | 4 | — | indéterminé | — |

## Contrôles d’entrée MIME

- PNG déclaré en JPEG — HTTP 415
- Octets arbitraires déclarés en PNG — HTTP 422
- JPEG véritable déclaré en PNG — HTTP 422

## Référence GitHub brute

Le CDN GitHub répond 200 image/png et conserve le fichier octet pour octet. Rendu distant non mesuré.
