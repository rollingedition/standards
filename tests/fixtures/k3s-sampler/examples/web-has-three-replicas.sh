#| check
#| hint: Apply the deployment, then wait until its three pods are Running: kubectl -n shop get pods
test "$(kubectl -n shop get deployment web -o jsonpath='{.status.availableReplicas}')" = 3
