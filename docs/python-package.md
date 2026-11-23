# Project Ghostframe for Python

English · [Français](#français) · [Project Ghostframe](https://github.com/zakariagharzouli/project-ghostframe)

`project-ghostframe` provides the `ghostframe` command and importable `ghostframe` module. It generates APNG files, inspects frame and archive metadata, and restores supported animations from a Ghostframe archive or atlas. It requires Python 3.10+ and Pillow. Ghostframe Replay is distributed as a standalone HTML app and a separate npm package.

Install from a repository checkout or from a built wheel.

```sh
python -m pip install .
# Or install the distribution archive
python -m pip install ./project_ghostframe-0.1.0-py3-none-any.whl
```

```sh
python -m ghostframe encode animation.png frame-0.png frame-1.png --delay 350
python -m ghostframe inspect animation.png
python -m ghostframe recover animation.png recovered.png
```

The default `dual` mode writes an APNG with a Ghostframe archive. `--mode apng` writes standard APNG frames, and `--mode atlas` produces a static PNG and a JSON manifest for `python -m ghostframe from-atlas`. `--sparse` uses delta rectangles for APNG or dual mode. Run `python -m ghostframe --help` for all commands. You can shorten `python -m ghostframe` to `ghostframe` when the installed console command is on your `PATH`.

## Français

`project-ghostframe` fournit la commande `ghostframe` et le module Python du même nom. Il génère des APNG, inspecte les métadonnées des trames et restaure les animations prises en charge depuis une archive Ghostframe ou un atlas. Python 3.10+ et Pillow sont nécessaires. Ghostframe Replay est distribué séparément en HTML et via npm.

Depuis un clone du dépôt, saisir `python -m pip install .`. Avec la roue construite, saisir `python -m pip install ./project_ghostframe-0.1.0-py3-none-any.whl`. Les trois commandes de l’exemple utilisent des trames PNG à fournir localement. `python -m ghostframe --help` affiche toutes les commandes. Le raccourci `ghostframe` est disponible si la commande installée est dans le `PATH`.

Le mode par défaut `dual` écrit un APNG avec archive Ghostframe. `--mode apng` écrit un APNG standard. `--mode atlas` fournit une image PNG fixe et un manifeste JSON pour `python -m ghostframe from-atlas`. `--sparse` utilise des rectangles de différences en mode APNG ou dual.
