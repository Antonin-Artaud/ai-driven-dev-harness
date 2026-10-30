| Élément | Rôle |
|---|---|
| `challenger` (agent) | Challenge le besoin, trie la demande (fast, standard, feature) et produit `brief.md` |
| `architect` (agent) | Part de la cartographie `docs/architecture/`, vérifie dans le code, compare des options, conteste ta vision et produit `plan.md` découpé en lots, avec l'impact sur la doc |
| `builder` (agent) | Orchestre implementer et reviewer, pousse la branche, ouvre la PR draft et traite les commentaires de PR |
| `implementer` (subagent caché) | Implémente un lot : tests, code, mise à jour de la doc d'architecture, un commit |
| `reviewer` (subagent caché) | Relit `merge-base..HEAD` en appliquant d'abord les skills du projet, vérifie que la doc d'architecture suit le code, puis écrit `review.md` |
| `skills/` | `delivery-workflow`, `business-challenge`, `solution-design`, `plan-execution`, `code-review`, `pr-feedback`, `azure-devops`, `project-onboarding`, `architecture-mapping` |
| `com.github.copilot/hooks/hooks.json` | Garde-fous déterministes `PreToolUse` et `Stop` (scripts Python, bibliothèque standard uniquement) |

Les agents restent légers. Toute la méthode vit dans les skills, un format portable, et chaque projet garde la main grâce à ses propres skills : **les skills du projet passent avant ceux du plugin**.