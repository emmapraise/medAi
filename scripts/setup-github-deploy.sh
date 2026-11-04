#!/usr/bin/env bash
# One-time Google Cloud setup so GitHub Actions can deploy the `medai` Cloud Run service WITHOUT a stored key
# (Workload Identity Federation: GitHub proves who it is with a short-lived token).
#
# It changes IAM in your Google project, so run it yourself, once:
#     DRY_RUN=1 bash scripts/setup-github-deploy.sh     # only prints what it would do
#     bash scripts/setup-github-deploy.sh               # does it
#
# What it creates, and how little each part may do:
#   - a service account `github-deployer` that can deploy the ONE service `medai` (not the other Cloud Run
#     services in the project), push to ONE image repository, and run revisions as the service's own identity;
#   - a Workload Identity pool that trusts tokens from ONE GitHub repository ($REPO), nobody else.
set -euo pipefail

PROJECT=${PROJECT:-oneevent-485310}
REGION=${REGION:-europe-west1}
SERVICE=${SERVICE:-medai}
REPO=${REPO:-emmapraise/medAi}           # GitHub owner/name; the case must match exactly
AR_REPO=${AR_REPO:-cloud-run-source-deploy}
SA_NAME=github-deployer
POOL=github
PROVIDER=github-actions

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
SA="$SA_NAME@$PROJECT.iam.gserviceaccount.com"
RUNTIME_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"   # the identity the service runs as
PROVIDER_NAME="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER"

run() { if [ "${DRY_RUN:-}" = 1 ]; then echo "+ $*"; else "$@"; fi; }
# Same, but hides gcloud's long policy printout in a real run (a dry run still shows the command).
grant() { if [ "${DRY_RUN:-}" = 1 ]; then echo "+ $*"; else "$@" > /dev/null; fi; }
# Re-running is safe: things that already exist are reported and skipped. Read the message if it is something else.
try() { run "$@" || echo "  (not done: it probably exists already; if not, read the error above)"; }

echo "Project $PROJECT ($PROJECT_NUMBER), service $SERVICE in $REGION, GitHub repo $REPO"
[ "${DRY_RUN:-}" = 1 ] && echo "DRY RUN: nothing below is executed."

echo "1/5 enable the APIs for keyless login"
run gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project "$PROJECT"

echo "2/5 service account"
try gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT" --display-name "GitHub Actions deployer"

echo "3/5 what that account may do (each grant is limited to one resource)"
grant gcloud run services add-iam-policy-binding "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --member "serviceAccount:$SA" --role roles/run.developer --quiet
grant gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" --project "$PROJECT" --location "$REGION" \
  --member "serviceAccount:$SA" --role roles/artifactregistry.writer --quiet
grant gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --project "$PROJECT" \
  --member "serviceAccount:$SA" --role roles/iam.serviceAccountUser --quiet

echo "4/5 trust GitHub tokens, but only from $REPO"
try gcloud iam workload-identity-pools create "$POOL" --project "$PROJECT" --location global --display-name "GitHub Actions"
try gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --project "$PROJECT" --location global \
  --workload-identity-pool "$POOL" --issuer-uri "https://token.actions.githubusercontent.com" \
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition "assertion.repository == '$REPO'"
grant gcloud iam service-accounts add-iam-policy-binding "$SA" --project "$PROJECT" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$REPO" \
  --quiet

echo "5/5 tell the GitHub workflow where to log in (two repository VARIABLES; they are IDs, not secrets)"
if command -v gh > /dev/null; then
  run gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER --repo "$REPO" --body "$PROVIDER_NAME"
  run gh variable set GCP_SERVICE_ACCOUNT --repo "$REPO" --body "$SA"
else
  echo "gh is not installed. In GitHub: repo > Settings > Secrets and variables > Actions > Variables, add:"
  echo "  GCP_WORKLOAD_IDENTITY_PROVIDER = $PROVIDER_NAME"
  echo "  GCP_SERVICE_ACCOUNT            = $SA"
fi
echo "Done. Push to main (or Actions > CI > Run workflow) to deploy."
