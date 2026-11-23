# Ghostframe package releases

[Français](#français) · [English](#english)

## Français

### Prérequis des registres

- **npm.** Depuis un compte autorisé sur le scope `@residual-labs`, déposer la première archive avec `npm stage publish ./residual-labs-ghostframe-replay-0.1.0.tgz --access public` (npm 11.16.0). Le mainteneur examine cette version et la rend publique avec `npm stage approve <stage-id>` et son second facteur. Pour les versions suivantes, ajouter un Trusted Publisher GitHub dans les paramètres du paquet et autoriser `npm stage publish`. [Publication par validation npm](https://docs.npmjs.com/cli/v11/commands/npm-stage/) · [Trusted Publishing npm](https://docs.npmjs.com/trusted-publishers/).
- **PyPI.** Dans **Publishing**, ajouter un Trusted Publisher GitHub en attente pour le projet `project-ghostframe`. La première exécution de publication réussie crée le projet sur PyPI. [Formulaire PyPI](https://pypi.org/manage/account/publishing/) · [Création d’un projet via Trusted Publishing](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

| Champ GitHub | npm | PyPI |
| --- | --- | --- |
| Propriétaire | `zakariagharzouli` | `zakariagharzouli` |
| Dépôt | `project-ghostframe` | `project-ghostframe` |
| Fichier du workflow | `publish-packages.yml` | `publish-packages.yml` |
| Environnement | `npm` | `pypi` |

### Publier et installer

1. Vérifier les builds npm et Python de la PR. Depuis le commit source choisi pour la publication, créer et pousser le tag qui correspond exactement à la version du manifeste. Par exemple, `git tag pypi-v0.1.0` puis `git push origin pypi-v0.1.0`. Pour une version npm suivante, mettre à jour `package.json` et utiliser un tag `npm-v<VERSION>`.
2. Vérifier GitHub Actions. La tâche PyPI envoie la roue et l’archive source. La tâche npm dépose le paquet pour validation par un mainteneur. Valider chaque version npm avec `npm stage approve <stage-id>`.
3. Vérifier la disponibilité publique avec `npm view @residual-labs/ghostframe-replay version` et `python -m pip index versions project-ghostframe`. Ensuite, tester les commandes d’installation dans un environnement propre.

```sh
npx --yes --package @residual-labs/ghostframe-replay ghostframe-replay
python -m pip install project-ghostframe
python -m ghostframe --help
```

## English

### Registry setup

- **npm.** From an account with rights on the `@residual-labs` scope, upload the first archive with `npm stage publish ./residual-labs-ghostframe-replay-0.1.0.tgz --access public` (npm 11.16.0). A maintainer can review it and make it public using `npm stage approve <stage-id>` and their second factor. For later versions, add a GitHub Trusted Publisher in the package settings and allow `npm stage publish`. [Staged publishing](https://docs.npmjs.com/cli/v11/commands/npm-stage/) · [npm Trusted Publishing](https://docs.npmjs.com/trusted-publishers/).
- **PyPI.** Under **Publishing**, add a pending GitHub Trusted Publisher for `project-ghostframe`. The first successful upload creates the public PyPI project. [PyPI form](https://pypi.org/manage/account/publishing/) · [Creating a project through Trusted Publishing](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

| GitHub field | npm | PyPI |
| --- | --- | --- |
| Owner | `zakariagharzouli` | `zakariagharzouli` |
| Repository | `project-ghostframe` | `project-ghostframe` |
| Workflow filename | `publish-packages.yml` | `publish-packages.yml` |
| Environment | `npm` | `pypi` |

### Publish and install

1. Check the npm and Python builds on the pull request. At the selected release commit, create and push the tag that matches the exact manifest version. For example, run `git tag pypi-v0.1.0` and `git push origin pypi-v0.1.0`. For a later npm version, update `package.json` and use an `npm-v<VERSION>` tag.
2. Check GitHub Actions. The PyPI job uploads the wheel and source distribution. The npm job stages the package for a maintainer. Approve each npm version with `npm stage approve <stage-id>`.
3. Check public availability with `npm view @residual-labs/ghostframe-replay version` and `python -m pip index versions project-ghostframe`. Then run the install commands in a clean environment.

```sh
npx --yes --package @residual-labs/ghostframe-replay ghostframe-replay
python -m pip install project-ghostframe
python -m ghostframe --help
```
