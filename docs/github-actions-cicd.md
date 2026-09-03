# GitHub Actions CI/CD for dev

This runbook describes the GitHub Actions setup for the development environment.
Commands in this document are intentionally manual: GitHub Actions never runs
`terraform apply`, and the ingestion job is never executed by a workflow.

## Trust boundary

The Workload Identity Federation provider trusts only the upstream repository:

```text
repository: teamdigitale/dati-semantic-schema-assistant-cms
repository_id: 1288130374
repository_owner_id: 25081492
branch: refs/heads/main
events: push, workflow_dispatch
workflows: deploy-dev.yml, deploy-ingestion-dev.yml
```

The numeric identifiers are checked together with the repository name so a
renamed or deleted GitHub repository cannot silently inherit this trust. The
`workflow_ref` claim also prevents other workflows in the same repository from
exchanging their OIDC tokens for Google Cloud credentials.

Pull request jobs have only `contents: read`. They do not request a GitHub OIDC
token and cannot authenticate to Google Cloud, including pull requests opened
from another fork.

## Workflows

- `.github/workflows/ci.yml` validates Python, Angular, Terraform and changed
  Docker images. It never deploys.
- `.github/workflows/deploy-dev.yml` runs the CI gate on pushes to `main`, then
  builds and deploys only the affected web and agent services. An ingestion
  change publishes its image but leaves the Cloud Run Job unchanged.
- `.github/workflows/deploy-ingestion-dev.yml` manually points the ingestion
  Job to an image that was already published from a `main` commit. It does not
  execute the Job.

Images use `sha-<full-commit-sha>` tags. A rerun reuses an existing tag instead
of moving it, and Cloud Run is updated with the resolved image digest.

## 1. Review and apply the Terraform bootstrap

Use the existing local `dev.tfvars`. Run these commands yourself from the
repository root:

```powershell
terraform fmt -check -recursive infra
terraform -chdir=infra\envs\dev init
terraform -chdir=infra\envs\dev validate
terraform -chdir=infra\envs\dev plan -var-file=dev.tfvars -out=cicd-dev.tfplan
terraform -chdir=infra\envs\dev show -no-color cicd-dev.tfplan
```

The plan should only add or update GitHub identity resources and IAM grants.
When transferring trust from a fork, an IAM member binding can be replaced to
use the upstream repository id. Stop if the plan replaces or deletes an
existing bucket, Firestore database, Artifact Registry repository, Cloud Run
service or Cloud Run Job.

Apply only the reviewed saved plan:

```powershell
terraform -chdir=infra\envs\dev apply cicd-dev.tfplan
```

Workload Identity Federation and new IAM grants can take a few minutes to
propagate after the apply.

## 2. Configure repository variables

Read the two non-sensitive Terraform outputs:

```powershell
terraform -chdir=infra\envs\dev output -raw github_actions_workload_identity_provider
terraform -chdir=infra\envs\dev output -raw github_actions_service_account_email
```

In `teamdigitale/dati-semantic-schema-assistant-cms`, open **Settings > Secrets
and variables > Actions > Variables** and create these repository variables:

| Variable | Value |
| --- | --- |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Value of `github_actions_workload_identity_provider` |
| `GCP_CICD_SERVICE_ACCOUNT` | Value of `github_actions_service_account_email` |

These values are resource identifiers, not credentials. Do not create a
`GCP_CREDENTIALS` secret or a Google service account JSON key.

## 3. Protect the dev environment

Create a GitHub Environment named `dev` and configure, where supported by the
repository plan:

- deployment branch restricted to `main`;
- at least one required reviewer;
- prevent self-review;
- do not allow administrators to bypass protection rules.

The deploy and image publication jobs reference this environment. CI jobs do
not, so pull request feedback remains automatic and cannot access deploy
credentials.

## 4. Protect main

Configure a branch ruleset for `main` with pull requests required, force pushes
and deletion disabled, review conversations resolved, and these required CI
checks:

- Python quality and tests;
- Angular build and tests;
- Terraform static validation;
- changed Docker image verification.

Direct pushes should be restricted to the smallest possible maintainer group.

## 5. Test the pipeline

1. Open a pull request targeting the upstream repository and verify that CI
   completes without a deploy.
2. Merge the pull request into `main`.
3. Review the pending `dev` environment deployment.
4. Confirm that only changed services receive a new revision.
5. For an ingestion change, confirm that the image is published but the Job
   image is unchanged.
6. Run **Deploy ingestion image to dev** manually when that image is approved.

Executing `schema-assistant-ingestion-dev` remains a separate manual operator
action outside GitHub Actions.

## Cloud Build fallback

The existing Cloud Build files remain available for manual recovery. Always
override `_IMAGE` with a unique commit tag rather than using the legacy `:dev`
default, for example:

```powershell
$SHA = git rev-parse HEAD
gcloud builds submit `
  --project istat-ndc-schema-ass-cms-dev `
  --region europe-west8 `
  --config cloudbuild.agent.yaml `
  --substitutions "_IMAGE=europe-west8-docker.pkg.dev/istat-ndc-schema-ass-cms-dev/schema-assistant/agent:sha-$SHA" `
  .
```

Run any `gcloud run ... update` command separately and only for the selected
service or Job. Never use a global deployment command.

## Trust transfer from the validation fork

The pipeline was validated in a fork before enabling upstream deployment.
Applying this configuration transfers deployment trust to the upstream
repository; the validation fork can continue to run CI but can no longer
exchange GitHub OIDC tokens for Google Cloud credentials.
