sudo docker build examples/fastapi --build-arg CACHEBUST=$(date +%s) -f examples/fastapi/Dockerfile -t ghcr.io/abi-jey/k8s-metrix/example-fastapi:latest
sudo docker push ghcr.io/abi-jey/k8s-metrix/example-fastapi:latest
kubectl apply -f examples/fastapi/deployment-example.yaml