#| wait: test "$(kubectl -n shop get deployment web -o jsonpath='{.status.availableReplicas}')" = 5
#| timeout: 180
kubectl -n shop scale deployment web --replicas=5
