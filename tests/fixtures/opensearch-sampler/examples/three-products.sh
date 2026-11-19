#| check
#| hint: Run the bulk request above: it indexes the three products.
test "$(curl -fsS 'http://127.0.0.1:9200/products/_count?filter_path=count')" = '{"count":3}'
