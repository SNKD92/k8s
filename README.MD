# NENMP Deployment Guide

This guide deploys a GKE cluster, cert-manager, and the `helloworld` app using Terraform and Kubernetes manifests.

## Project Structure

```text
nenmp/
├── app/helloworld/
│   ├── Dockerfile
│   └── index.html
├── .github/workflows/
│   └── deploy.yml
├── infra/terraform/
│   ├── main.tf
│   ├── gke.tf
│   ├── sa.tf
│   ├── outputs.tf
│   └── variables.tf
└── k8s/
    ├── app/
    │   ├── deployment.yaml
    │   ├── service.yaml
    │   └── ingress.yaml
    └── cert-manager/
        ├── clusterissuer.yaml
        ├── certificate.yaml
        └── cloudflare-secret.yaml  # placeholder only
```

## Prerequisites

- Terraform installed
- `gcloud` installed and authenticated to your project
- `kubectl` installed
- Domain `deniskachar.com` managed in Cloudflare
- GCP Secret Manager secret `cloudflare-api-token` already created

## CI/CD Auth and Secrets (`sa.tf` + `deploy.yml`)

`infra/terraform/sa.tf` creates identity resources for GitHub Actions:

- Service account: `github-actions@project-e7b71f6e-c56d-438f-a7e.iam.gserviceaccount.com`
- Workload Identity Pool: `github-pool`
- Workload Identity Provider: `github-provider`
- Repo restriction: only `SNKD92/k8s` can federate
- IAM roles on project:
  - `roles/container.developer`
  - `roles/container.clusterViewer`
- Service account impersonation binding:
  - `roles/iam.workloadIdentityUser` for principal set
    `principalSet://iam.googleapis.com/projects/365212276900/locations/global/workloadIdentityPools/github-pool/attribute.repository/SNKD92/k8s`

GitHub workflow file: `.github/workflows/deploy.yml`.

Keep these values in sync between `infra/terraform/sa.tf` and `.github/workflows/deploy.yml`:

- Project number: `365212276900`
- Workload Identity provider path:
  `projects/365212276900/locations/global/workloadIdentityPools/github-pool/providers/github-provider`
- Service account:
  `github-actions@project-e7b71f6e-c56d-438f-a7e.iam.gserviceaccount.com`
- Repository scope: `SNKD92/k8s`

Required GitHub repository secrets for that workflow:

- `DOCKER_USERNAME` (Docker Hub username)
- `DOCKER_PASSWORD` (Docker Hub access token/password)
  Source of truth: GCP Secret Manager secret
  `projects/365212276900/secrets/githubactionssecret` (latest version).

No static GCP service account key secret is required because the workflow uses OIDC Workload Identity Federation.

## Step 1 - Deploy the GKE cluster

```bash
cd infra/terraform
terraform init
terraform apply
```

When prompted, type:

```text
yes
```

## Step 2 - Connect kubectl to the cluster

```bash
gcloud container clusters get-credentials small-gke --zone us-central1-a
kubectl get nodes
```

Expected output should show nodes in `Ready` state.

## Step 3 - Install cert-manager

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml
kubectl get pods -n cert-manager
```

Wait until cert-manager pods are `Running`.

## Step 4 - Restore Cloudflare token secret from Secret Manager

```bash
kubectl create secret generic cloudflare-api-token-secret \
  -n cert-manager \
  --from-literal=api-token="$(gcloud secrets versions access latest --secret=cloudflare-api-token)" \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Step 5 - Apply cert-manager resources

Return to repo root first:

```bash
cd ../..
kubectl apply -f k8s/cert-manager/clusterissuer.yaml
kubectl apply -f k8s/cert-manager/certificate.yaml
kubectl get clusterissuer
```

Expected:

```text
letsencrypt-cloudflare   True
```

## Step 6 - Deploy the application

```bash
kubectl apply -f k8s/app/
kubectl get ingress deniskachar-com-ingress
```

Copy the ingress external IP from the output.

## Step 7 - Configure Cloudflare DNS

Create an `A` record:

```text
deniskachar.com -> <INGRESS_IP>
```

## Step 8 - Verify TLS

```bash
kubectl get certificate deniskachar-cert
kubectl get secret deniskachar-com-tls
```

Then test:

```text
https://deniskachar.com
```

## Note

The Cloudflare API token is stored in GCP Secret Manager and injected into Kubernetes via the Step 4 command.
