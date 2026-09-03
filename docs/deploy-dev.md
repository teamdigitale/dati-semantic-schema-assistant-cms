# Dev deployment runbook

This runbook contains manual operator commands. Terraform owns infrastructure,
IAM, Cloud Run configuration, and Google Cloud services. GitHub Actions is the
normal deployment path; Cloud Build remains a manual fallback.

The GitHub Actions and Workload Identity Federation setup is documented in
`docs/github-actions-cicd.md`. Deployments from `main` use commit-tagged images
and update Cloud Run with the resolved immutable image digest.

## 1. Prerequisites

```powershell
uv --version
gcloud version
terraform version
uv venv .venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv sync --all-extras
gcloud auth login
gcloud auth application-default login
gcloud config set project istat-ndc-schema-ass-cms-dev
```

Enable Service Usage once before the first Terraform run:

```powershell
gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com --project istat-ndc-schema-ass-cms-dev
```

## 2. Configure Terraform

Copy the example file, add your own IAM principal, and keep the resulting file
local. `dev.tfvars` is ignored by Git.

```powershell
Copy-Item infra\envs\dev\dev.tfvars.example infra\envs\dev\dev.tfvars
notepad infra\envs\dev\dev.tfvars
```

```hcl
developer_invokers = [
  "user:your.name@example.com"
]
```

## 3. Plan and apply infrastructure

```powershell
terraform fmt -recursive infra
terraform -chdir=infra\envs\dev init
terraform -chdir=infra\envs\dev validate
terraform -chdir=infra\envs\dev plan -var-file=dev.tfvars -out=dev.tfplan
terraform -chdir=infra\envs\dev apply dev.tfplan
```

Review the saved plan before applying it. If the `(default)` Firestore database
already exists, import it instead of creating it:

```powershell
terraform -chdir=infra\envs\dev import -var-file=dev.tfvars module.foundation.google_firestore_database.default "projects/istat-ndc-schema-ass-cms-dev/databases/(default)"
```

Stop if the plan replaces or deletes an existing bucket, database, Artifact
Registry repository, Cloud Run service, or Cloud Run Job.

## 4. Verify Cloud Run IAM

```powershell
terraform -chdir=infra\envs\dev output
$AGENT_URL = terraform -chdir=infra\envs\dev output -raw agent_url
$TOKEN = gcloud auth print-identity-token --audiences=$AGENT_URL
curl.exe -i -H "Authorization: Bearer $TOKEN" $AGENT_URL/health
curl.exe -i $AGENT_URL/health
```

The authenticated request should succeed. The unauthenticated request should
fail with `401` or `403`.

## 5. Manual application deployment

Use a unique commit tag and update only the selected service:

```powershell
$SHA = git rev-parse HEAD
$IMAGE = "europe-west8-docker.pkg.dev/istat-ndc-schema-ass-cms-dev/schema-assistant/agent:sha-$SHA"
gcloud builds submit --project istat-ndc-schema-ass-cms-dev --region europe-west8 --config cloudbuild.agent.yaml --substitutions "_IMAGE=$IMAGE" .
gcloud run services update schema-assistant-agent-dev --project istat-ndc-schema-ass-cms-dev --region europe-west8 --image $IMAGE
```

For local Docker builds:

```powershell
gcloud auth configure-docker europe-west8-docker.pkg.dev
docker build -f services\agent\Dockerfile -t $IMAGE .
docker push $IMAGE
gcloud run services update schema-assistant-agent-dev --project istat-ndc-schema-ass-cms-dev --region europe-west8 --image $IMAGE
```

The agent defaults to `THINKING_BUDGET=512` and `MAX_OUTPUT_TOKENS=2048`.
With `RAG_ENABLED=true`, it embeds the question, searches Firestore Vector,
and returns sources in the `sources` field. A question is answered only when a
chunk is within `RAG_MAX_DISTANCE=0.45`.

## 6. Knowledge base and ingestion

See `docs/knowledge-base-design.md` for the data model. The manual ingestion
job reads `config/entities_config.json`, clones configured GitHub repositories
into `/tmp`, processes PDF/CSV sources, and writes Cloud Storage and Firestore
data. Upload source documents under `incoming/docs/`; do not bake them into the
Docker image.

```powershell
gcloud builds submit --project istat-ndc-schema-ass-cms-dev --region europe-west8 --config cloudbuild.ingestion.yaml --substitutions "_IMAGE=europe-west8-docker.pkg.dev/istat-ndc-schema-ass-cms-dev/schema-assistant/ingestion:sha-$SHA" .
gcloud run jobs update schema-assistant-ingestion-dev --project istat-ndc-schema-ass-cms-dev --region europe-west8 --image "europe-west8-docker.pkg.dev/istat-ndc-schema-ass-cms-dev/schema-assistant/ingestion:sha-$SHA"
gcloud run jobs execute schema-assistant-ingestion-dev --project istat-ndc-schema-ass-cms-dev --region europe-west8 --wait
```

The job has no scheduler. `source_hash` makes ingestion incremental; sources
left in `processing` are retried. Use `INGESTION_DRY_RUN=true` only for a
temporary no-write test, then restore `false`. PDFs without extractable text
require OCR.

## 7. Public web frontend

The Angular frontend in `apps/web/` runs as a public Cloud Run service. The
agent remains private. The web server obtains an identity token from the Cloud
Run metadata server and proxies `/api/chat`; the browser never receives an IAM
token, and chat history remains in browser memory.

`web_frame_ancestors` accepts exact HTTPS origins only. Do not use wildcards.
Terraform passes the value as `FRAME_ANCESTORS`; an empty value falls back to
`frame-ancestors 'none'`. Verify headers after deployment and test both an
allowed and a disallowed embedding origin. `X-Frame-Options` should be absent
because it cannot express a multi-origin allowlist.

For emergency maintenance, set `COST_STATUS=blocked` on the agent service and
restore `COST_STATUS=green` afterwards. Keep normal configuration in Terraform.
