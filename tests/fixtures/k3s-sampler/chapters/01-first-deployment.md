---
chapter_id: first-deployment
---
# A first deployment

By the end of this chapter, you can run a web server on the cluster in three copies and check that each one is up.

## Make a namespace {#make-a-namespace}

Everything this book runs goes in a namespace of its own, so one command can show it all and one can take it away.

[Step: create-shop-namespace](../examples/create-shop-namespace.sh)

[Check: shop-namespace-exists](../examples/shop-namespace-exists.sh)

## Deploy the web server {#deploy-the-web-server}

The deployment asks for three copies of nginx, at the version the stack pins. The cluster can't pull anything, so it runs the image the book imported.

[File: web-deployment](../examples/manifests/web-deployment.yaml)

[Step: apply-web](../examples/apply-web.sh)

[Check: web-has-three-replicas](../examples/web-has-three-replicas.sh)

Each copy is a pod with a generated name, so the listing masks the names' suffixes and the pods' ages.

[Step: list-web-pods](../examples/list-web-pods.sh)
