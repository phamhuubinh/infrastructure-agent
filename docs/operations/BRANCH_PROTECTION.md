# Main branch delivery policy

Issue #136 uses the repository ruleset payload in
[`main-ruleset.json`](../../.github/main-ruleset.json) for
`phamhuubinh/infrastructure-agent`. The file is a reviewed settings payload, not a
workflow: committing it alone does not activate GitHub protection. GitHub settings
and API read-back establish the active state.

## Policy

The `main-offline-ci` ruleset targets only `refs/heads/main`, with active enforcement
and no exclusions or bypass actors. All contributors, including administrators,
must submit changes through PRs. Administrators retain permission to edit repository
settings, but receive no bypass of this rule while it is active.

The minimum PR rule requires zero approving reviews, so it does not impose a second
maintainer requirement. It still requires a PR and successful checks against the
latest base branch (`strict_required_status_checks_policy=true`). No merge queue,
required deployment, signature rule, or merge-method restriction is added.
Force pushes and branch deletion are blocked.

The required contexts are exact check-run names, bound to the GitHub Actions app
(`integration_id=15368`, slug `github-actions`):

| Context | Existing workflow coverage |
| --- | --- |
| `backend` | Python lint, formatting, types, and offline pytest |
| `ui` | UI lint, TypeScript, unit tests, and packaged UI |
| `acceptance-extra` | Generated OpenAPI, architecture, and isolated operations lifecycle |

These jobs come from [`ci.yml`](../../.github/workflows/ci.yml). Their success proves
the corresponding offline checks passed, not live model stability, answer grounding,
or real infrastructure behavior. Smoke/full/stability QA is not a required check or
a CI/acceptance/startup dependency.

## Apply and read back

An authorized repository administrator can apply the payload once, after confirming
there is no existing overlapping rule. Reuse the existing ruleset ID for later
reviewed updates instead of creating duplicates. Do not weaken an active rule to
push directly to `main`; subsequent changes use PRs.

For initial rollout, validate and push the payload/documentation while `main` is
still unprotected, then create the active ruleset. This avoids creating temporary
bypasses. The initial push may trigger the ordinary CI workflow; no manual Actions
dispatch or rerun is needed to verify protection.

```bash
gh api repos/phamhuubinh/infrastructure-agent/rulesets
gh api repos/phamhuubinh/infrastructure-agent/commits/main/check-runs
gh api --method POST repos/phamhuubinh/infrastructure-agent/rulesets \
  --input .github/main-ruleset.json
```

Record the returned ID and use it for `GET /repos/phamhuubinh/infrastructure-agent/rulesets/{id}`.
Verify `enforcement`, `conditions`, the empty `bypass_actors`, all four rule types,
and the three exact context/app pairs against the payload. Then read:

```bash
gh api repos/phamhuubinh/infrastructure-agent/rules/branches/main
gh api repos/phamhuubinh/infrastructure-agent/branches/main
```

The first endpoint lists active rules that apply to `main`. The branch metadata
should report `protected=true`. A file in Git or a successful create response alone
does not replace these read-backs. Check contexts against the actual commit SHA;
an earlier green run does not prove a later head passed. Verification never needs
a dummy commit, fake PR, force push, deletion attempt, or live tool invocation.

If GitHub rejects configuration because the acting account lacks repository
administration write access, preserve the payload for review and leave #136 open
as blocked. Do not claim protection is enabled.

## Evidence before rollout

On 2026-09-07, the authenticated repository API reported admin access, no rulesets,
and `protected=false` for `main`. The three contexts above were completed with
`success` for head `c4ada711e7894b5d56cb82d34ccdb9f2330bff9d` in
[CI run 34140036320](https://github.com/phamhuubinh/infrastructure-agent/actions/runs/34140036320).
The older [run 33972857019](https://github.com/phamhuubinh/infrastructure-agent/actions/runs/33972857019)
referenced in #136 concerns `4bb91b30e6d9f767899763c1b39afce34387677c`, not that head.

GitHub's [ruleset API](https://docs.github.com/en/rest/repos/rules) documents the
settings and read-back endpoints; its [available rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
describe the enforcement semantics.
