# NENMP Deployment Guide

This guide deploys a GKE cluster, cert-manager, and the `helloworld` app using Terraform and Kubernetes manifests.

## Project Structure

```text
nenmp/
├── app/helloworld/
│   ├── Dockerfile
│   └── index.html
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
