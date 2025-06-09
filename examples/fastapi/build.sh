#!/bin/bash

sudo docker build . -f Dockerfile -t ghcr.io/abi-jey/k8s-metrix/examples/fastapi:latest
sudo docker push ghcr.io/abi-jey/k8s-metrix/examples/fastapi:latest