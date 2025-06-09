#!/bin/bash
set -e
sudo docker build -t ghcr.io/abi-jey/k8s-metrix/metrix-adapter:latest -f Dockerfile.Adapter .
sudo docker push ghcr.io/abi-jey/k8s-metrix/metrix-adapter:latest
