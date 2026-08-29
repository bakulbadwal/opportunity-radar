# Cloud Run Jobs deployment — DRAFT

> **DRAFT STATUS — none of the commands below have been executed.** They are
> written against the current gcloud CLI surface but are unverified against a
> real GCP project. The offline pipeline (`radar scan --fixtures ...`) is fully
> tested and needs none of this. Deploy manually, verify each step.

## Architecture on GCP

- **Cloud Run Job** `opportunity-radar` — one container execution per run:
  fetch Devpost → normalize → dedupe (Firestore) → score → select → Gemini
  brief (anti-invention gated, deterministic fallback).
- **Cloud Scheduler** triggers the job weekly.
- **Firestore** holds seen-ids + last-run (`FirestoreState`, DRAFT/untested).
- **Secret Manager** holds the Gemini API key (`GOOGLE_API_KEY`).

## 0. One-time project setup

```bash
export PROJECT_ID=your-project-id
export REGION=us-east1

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com

# Firestore (Native mode) — once per project
gcloud firestore databases create --location="$REGION"

# Artifact Registry repo for the image
gcloud artifacts repositories create opportunity-radar \
  --repository-format=docker --location="$REGION"
```

## 1. Secret: Gemini API key

```bash
printf '%s' 'YOUR_GEMINI_API_KEY' | gcloud secrets create gemini-api-key \
  --data-file=- --replication-policy=automatic
```

## 2. Build and push the image

```bash
# from the repo root (deploy/Dockerfile copies src/, pyproject.toml, etc.)
gcloud builds submit . \
  --tag "$REGION-docker.pkg.dev/$PROJECT_ID/opportunity-radar/radar:latest" \
  --project "$PROJECT_ID"
```

(Note: `deploy/Dockerfile` must be moved or referenced via a build config if
you keep it out of the root — simplest is
`docker build -f deploy/Dockerfile -t ...:latest .` + `docker push`.)

## 3. Create the Cloud Run Job

```bash
gcloud run jobs create opportunity-radar \
  --image "$REGION-docker.pkg.dev/$PROJECT_ID/opportunity-radar/radar:latest" \
  --region "$REGION" \
  --set-secrets GOOGLE_API_KEY=gemini-api-key:latest \
  --max-retries 1 \
  --task-timeout 600 \
  --memory 512Mi

# or, declaratively, from the (also DRAFT) manifest:
gcloud run jobs replace deploy/cloudrun-job.yaml --region "$REGION"
```

The job's runtime service account needs Firestore access:

```bash
export SA=$(gcloud run jobs describe opportunity-radar --region "$REGION" \
  --format 'value(spec.template.spec.template.spec.serviceAccountName)')
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${SA:-$PROJECT_ID-compute@developer.gserviceaccount.com}" \
  --role roles/datastore.user
```

## 4. Smoke-test one execution

```bash
gcloud run jobs execute opportunity-radar --region "$REGION" --wait
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="opportunity-radar"' \
  --limit 50 --format 'value(textPayload)'
```

Expect the transparent weights block, the fetch/dedupe counts, and either a
gated Gemini brief or the deterministic fallback with its reason.

## 5. Schedule it (weekly, Monday 13:00 UTC)

```bash
gcloud scheduler jobs create http opportunity-radar-weekly \
  --location "$REGION" \
  --schedule "0 13 * * 1" \
  --uri "https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/opportunity-radar:run" \
  --http-method POST \
  --oauth-service-account-email "$PROJECT_ID-compute@developer.gserviceaccount.com"
```

## Known open items (why this is DRAFT)

- No command above has been run; flags may have drifted.
- `FirestoreState` has never talked to a real Firestore database.
- The Gemini call has never been made with a live key from this codebase.
- Brief delivery is just the job log / `/tmp/brief.md` — wiring an email or
  chat sink is future work.
