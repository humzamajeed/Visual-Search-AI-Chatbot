#!/bin/bash
set -e

echo "=== Starting Visual Search AI Chatbot — Kubernetes Deployment ==="

NAMESPACE="visual-search"
K8S_DIR="$(dirname "$0")/k8s"

echo "[1/9] Applying namespace..."
kubectl apply -f "$K8S_DIR/namespace.yml"

echo "[2/9] Applying secrets..."
kubectl apply -f "$K8S_DIR/mongo-secret.yml"

echo "[3/9] Applying ConfigMap..."
kubectl apply -f "$K8S_DIR/backend-configmap.yml"

echo "[4/9] Applying PersistentVolume and PVC..."
kubectl apply -f "$K8S_DIR/mongo-pv.yml"
kubectl apply -f "$K8S_DIR/mongo-pvc.yml"

echo "[5/9] Deploying MongoDB..."
kubectl apply -f "$K8S_DIR/mongo-deployment.yml"
kubectl apply -f "$K8S_DIR/mongo-service.yml"
kubectl wait --for=condition=ready pod -l app=mongo -n "$NAMESPACE" --timeout=120s

echo "[6/9] Deploying backend..."
kubectl apply -f "$K8S_DIR/backend-deployment.yml"
kubectl apply -f "$K8S_DIR/backend-service.yml"
kubectl wait --for=condition=ready pod -l app=backend -n "$NAMESPACE" --timeout=180s

echo "[7/9] Deploying frontend..."
kubectl apply -f "$K8S_DIR/frontend-deployment.yml"
kubectl apply -f "$K8S_DIR/frontend-service.yml"
kubectl wait --for=condition=ready pod -l app=frontend -n "$NAMESPACE" --timeout=120s

echo "[8/9] Deploying Prometheus monitoring..."
kubectl apply -f "$K8S_DIR/prometheus-config.yml"
kubectl apply -f "$K8S_DIR/prometheus-deployment.yml"
kubectl apply -f "$K8S_DIR/prometheus-service.yml"

echo "[9/9] Deploying Grafana..."
kubectl apply -f "$K8S_DIR/grafana-deployment.yml"
kubectl apply -f "$K8S_DIR/grafana-service.yml"

echo ""
echo "=== Deployment complete ==="
kubectl get pods -n "$NAMESPACE"
kubectl get svc -n "$NAMESPACE"

echo ""
echo "Access the app with:"
echo "  kubectl port-forward -n $NAMESPACE svc/frontend 8080:80"
echo "Access Grafana with:"
echo "  kubectl port-forward -n $NAMESPACE svc/grafana 3000:3000"
