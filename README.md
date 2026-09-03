# Schema Assistant CMS

Schema Assistant is a retrieval-augmented assistant for semantic data
catalogues. This repository contains the ingestion pipeline, private chat
agent, public Angular frontend, and Google Cloud infrastructure.

## Architecture

```text
Browser -> public Angular web service -> private FastAPI agent
                                      -> Vertex AI
                                      -> Firestore Vector knowledge base
                                      -> Cloud Storage source assets
```

- `apps/web/` contains the Angular application and the server-side proxy for
  `/api/chat`.
- `services/agent/` packages the private FastAPI agent.
- `jobs/ingestion/` packages the manual ingestion job.
- `src/schema_assistant/` contains the shared Python implementation.
- `config/` defines entities, resources, and routing vocabulary.
- `infra/` contains reusable Terraform modules and the dev environment.
- `docs/` contains the deployment, CI/CD, and knowledge base runbooks.

The web service is public, while the agent and ingestion job require IAM
authentication. The browser does not receive Google Cloud credentials, and chat
history is kept in browser memory rather than stored in Firestore.

## Local development

Requirements: Python 3.12, `uv`, Node.js/npm, Terraform, and the Google Cloud
CLI. Set up the Python environment with:

```powershell
uv venv .venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv sync --all-extras
```

Run the Python test suite and quality checks:

```powershell
uv run pytest
uv run ruff check .
uv run mypy src
```

Run the web checks from `apps/web/`:

```powershell
npm ci
npm test -- --watch=false --browsers=ChromeHeadless
npm run build
```

The web proxy can be exercised locally with `AGENT_SERVICE_URL`, an identity
token in `AGENT_ID_TOKEN`, and a comma-separated `FRAME_ANCESTORS` value. See
[`apps/web/README.md`](apps/web/README.md) for the complete example.

## Deployment

Start with the [dev deployment runbook](docs/deploy-dev.md). The normal CI/CD
path is documented in the [GitHub Actions runbook](docs/github-actions-cicd.md).
The [knowledge base design](docs/knowledge-base-design.md) describes storage,
vector search, routing, and incremental ingestion.

GitHub Actions uses Workload Identity Federation and short-lived credentials;
the repository must not contain a Google service-account JSON key. Deployments
use immutable commit-based image tags and digest-pinned Cloud Run revisions.

## Public-repository safety

Do not commit `dev.tfvars`, `.env` files, Terraform state or plans, generated
credentials, customer source documents, or files containing personal data.
Use `infra/envs/dev/dev.tfvars.example` as the local configuration template.
The repository intentionally keeps only synthetic examples and public
configuration in source control.
