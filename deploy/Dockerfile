# DRAFT — NOT YET BUILT OR DEPLOYED. Written for Cloud Run Jobs; the build
# and deploy commands in docs/DEPLOY.md have not been executed against a real
# GCP project. The offline pipeline is fully tested without this image.

FROM python:3.12-slim

WORKDIR /app

# Install the package with the agent + gcp extras (Gemini narration and
# FirestoreState). The image never runs tests; tests run offline in CI.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY profile.example.yaml ./profile.yaml

RUN pip install --no-cache-dir ".[agent,gcp]"

# Cloud Run Jobs invoke the container once per execution: one radar run,
# live Devpost fetch, Firestore-backed dedupe, Gemini brief with the
# anti-invention gate (deterministic fallback on any failure).
# GOOGLE_API_KEY comes from Secret Manager (see cloudrun-job.yaml).
ENTRYPOINT ["python", "-m", "opportunity_radar", "scan", "--gemini", "--firestore", "--out", "/tmp/brief.md"]
