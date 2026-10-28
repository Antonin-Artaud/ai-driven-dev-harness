---
name: azure-devops
description: 'Azure DevOps conventions of the delivery workflow through the remote MCP servers ado-read (read-only work items, repos, wiki) and ado-write (draft PRs and PR comments only): read a work item as a spec, create an Azure Repos draft pull request linked to its work item, write a PR description of at most 4000 characters, post AI comments. Use for Azure DevOps work items, Azure Repos pull requests or PR comment threads.'
---

# Azure DevOps

## Servers and identity

- `ado-read`: the remote Azure DevOps MCP server in read-only mode (`X-MCP-Readonly: true`, toolsets `repos`, `wit` and `wiki`). Use it for every read.
- `ado-write`: the same server restricted to `repo_pull_request_write` and `repo_pull_request_thread_write`. Only the builder uses it.
- The organization, project and repository come from the project contract (`AGENTS.md`).
- Both servers act **with the user's identity**: everything written appears as written by the user, hence the `🤖` marker on workflow comments.
- Never use the az CLI. If the MCP tools are missing or fail (sign-in, network), say so: the challenger asks the user to paste the work item; the builder hands over `pr-description.md` so the user can create the draft PR manually.

## Read a work item (intake)

1. `wit_work_item` with `action: get` and the ID. Extract the type, title, state, description, acceptance criteria (`Microsoft.VSTS.Common.AcceptanceCriteria`), repro steps of bugs (`Microsoft.VSTS.TCM.ReproSteps`), tags, area, iteration, parent and children.
2. `wit_work_item` with `action: list_comments` for the discussion. Read linked work items only when they clarify the scope.
3. Convert the HTML to plain text. In the brief, quote the original acceptance criteria and keep them apart from the ones you propose.
4. Never modify work items: no field update, comment, link, attachment or state change. The only link created by the workflow is the one attached when the draft PR is created.

## Create the draft PR (builder)

The hook checks the preconditions (see the `delivery-workflow` skill): `phase: build`, clean tree, `APPROVED` review of HEAD, HEAD pushed to `origin/<branch>`. Call `repo_pull_request_write` with:

| Parameter | Value |
|---|---|
| `action` | `create` |
| `repositoryId`, `project` | From the project contract |
| `sourceRefName` | `refs/heads/ai/<slug>` (the current branch) |
| `targetRefName` | `refs/heads/<base_branch>` |
| `title` | `<type>(<scope>): <summary>`, following the project conventions |
| `description` | Content of `pr-description.md` (at most 4000 characters) |
| `isDraft` | `true` |
| `workItems` | `state.work_item` as a string, when set |

Never set `autoComplete` or `bypassPolicy`, never publish the draft (`isDraft: false`), abandon it, vote or change the reviewers: the user does that in Azure DevOps.

Write the description from the [PR description template](./assets/pr-description-template.md). The 4000 characters include the Markdown. Summarize, and do not link to `.ai/` files: they are not in the repository.

## PR comments

- The content always starts with `🤖` (the hook rejects anything else). Format: `🤖 AI review — <severity>: <problem>. <reason>. Suggested fix: <fix>.`
- One thread per finding. Anchor it with `filePath` (repository path starting with `/`) and `rightFileStartLine`, plus `rightFileEndLine` and `rightFileEndOffset` for a range; otherwise create a general thread.
- Replies follow the `pr-feedback` skill. Change a thread status only on AI threads.
