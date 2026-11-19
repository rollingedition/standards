#| wait: curl -fsS http://127.0.0.1:9200/_cluster/health?wait_for_status=yellow
#| compare: lines
curl -fsS 'http://127.0.0.1:9200/_cat/health?h=status,node.total'
