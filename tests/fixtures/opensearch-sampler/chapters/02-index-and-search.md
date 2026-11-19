---
chapter_id: index-and-search
setup: [cluster-health]
---
# Index and search

By the end of this chapter, you can index a few products and find them by a word in their names.

## Index the products {#index-the-products}

The products are a small file of JSON lines, an action line and a document for each. Send them in one bulk request,
and refresh the index so a search sees them at once.

[File: products](../examples/data/products.ndjson)

[Step: index-products](../examples/index-products.sh)

[Check: three-products](../examples/three-products.sh)

## Search by name {#search-by-name}

Ask for the products whose name has "lamp" in it.

[Step: search-lamps](../examples/search-lamps.sh)
