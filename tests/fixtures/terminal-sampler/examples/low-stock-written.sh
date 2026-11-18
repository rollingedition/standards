#| check
#| hint: Write project/low-stock.csv with the step above.
test -s project/low-stock.csv && grep -q sprocket project/low-stock.csv
