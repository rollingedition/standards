---
chapter_id: scale-and-serve
setup: [create-shop-namespace, apply-web]
---
# Scale and serve

By the end of this chapter, you can run more copies of the web server and reach them through one service.

## Scale the deployment {#scale-the-deployment}

Five copies instead of three: the step waits until all five are available.

[Step: scale-web](../examples/scale-web.sh)

[Check: web-has-five-replicas](../examples/web-has-five-replicas.sh)

## Serve it {#serve-the-copies}

A service gives the copies one address inside the cluster. A port-forward in a second tab brings it to this machine.

[Step: expose-web](../examples/expose-web.sh)

[Step: forward-web](../examples/forward-web.sh)

[Step: fetch-home-page](../examples/fetch-home-page.sh)

[Check: home-page-answers](../examples/home-page-answers.sh)
