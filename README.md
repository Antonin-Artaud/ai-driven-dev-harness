# ai-delivery-workflow

Plugin d'agents (format [Agent Plugins 1.0](https://agent-plugins.org/)) pour VS Code et GitHub Copilot. Il transforme une demande (prompt, spec ou work item Azure DevOps) en **PR draft Azure Repos** relue. Le parcours passe par un challenge du besoin métier, un plan d'architecture qui part de la cartographie du projet, une implémentation qui suit le plan et met cette cartographie à jour, et une review indépendante fondée sur les skills du projet.

```
challenger ─▶ architect ─▶ builder ─▶ PR draft ─▶ ta revue dans Azure DevOps ─▶ builder (retours) ─▶ tu publies
 brief.md      plan.md      ├─ implementer (subagent, un lot de code à la fois)
               │            ├─ ui-ux-designer (subagent, un lot UI à la fois)
               │            └─ reviewer (subagent indépendant, autre famille de modèles)
               ├─ security-architect (subagent si la sécurité est en jeu : security.md)
               └─ performance-architect (subagent si la performance est en jeu : performance.md)
```

Chaque passage entre agents interactifs est un **handoff** (`send: false`) : tu valides le brief ou le plan, puis tu cliques.

## Contenu

| Élément | Rôle |
|---|---|
| `challenger` (agent) | Challenge le besoin, trie la demande (fast, standard, feature) et produit `brief.md` |
| `architect` (agent) | Part de la cartographie `docs/architecture/`, vérifie dans le code, compare des options, conteste ta vision et produit `plan.md` découpé en lots, avec l'impact sur la doc |
| `security-architect` (agent et subagent de l'architect) | Modélise les menaces (STRIDE) et écrit `security.md` : mitigations, exigences `SEC-n` par lot, risque résiduel. Ne code pas. Consulté par l'architect quand le brief ou le changement touche la sécurité, ou lancé directement par toi pour analyser un plan |
| `performance-architect` (agent et subagent de l'architect) | Fixe les budgets, repère les chemins chauds et les volumes, prévoit les mesures et écrit `performance.md` avec des exigences `PERF-n` par lot. Ne code pas. Même mode de consultation |
| `builder` (agent) | Orchestre implementer, ui-ux-designer et reviewer, pousse la branche, ouvre la PR draft et traite les commentaires de PR |
| `implementer` (subagent caché) | Implémente un lot en TDD (red-green-refactor) : tests, code, mise à jour de la doc d'architecture, un commit |
| `ui-ux-designer` (subagent caché) | Implémente les lots marqués `Kind: ui` : design system du projet d'abord, accessibilité WCAG 2.1 AA, tous les états (chargement, vide, erreur…), responsive, i18n, preuves visuelles quand le projet sait en produire |
| `reviewer` (subagent caché) | Relit `merge-base..HEAD` en appliquant d'abord les skills du projet, vérifie les exigences `SEC-n` et `PERF-n` du plan, la checklist UI des lots UI et la doc d'architecture, puis écrit `review.md` |
| `skills/` | `delivery-workflow`, `business-challenge`, `solution-design`, `security-design`, `performance-design`, `dotnet-performance`, `plan-execution`, `red-green-refactor`, `ui-ux-design`, `code-review`, `pr-feedback`, `azure-devops`, `project-onboarding`, `architecture-mapping` |
| `com.github.copilot/hooks/hooks.json` | Garde-fous déterministes `UserPromptSubmit`, `PreToolUse`, `SubagentStart`, `SubagentStop` et `Stop` (scripts Python, bibliothèque standard uniquement) |

### Projets .NET

Sur un projet .NET, le skill `dotnet-performance` vise le code le plus économe en mémoire et le plus performant possible, en deux niveaux. Le **niveau A** s'applique à tout le code .NET écrit : lectures EF Core sans suivi (`AsNoTracking` ou `QueryTrackingBehavior.NoTracking` par défaut), projections, pas de N+1, pagination keyset, `ExecuteUpdate`/`ExecuteDelete`, async de bout en bout, logs et JSON générés par source, analyseurs CA18xx. Le **niveau B** s'applique aux chemins chauds couverts par une exigence `PERF-n` : `Span<T>`, `Memory<T>`, `stackalloc`, `ArrayPool<T>`, `ValueTask`, `SearchValues`, Pipelines, SIMD… avec un benchmark BenchmarkDotNet (`[MemoryDiagnoser]`) avant/après. Chaque règle cite sa source Microsoft Learn et la version requise. L'onboarding ajoute le serveur MCP **`ms-learn`** (documentation Microsoft Learn, sans authentification) pour que les agents vérifient les API dans la documentation officielle.

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

Remplace `<dossier-des-plugins>` par le dossier de ton choix (par exemple `C:/Users/<toi>/source`).

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
6. Démarre `ado-read` et `ado-write` depuis la vue MCP (connexion Entra), ainsi que `ms-learn` sur un projet .NET (détecté par un `*.sln`, `*.slnx`, `*.csproj` ou `global.json`, ou forcé avec `--dotnet`).

## Utilisation

1. Sélectionne l'agent **challenger** et donne ta demande, ou un ID ou une URL de work item.
2. Réponds aux questions (5 maximum par tour, chacune avec une réponse par défaut) et valide `brief.md`. Clique ensuite sur **Design the solution**, ou sur **Fast path** pour un petit changement.
3. L'**architect** propose des options, conteste ta vision et produit `plan.md`. Valide-le, puis clique sur **Implement the plan**. Selon le brief (ligne `Concerns`), il consulte le **security-architect** et le **performance-architect**, intègre leurs exigences dans les lots et marque les lots UI (`Kind: ui`), confiés ensuite à l'**ui-ux-designer**.
4. Le **builder** fait implémenter les lots et relire la branche (2 itérations de review au maximum, sinon il te passe la main). Il pousse la branche, puis crée la PR draft liée au work item ; tu confirmes chacune de ces deux actions. Il archive ensuite le brief et le plan sur la PR dans le fil **🤖 Workflow record**.
5. Relis la PR draft dans Azure DevOps et commente.
6. De retour dans VS Code, clique sur **Address PR feedback**. Le builder passe en phase `triage`, classe les commentaires et propose des **learnings** : les règles réutilisables révélées par tes commentaires, à ajouter aux skills du projet, à ses instructions ou à `AGENTS.md`. **Tu valides le classement et chaque learning**, puis il corrige, commite les learnings à part (`docs(agents): …`), fait relire et répond à chaque fil. Un commentaire fait une fois n'a plus à être refait à la PR suivante.
7. Publie la PR toi-même, puis demande au builder de **clore** le workflow (ou lance `python <plugin>/scripts/close_workflow.py --repo .`) : `phase` passe à `done`, `.ai/<slug>/` est archivé dans `.ai/archive/` et `.ai/current` est supprimé. Tu confirmes la clôture. Le builder t'affiche ensuite le **coût par agent** (ci-dessous).

## Coût par agent

À la clôture, le builder affiche un tableau : pour chaque agent (challenger, architect, builder et chaque subagent), le modèle, le nombre d'exécutions, la durée, les tokens (entrée, cache lu, cache écrit, sortie) et une **estimation en crédits GitHub AI** (1 crédit = 0,01 $), suivi du total. Tu peux aussi l'afficher à tout moment, y compris pour un workflow archivé :

```powershell
python <plugin>/scripts/usage_report.py --repo .                 # workflow actif
python <plugin>/scripts/usage_report.py --repo . --slug <slug>   # workflow archivé
python <plugin>/scripts/usage_report.py --repo . --json          # même résumé en JSON
```

D'où viennent les chiffres : ni VS Code ni Copilot ne donnent la consommation dans les hooks, et GitHub ne détaille pas les crédits par requête. Les hooks lisent donc le transcript de la session (`transcript_path`) et attribuent les nouvelles requêtes à l'agent qui tournait : au subagent entre son `SubagentStart` et son `SubagentStop`, à l'agent principal de la phase sinon. Le tout est écrit dans `.ai/<slug>/usage.json` (hooks seuls). Les crédits sont calculés avec les tarifs publics de [GitHub](https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing), recopiés dans `scripts/hooks/pricing.json` (date de relevé dans le fichier).

Limites :
- C'est une **estimation**, pas ta facture : le décompte exact est dans GitHub, *Billing > Metered usage*.
- Le format du transcript n'est pas une API stable de VS Code. S'il ne contient pas de compteurs de tokens, le tableau l'indique et n'affiche que les exécutions et les durées, sans coût inventé. Lance alors `usage_report.py --probe <chemin du transcript>` : il liste la structure du fichier (les clés, jamais les valeurs) pour adapter le lecteur.
- Un modèle absent de `pricing.json` (par exemple Gemini 3.1 Pro, non listé par GitHub) apparaît en `n/d` et le total devient un minimum (`≥`).
- Des subagents lancés en parallèle partagent le transcript : leur répartition est approximative.

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

Les hooks n'agissent que dans un dépôt où un workflow est actif (`.ai/current` présent, `phase` différent de `done`). La liste complète et à jour des règles est dans [la référence des garde-fous](skills/delivery-workflow/references/gates.md) ; en résumé :

| Règle | Comportement |
|---|---|
| État du workflow | Chaque modification de `state.json` est simulée puis vérifiée : transitions autorisées, brief et plan validés par un message de ta part après leur dernière modification, review `APPROVED` avant `pr-open`, au plus 2 itérations de review, sortie d'`escalated` seulement après ta réponse. `done` passe uniquement par l'étape de clôture. |
| Rôles | Seul le reviewer écrit `review.md` (et rien d'autre) ; l'implementer n'écrit jamais sous `.ai/` ; l'agent principal te demande confirmation avant d'écrire hors de `.ai/`. Les fichiers des hooks (`.hooks.json`, `log.jsonl`, marqueurs) ne sont jamais écrits par un agent. |
| Contrôles de fin de tour (`Stop`) | En `build` et `feedback`, pas de fin de tour avec du code non commité ou non relu (`APPROVED` du HEAD) ; en `pr-open`, pas avant le fil **🤖 Workflow record**. Au plus 3 blocages consécutifs. |
| Commit sans test | En phase `build` ou `feedback`, un `git commit` qui modifie du code sans aucun fichier de test (skill `red-green-refactor`) demande **ta confirmation** : toi seul acceptes un lot sans test, par exemple sur un projet legacy sans tests unitaires ni E2E. |
| Push | `git push` demande confirmation et ne vise que `ai/<slug>` ; force push, suppression, `--mirror`, `--all` et toute autre destination sont refusés, y compris via alias, `sudo`, `env`, `timeout`, `xargs`, `eval`, `python -c`, variables. |
| Azure DevOps | Outils MCP en lecture autorisés (liste vérifiée) ; création de la PR draft contrôlée puis confirmée ; mise à jour limitée au titre et à la description de la PR du workflow ; commentaires préfixés `🤖` ; tout le reste est refusé. `az rest`, les écritures `az` et les appels HTTP directs à Azure DevOps sont refusés. |
| Journal | Chaque décision est ajoutée à `.ai/<slug>/log.jsonl` (secrets masqués). |

## Fichiers de travail (`.ai/`, jamais commités)

| Fichier | Contenu |
|---|---|
| `.ai/current` | Slug actif |
| `.ai/<slug>/state.json` | Phase, parcours, branches, work item, validations du brief et du plan, lots faits, PR, fil d'archivage, itérations de review, escalade, langue |
| `.ai/<slug>/brief.md`, `plan.md` | Besoin validé, plan découpé en lots |
| `.ai/<slug>/review.md` | Dernière review, avec dans l'en-tête `verdict`, `reviewed_sha`, `base_sha` et `iteration` |
| `.ai/<slug>/pr-description.md`, `feedback.md` | Description de la PR draft, classement des commentaires et learnings |
| `.ai/<slug>/.hooks.json`, `log.jsonl` | Écrits par les hooks seuls : heartbeat, heure de ton dernier message, journal des décisions |
| `.ai/<slug>/usage.json` | Écrit par les hooks seuls : tokens par agent et par modèle, exécutions, durées (voir « Coût par agent ») |
| `.ai/<slug>/.reviewer-active`, `.implementer-active` | Marqueurs écrits par les hooks pendant qu'un subagent tourne |
| `.ai/archive/<slug>/` | Workflows clos |

Ces fichiers restent locaux : le brief et le plan validés survivent à la PR grâce au fil **🤖 Workflow record**, mis à jour en réponse quand le plan change.

## Modèles

| Agent | Modèle (avec repli) |
|---|---|
| challenger, architect, security-architect, performance-architect | Claude Opus 5.5 (Claude Opus 5) |
| builder, implementer, ui-ux-designer | Claude Sonnet 5.5 (Claude Sonnet 5) |
| reviewer | GPT-6.1 Sol (GPT-6 Astra, puis Gemini 3.1 Pro) : autre famille que l'implementer et l'ui-ux-designer, donc moins d'angles morts partagés. Le nom Gemini est **à confirmer** dans ton sélecteur de modèles. |

En Local, le champ `model` de l'en-tête d'un agent s'applique aux subagents. Pour les agents interactifs, c'est le `model` du handoff (présent sur chaque handoff, y compris **Address PR feedback**) qui choisit le modèle au moment du passage, et le challenger utilise le modèle sélectionné dans le sélecteur. Les noms doivent correspondre exactement à ceux du sélecteur de modèles, au format `<nom> (copilot)`.

## Portabilité vers le harness Copilot

- Le champ `handoffs` est ignoré : il suffit de changer d'agent à la main ; les fichiers `.ai/` portent le contexte d'une étape à l'autre.
- Les hooks sont déclarés avec des noms d'événements PascalCase et les clés `bash` et `powershell`, reconnues par les deux harnesses. Ils lisent les deux formats d'entrée (`tool_name`/`tool_input` et `toolName`/`toolArgs`) et écrivent leurs décisions dans les deux formats de sortie.
- Aucun hook n'est déclaré dans l'en-tête des agents. Le harness Copilot ignore aujourd'hui ces hooks pour les agents fournis par un plugin ; ici, ils sont tous au niveau du plugin.

## Mise à jour

1. Termine ou clos les workflows en cours avant de changer de version : un `state.json` écrit par une version antérieure peut ne pas respecter les nouvelles règles de transition.
2. Clone local : `git pull` dans le dossier du plugin, puis recharge la fenêtre VS Code. Installation depuis la source : réinstalle le plugin.
3. Lis le [CHANGELOG](CHANGELOG.md). En passant de 0.2.0 à 0.3.0 : les validations du brief et du plan sont désormais des champs de `state.json` (`brief_validated`, `plan_validated`), la clôture passe par `scripts/close_workflow.py`, et un nouveau hook `UserPromptSubmit` est déclaré.
4. Vérifie que la version affichée dans `.ai/<slug>/.hooks.json` (`heartbeat.version`) est la nouvelle.

## Dépannage

| Symptôme | Cause probable et solution |
|---|---|
| Le builder refuse de construire : heartbeat absent ou ancien | Les hooks ne tournent pas : active `chat.useHooks`, approuve le workspace, vérifie `python`/`python3` dans le PATH, puis envoie un message et relance. |
| `state.json` : « not an allowed transition » ou « wait for their validation » | Le hook protège les étapes : valide explicitement le brief ou le plan dans un message, sans que l'agent ne modifie le fichier ensuite. En cas de blocage, demande une escalade, puis indique la phase voulue. |
| L'agent principal demande confirmation pour chaque fichier | Normal hors `escalated` : l'agent principal ne code pas. Si cela arrive pendant que l'implementer tourne, l'hôte n'envoie ni `agent_type` ni `agentName` (voir « Points à vérifier »). |
| Un `git push` est refusé | La destination n'est pas `ai/<slug>`, une option force ou suppression est présente, ou la branche suivie pointe ailleurs (`git branch --unset-upstream`). |
| Un fil de PR ne change pas de statut | Chaque changement de statut te demande confirmation ; le fil d'archivage ne change jamais de statut. |
| Le tableau des coûts affiche `n/d` partout | Le transcript de VS Code ne contient pas de compteurs de tokens reconnus : lance `usage_report.py --probe <transcript>` (le chemin est dans `usage.json`, clé `transcripts`) et ouvre une demande avec sa sortie. |
| Comprendre une décision d'un hook | Lis `.ai/<slug>/log.jsonl` : une ligne par décision, avec la raison, le HEAD et la phase. |
| Workflow terminé mais les hooks agissent encore | Clos-le : `python <plugin>/scripts/close_workflow.py --repo .` |
| `onboard.py` sort avec le code 3 | `ado-read` ou `ado-write` existent déjà avec une autre définition : compare, puis relance avec `--force`. |

## Tests

```powershell
cd tests
python -m unittest
```

La CI `azure-pipelines.yml` lance ces tests sur Ubuntu (Python 3.9 et 3.12), Windows et macOS (Python 3.12) à chaque push sur `main`, plus un job de qualité : `ruff`, `mypy` et la couverture des scripts avec un seuil minimal. Pour la lancer sur les PR, ajoute ce pipeline comme **build validation** dans les policies de la branche `main` (Azure Repos ignore la clé `pr`).

Couvert par les tests : décisions des hooks (payloads Local et Copilot), corpus de contournements (`tests/test_bypass_corpus.py`), transitions de `state.json`, clôture, journal, exécution des commandes de `hooks.json` dans un vrai shell, alias git, propriété de `review.md` et marqueur du reviewer, contrôles de review et d'archivage sur de vrais dépôts git temporaires, script d'onboarding (dont le squelette de la cartographie), cohérence des skills, des agents et des hooks.

## Points à vérifier au premier essai

- La doc VS Code qualifie les hooks du harness Local de « legacy ». Ils fonctionnent, mais l'éditeur évolue vers le harness Copilot.
- Ouvre l'Agent Debug Log pour vérifier les noms réels des outils (terminal, édition de fichiers, outils MCP `ado-*`). Les hooks reconnaissent les outils Azure DevOps à leur nom, sur un serveur dont le nom contient `ado`, `azure`, `devops` ou `vsts` (ou sans préfixe) ; ils simulent les éditions de fichiers faites avec `create_file`, `replace_string_in_file`, `multi_replace_string_in_file` et `apply_patch`, et refusent sur `state.json` les autres outils d'édition.
- Si un handoff ou un modèle n'est pas trouvé, ajuste le nom dans l'en-tête de l'agent.
- Vérifie dans l'Agent Debug Log que `SubagentStart` reçoit bien `agentName: reviewer` (et `implementer`), ou que les appels d'outils des subagents portent `agent_type`. Sinon, l'écriture de `review.md` est refusée au reviewer lui-même, et chaque écriture de l'implementer te demande confirmation.
- Vérifie que `UserPromptSubmit` est bien reçu : après ton premier message dans un workflow actif, `.ai/<slug>/.hooks.json` doit contenir `user_prompt_at`. Sans lui, les contrôles « tu as répondu après la modification » sont ignorés.

## Limites des garde-fous

Les hooks protègent contre les erreurs et les dérives d'un agent, pas contre un contournement délibéré : un script écrit sur disque puis exécuté, une variable `GIT_CONFIG_*` ou un serveur MCP Azure DevOps enregistré sous un nom inattendu peuvent passer. Sans workflow actif, aucune règle ne s'applique. La review humaine de la PR draft reste le contrôle final. Les limites restantes sont listées dans [docs/architecture/security.md](docs/architecture/security.md#known-gaps).

## Licence

Aucune licence n'est encore choisie : c'est une décision du propriétaire du dépôt (point ouvert).
