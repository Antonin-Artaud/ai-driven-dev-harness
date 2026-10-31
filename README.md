# ai-delivery-workflow

Plugin d'agents (format [Agent Plugins 1.0](https://agent-plugins.org/)) pour VS Code et GitHub Copilot. Il transforme une demande (prompt, spec ou work item Azure DevOps) en **PR draft Azure Repos** relue. Le parcours passe par un challenge du besoin métier, un plan d'architecture qui part de la cartographie du projet, une implémentation qui suit le plan et met cette cartographie à jour, et une review indépendante fondée sur les skills du projet.

```
challenger ─▶ architect ─▶ builder ─▶ PR draft ─▶ ta revue dans Azure DevOps ─▶ builder (retours) ─▶ tu publies
 brief.md      plan.md      ├─ implementer (subagent, un lot à la fois)
                            └─ reviewer (subagent indépendant, autre famille de modèles)
```

Chaque passage entre agents interactifs est un **handoff** (`send: false`) : tu valides le brief ou le plan, puis tu cliques.

## Contenu

| Élément | Rôle |
|---|---|
| `challenger` (agent) | Challenge le besoin, trie la demande (fast, standard, feature) et produit `brief.md` |
| `architect` (agent) | Part de la cartographie `docs/architecture/`, vérifie dans le code, compare des options, conteste ta vision et produit `plan.md` découpé en lots, avec l'impact sur la doc |
| `builder` (agent) | Orchestre implementer et reviewer, pousse la branche, ouvre la PR draft et traite les commentaires de PR |
| `implementer` (subagent caché) | Implémente un lot en TDD (red-green-refactor) : tests, code, mise à jour de la doc d'architecture, un commit |
| `reviewer` (subagent caché) | Relit `merge-base..HEAD` en appliquant d'abord les skills du projet, vérifie que la doc d'architecture suit le code, puis écrit `review.md` |
| `skills/` | `delivery-workflow`, `business-challenge`, `solution-design`, `plan-execution`, `red-green-refactor`, `code-review`, `pr-feedback`, `azure-devops`, `project-onboarding`, `architecture-mapping` |
| `com.github.copilot/hooks/hooks.json` | Garde-fous déterministes `PreToolUse` et `Stop` (scripts Python, bibliothèque standard uniquement) |

Les agents restent légers. Toute la méthode vit dans les skills, un format portable, et chaque projet garde la main grâce à ses propres skills : **les skills du projet passent avant ceux du plugin**.

## Prérequis

- VS Code avec GitHub Copilot, harness **Local** (pour les handoffs).
- Python ≥ 3.9 dans le PATH : `python` sous Windows, `python3` sous Linux et macOS.
- Git, un dépôt hébergé sur Azure Repos et une organisation Azure DevOps rattachée à Microsoft Entra ID (exigence du serveur MCP distant).

## Installation

