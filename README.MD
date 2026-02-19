# NENMP Deployment Guide

This guide deploys GKE cluster, cert-manager, and the helloworld app from scratch using Terraform and Kubernetes manifests.

---

# Project Structure

```
nenmp/
├── app/helloworld/
│   ├── Dockerfile
│   └── index.html
│
├── infra/terraform/
│   ├── main.tf
│   ├── gke.tf
│   ├── outputs.tf
│   └── variables.tf
│
└── k8s/
    ├── app/
    │   ├── deployment.yaml
    │   ├── service.yaml
    │   └── ingress.yaml
    │
    └── cert-manager/
        ├── clusterissuer.yaml
        ├── certificate.yaml
        └── cloudflare-secret.yaml  # placeholder
```

---

# Step 1 — Deploy GKE cluster

```
cd infra/terraform

terraform init
terraform apply
```

Confirm:

```
yes
```

---

# Step 2 — Connect kubectl

```
gcloud container clusters get-credentials small-gke --zone us-central1-a

kubectl get nodes
```

Expected:

```
Ready
```

---

# Step 3 — Install cert-manager

```
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

kubectl get pods -n cert-manager
```

Wait until all are Running.

---

# Step 4 — Restore Cloudflare secret from Secret Manager

```
kubectl create secret generic cloudflare-api-token-secret \
  -n cert-manager \
  --from-literal=api-token="$(gcloud secrets versions access latest --secret=cloudflare-api-token)" \
  --dry-run=client -o yaml | kubectl apply -f -
```

---

# Step 5 — Apply cert-manager resources

```
kubectl apply -f k8s/cert-manager/clusterissuer.yaml
kubectl apply -f k8s/cert-manager/certificate.yaml

kubectl get clusterissuer
```

Expected:

```
READY True
```

---

# Step 6 — Deploy application

```
kubectl apply -f k8s/app/
```

Get ingress IP:

```
kubectl get ingress
```

---

# Step 7 — Configure Cloudflare DNS

Create A record:

```
helloworld.deniskachar.com → <INGRESS_IP>
```

---

# Step 8 — Verify TLS

```
kubectl get certificate
kubectl get secret helloworld-tls
```

Test:

```
https://helloworld.deniskachar.com
```

---

# Note

Cloudflare API token is stored in:

```
GCP Secret Manager
```

and injected into Kubernetes manually using the command in Step 4.
