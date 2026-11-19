#| check
#| hint: Scale the deployment to five copies, then wait until they're available: kubectl -n shop get deployment web
test "$(kubectl -n shop get deployment web -o jsonpath='{.status.availableReplicas}')" = 5
