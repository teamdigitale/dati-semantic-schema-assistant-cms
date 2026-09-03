#!/usr/bin/env bash
set -euo pipefail

image="${1:?image repository is required}"
dockerfile="${2:?Dockerfile path is required}"
commit_sha="${3:?commit SHA is required}"
output_file="${GITHUB_OUTPUT:-/dev/null}"
tag="sha-${commit_sha}"
tagged_image="${image}:${tag}"

# A rerun reuses the existing commit tag instead of moving it to another digest.
digest="$(
  gcloud artifacts docker images describe "$tagged_image" \
    --format='value(image_summary.digest)' 2>/dev/null || true
)"

if [[ -z "$digest" ]]; then
  echo "Building $tagged_image from $dockerfile"
  docker build \
    --file "$dockerfile" \
    --label "org.opencontainers.image.revision=$commit_sha" \
    --label "org.opencontainers.image.source=${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}" \
    --tag "$tagged_image" \
    .
  docker push "$tagged_image"

  digest="$(
    gcloud artifacts docker images describe "$tagged_image" \
      --format='value(image_summary.digest)'
  )"
else
  echo "Reusing existing immutable commit tag $tagged_image"
fi

if [[ ! "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]; then
  echo "Artifact Registry returned an invalid digest: $digest" >&2
  exit 1
fi

{
  echo "digest=$digest"
  echo "tag=$tag"
  echo "tagged_image=$tagged_image"
  echo "digest_image=${image}@${digest}"
} >> "$output_file"
