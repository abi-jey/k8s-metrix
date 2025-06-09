#!/bin/bash
kubectl create secret tls k8s-metrix-tls-secret --cert=examples/fastapi/k8s-metrix-cert.pem --key=examples/fastapi/k8s-metrix-key.pem --namespace=metrix-system --dry-run=client -o yaml | kubectl apply -f -
