#| tab: forward
#| background
#| wait: curl -fsS -o /dev/null http://127.0.0.1:8080/
kubectl -n shop port-forward service/web 8080:80
