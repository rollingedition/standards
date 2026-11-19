curl -fsS -H 'Content-Type: application/x-ndjson' --data-binary @data/products.ndjson \
  'http://127.0.0.1:9200/_bulk?refresh=true&filter_path=errors'
