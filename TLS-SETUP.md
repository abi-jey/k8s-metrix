# TLS Certificate Setup for k8s-metrix

This guide explains how to generate TLS certificates for k8s-metrix and deploy them in Kubernetes.

## Quick Start

### 1. Generate Certificate and CSR

```bash
# Generate certificate for the FastAPI example service
python src/k8s_metrix/main.py --service-name metrix-example-fastapi-service --namespace metrix-example
```

This will create:
- `k8s-metrix-csr.pem` - Certificate Signing Request
- `k8s-metrix-key.pem` - Private key
- `k8s-metrix-cert.pem` - Signed certificate (after approval)

### 2. Approve the CSR

The script will show you the approval command, but you can also run:

```bash
kubectl certificate approve metrix-example-fastapi-service-csr
```

### 3. Create Kubernetes Secret

Use the provided script to create a TLS secret:

```bash
./create-tls-secret.sh metrix-example k8s-metrix-tls-secret
```

Or manually:

```bash
kubectl create secret tls k8s-metrix-tls-secret \
  --cert=k8s-metrix-cert.pem \
  --key=k8s-metrix-key.pem \
  --namespace=metrix-example
```

### 4. Deploy the Application

```bash
kubectl apply -f examples/fastapi/deployment.yaml
```

## Files Generated

| File | Description | Permissions |
|------|-------------|-------------|
| `k8s-metrix-csr.pem` | Certificate Signing Request | 644 (readable) |
| `k8s-metrix-key.pem` | Private Key | 600 (owner only) |
| `k8s-metrix-cert.pem` | Signed Certificate | 644 (readable) |

## Certificate Locations in Pod

When mounted in the pod, certificates are available at:

- **Certificate**: `/etc/ssl/certs/k8s-metrix/tls.crt`
- **Private Key**: `/etc/ssl/certs/k8s-metrix/tls.key`

Environment variables are also set:
- `TLS_CERT_PATH=/etc/ssl/certs/k8s-metrix/tls.crt`
- `TLS_KEY_PATH=/etc/ssl/certs/k8s-metrix/tls.key`

## Common Commands

### View Certificate Details
```bash
# From file
openssl x509 -in k8s-metrix-cert.pem -text -noout

# From Kubernetes secret
kubectl get secret k8s-metrix-tls-secret -n metrix-example -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -text -noout
```

### View CSR Details
```bash
openssl req -in k8s-metrix-csr.pem -text -noout
```

### Check CSR Status
```bash
kubectl get csr
kubectl describe csr metrix-example-fastapi-service-csr
```

### Verify Secret
```bash
kubectl get secret k8s-metrix-tls-secret -n metrix-example
kubectl describe secret k8s-metrix-tls-secret -n metrix-example
```

## Troubleshooting

### CSR Approval Failed
If you see "invalid usage for client certificate: server auth", ensure you're using the latest version of the script that requests only client authentication.

### Permission Denied
Make sure the script is executable:
```bash
chmod +x create-tls-secret.sh
```

### Certificate Not Found
Ensure the CSR was approved and the certificate was generated:
```bash
kubectl get csr
ls -la k8s-metrix-*.pem
```

## Security Notes

- Private keys are stored with restrictive permissions (600)
- Certificates are mounted read-only in pods
- Use appropriate RBAC for accessing secrets
- Rotate certificates regularly according to your security policy

## Custom Service Names

For different services, adjust the service name and namespace:

```bash
# For a different service
python src/k8s_metrix/main.py --service-name my-service --namespace my-namespace

# Create secret for the custom service
./create-tls-secret.sh my-namespace my-service-tls-secret
```
