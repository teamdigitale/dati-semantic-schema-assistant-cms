#!/usr/bin/env bash
set -euo pipefail

base_sha="${1:?base SHA is required}"
head_sha="${2:?head SHA is required}"
output_file="${GITHUB_OUTPUT:-/dev/null}"

if [[ "$base_sha" =~ ^0+$ ]] || ! git cat-file -e "${base_sha}^{commit}" 2>/dev/null; then
  mapfile -t changed_files < <(git ls-tree -r --name-only "$head_sha")
else
  mapfile -t changed_files < <(git diff --name-only "$base_sha" "$head_sha")
fi

web=false
agent=false
ingestion=false

for path in "${changed_files[@]}"; do
  case "$path" in
    .dockerignore)
      web=true
      agent=true
      ingestion=true
      ;;
    apps/web/*)
      web=true
      ;;
    services/agent/* | src/schema_assistant/agent/* | config/resources.json | config/routing_lexicon.json)
      agent=true
      ;;
    jobs/ingestion/* | src/schema_assistant/ingestion/* | config/entities_config.json)
      ingestion=true
      ;;
    src/schema_assistant/knowledge_base/* | src/schema_assistant/__init__.py | pyproject.toml | uv.lock)
      agent=true
      ingestion=true
      ;;
  esac
done

if [[ "$web" == true || "$agent" == true || "$ingestion" == true ]]; then
  any=true
else
  any=false
fi

{
  echo "web=$web"
  echo "agent=$agent"
  echo "ingestion=$ingestion"
  echo "any=$any"
} >> "$output_file"

echo "Changed files (${#changed_files[@]}):"
printf ' - %s\n' "${changed_files[@]}"
echo "Affected modules: web=$web agent=$agent ingestion=$ingestion"
