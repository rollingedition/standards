curl -fsS 'http://127.0.0.1:9200/products/_search?q=name:lamp&sort=price&filter_path=hits.hits._source.name'
