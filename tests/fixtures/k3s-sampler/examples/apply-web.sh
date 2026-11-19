#| wait: test "$(kubectl -n shop get deployment web -o jsonpath='{.status.availableReplicas}')" = 3
#| timeout: 180
kubectl apply -f manifests/web-deployment.yaml
