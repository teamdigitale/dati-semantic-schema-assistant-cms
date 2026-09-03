# Schema Assistant web frontend

This directory contains the public Angular frontend.

The Dockerfile builds Angular and starts `server.mjs`, a Node server that serves
static assets and forwards `/api/chat` to the private agent.

The browser calls only its own web origin. The server uses its Cloud Run service
account to obtain an identity token and invoke the private agent. Chat history
stays in browser memory and is sent to the agent with each request.

To test the proxy locally, provide an agent URL and identity token:

```powershell
$env:AGENT_SERVICE_URL = 'https://<agent-url>'
$env:AGENT_ID_TOKEN = gcloud auth print-identity-token --audiences=$env:AGENT_SERVICE_URL
$env:FRAME_ANCESTORS = 'https://wp-ndc-dev.apps.cloudpub.testedev.istat.it,https://schema.gov.it'
$env:STATIC_DIR = 'dist/ndc-platform-ai/browser'
npm run start:cloud-run
```

In Cloud Run, Terraform configures `AGENT_SERVICE_URL`. Do not set
`AGENT_ID_TOKEN` in the service; the token is obtained automatically from the
metadata server.

`FRAME_ANCESTORS` is a comma-separated list of HTTPS origins that may embed the
app in an iframe. Only exact origins are accepted, without paths, trailing
slashes, or wildcards. If the variable is empty, CSP uses
`frame-ancestors 'none'`; an invalid configuration prevents the container from
starting. `X-Frame-Options` is not sent because it cannot represent a
multi-origin allowlist; CSP `frame-ancestors` provides the control.