Source : [Antonin-Artaud / ai-driven-dev-harness](https://github.com/Antonin-Artaud/ai-driven-dev-harness) (GitHub).

**Option 1 (recommandée pendant la mise au point) : clone local.** Clone le dépôt, puis déclare-le dans les paramètres utilisateur de VS Code (`settings.json`). Une modification du plugin est alors prise en compte sans réinstallation.

```powershell
git clone "https://github.com/Antonin-Artaud/ai-driven-dev-harness.git" <dossier-des-plugins>\ai-delivery-workflow
```

```jsonc
{
  "chat.plugins.enabled": true,
  "chat.pluginLocations": {
    "<dossier-des-plugins>/ai-delivery-workflow": true
  },
  "chat.useHooks": true
}
```

**Option 2 : installation depuis la source.** Lance **Chat: Install Plugin From Source** et colle l'URL du dépôt. VS Code clone le dépôt avec tes identifiants git Azure Repos.

Dans les deux cas, le workspace doit être approuvé (*trusted*), sinon les hooks ne s'exécutent pas.

## Onboarding d'un projet

1. Ouvre le projet et lance le skill `/project-onboarding`.
2. L'agent exécute `skills/project-onboarding/scripts/onboard.py`, d'abord en `--dry-run` :
   - il déduit l'organisation, le projet et le repo du remote `origin` ;
   - il crée ou complète `.vscode/mcp.json` avec `ado-read` (lecture seule) et `ado-write` (PR draft et commentaires uniquement) ;
   - il ajoute `.ai/` à `.git/info/exclude`, sans toucher au `.gitignore` de l'équipe ;
   - avec `--docs`, il crée le squelette de la cartographie dans `docs/architecture/` (ou `--docs-path <dossier>`), sans écraser l'existant.
3. Il te propose de cartographier l'application (skill `architecture-mapping`) : il te montre les pages et les points « À confirmer », puis les commite sur une branche dédiée pour une PR.
4. Il rédige la section **AI delivery workflow** de `AGENTS.md` : commandes, branche de base, glossaire et correspondance optionnelle entre étapes et skills du projet. Il te demande validation avant d'écrire.
5. Commite `AGENTS.md`, et `.vscode/mcp.json` s'il est suivi par git, sur la branche de base. Le builder exige un arbre de travail propre avant de créer sa branche `ai/<slug>`.
6. Démarre `ado-read` et `ado-write` depuis la vue MCP (connexion Entra).

## Utilisation

1. Sélectionne l'agent **challenger** et donne ta demande, ou un ID ou une URL de work item.
2. Réponds aux questions (5 maximum par tour, chacune avec une réponse par défaut) et valide `brief.md`. Clique ensuite sur **Design the solution**, ou sur **Fast path** pour un petit changement.
3. L'**architect** propose des options, conteste ta vision et produit `plan.md`. Valide-le, puis clique sur **Implement the plan**.
4. Le **builder** fait implémenter les lots et relire la branche (2 itérations de review au maximum, sinon il te passe la main). Il pousse la branche, puis crée la PR draft liée au work item ; tu confirmes chacune de ces deux actions.
5. Relis la PR draft dans Azure DevOps et commente.
6. De retour dans VS Code, clique sur **Address PR feedback**. Le builder classe les commentaires ; **tu valides ce classement**, puis il corrige, fait relire et répond à chaque fil.
7. Publie la PR toi-même. Mets ensuite `phase` à `done` dans `.ai/<slug>/state.json`, ou demande-le au builder.

## Cartographie de l'application (`docs/architecture/`)

Contrairement à `.ai/`, la cartographie est commitée avec le code. Le dossier est configurable dans la section **AI delivery workflow** de `AGENTS.md` (`docs/architecture/` par défaut).

| Page | Contenu |
|---|---|
| `README.md` | Index, points « À confirmer » |
| `context.md`, `containers.md` | C4 niveaux 1 et 2 |
| `components.md` | Modules, couches, dépendances autorisées |
| `integrations.md` | API externes et diagrammes de séquence des flux critiques |
| `data.md`, `security.md`, `quality.md` | Données, sécurité, qualités (performance, fiabilité, observabilité) |
| `glossary.md` | Glossaire métier |
| `decisions/` | ADR numérotés |

Règles : chaque affirmation cite le fichier du code dont elle vient, ce qui n'est pas prouvé est marqué « À confirmer », les schémas sont en Mermaid, et aucun secret ni URL interne n'y figure.

Cycle de vie : l'architect lit la cartographie et regarde ce qui a changé depuis le dernier commit de chaque page ; le plan liste l'**impact sur la doc** (ou `none` avec la raison, par exemple un changement de libellé) ; l'implementer met la doc à jour dans la même PR ; le reviewer signale en `major` un changement d'intégration, de flux, de règle de sécurité, de stockage ou de composant sans mise à jour. Hors workflow, `architecture-mapping --refresh` rattrape les écarts. Aucun hook ne contrôle la doc : c'est le rôle du reviewer.

## Garde-fous (hooks)

Les hooks n'agissent que dans un dépôt où un workflow est actif (`.ai/current` présent, `phase` différent de `done`).

| Règle | Comportement |
|---|---|
| Contrôle de review (`Stop`) | En phase `build` ou `feedback`, l'agent ne peut pas terminer son tour s'il reste des modifications non commitées, ou si `review.md` est absent, périmé (SHA ≠ HEAD) ou non `APPROVED`. Il peut s'arrêter en passant `phase` à `escalated`. Un seul blocage consécutif (`stop_hook_active`). |
| Création de PR | `repo_pull_request_write` `create` exige `phase: build`, `isDraft: true`, un arbre propre, une review `APPROVED` du HEAD, le HEAD poussé sur `origin/<branch>`, la bonne source et la bonne cible, et une description de 4000 caractères maximum. Ensuite, **confirmation**. |
| Actions réservées à toi | Auto-complete, contournement des policies, publication de la draft (`isDraft: false`), abandon, vote et changement de relecteurs sont refusés. |
| Commit sans test | En phase `build` ou `feedback`, un `git commit` qui modifie du code sans aucun fichier de test (skill `red-green-refactor`) demande **ta confirmation** : toi seul acceptes un lot sans test, par exemple sur un projet legacy sans tests unitaires ni E2E. |
| Push | `git push` demande confirmation ; force push, suppression de branche et `--mirror` sont refusés. |
| Écritures Azure DevOps | Seules la PR draft et les commentaires de PR sont autorisés. Les commentaires doivent commencer par `🤖`, puisqu'ils sont publiés sous ton identité. Les work items ne sont jamais modifiés. |
| az CLI | Les écritures `az repos pr`, `az boards work-item` et `az devops invoke` sont refusées : Azure DevOps passe uniquement par le MCP. |

## Fichiers de travail (`.ai/`, jamais commités)

| Fichier | Contenu |
|---|---|
| `.ai/current` | Slug actif |
| `.ai/<slug>/state.json` | Phase, parcours (fast, standard, feature), branches, work item, PR, itérations de review, langue |
| `.ai/<slug>/brief.md` | Besoin validé |
| `.ai/<slug>/plan.md` | Plan découpé en lots |
| `.ai/<slug>/review.md` | Dernière review, avec dans l'en-tête `verdict`, `reviewed_sha`, `base_sha` et `iteration` |
| `.ai/<slug>/pr-description.md` | Description de la PR draft |
| `.ai/<slug>/feedback.md` | Classement des commentaires de PR |

## Modèles

| Agent | Modèle (avec repli) |
|---|---|
| challenger, architect | Claude Opus 5.5 (Claude Opus 5) |
| builder, implementer | Claude Sonnet 5.5 (Claude Sonnet 5) |
| reviewer | GPT-6.1 Sol (GPT-6 Astra) : autre famille que l'implementer, donc moins d'angles morts partagés |

En Local, le champ `model` de l'en-tête d'un agent s'applique aux subagents. Pour les agents interactifs, c'est le `model` du handoff qui choisit le modèle au moment du passage, et le challenger utilise le modèle sélectionné dans le sélecteur. Les noms doivent correspondre exactement à ceux du sélecteur de modèles, au format `<nom> (copilot)`.

## Portabilité vers le harness Copilot

- Le champ `handoffs` est ignoré : il suffit de changer d'agent à la main ; les fichiers `.ai/` portent le contexte d'une étape à l'autre.
- Les hooks sont déclarés avec des noms d'événements PascalCase et les clés `bash` et `powershell`, reconnues par les deux harnesses. Ils lisent les deux formats d'entrée (`tool_name`/`tool_input` et `toolName`/`toolArgs`) et écrivent leurs décisions dans les deux formats de sortie.
- Aucun hook n'est déclaré dans l'en-tête des agents. Le harness Copilot ignore aujourd'hui ces hooks pour les agents fournis par un plugin ; ici, ils sont tous au niveau du plugin.

## Tests

```powershell
cd tests
python -m unittest
```

La CI `azure-pipelines.yml` lance ces tests sur Ubuntu (Python 3.9 et 3.12), Windows et macOS (Python 3.12) à chaque push sur `main`. Pour la lancer sur les PR, ajoute ce pipeline comme **build validation** dans les policies de la branche `main` (Azure Repos ignore la clé `pr`).

Couvert par les tests : décisions des hooks (payloads Local et Copilot), contrôle de review sur de vrais dépôts git temporaires, script d'onboarding (dont le squelette de la cartographie), cohérence des skills, des agents et des hooks.

## Points à vérifier au premier essai

- La doc VS Code qualifie les hooks du harness Local de « legacy ». Ils fonctionnent, mais l'éditeur évolue vers le harness Copilot.
- Ouvre l'Agent Debug Log pour vérifier les noms réels des outils (terminal, outils MCP `ado-*`). Les hooks reconnaissent les outils Azure DevOps à leur nom : `repo_pull_request_write`, `repo_pull_request_thread_write`, tout autre outil d'écriture (`*_write`, `repo_create_branch`, `wiki_upsert_page`, ajout ou liaison de pièces jointes de work item), quel que soit le préfixe du serveur. Ils analysent aussi comme commande shell tout paramètre `command`, y compris un `git` appelé par son chemin complet ou via `cmd /c`, `bash -c`, `pwsh -Command`.
- Si un handoff ou un modèle n'est pas trouvé, ajuste le nom dans l'en-tête de l'agent.
