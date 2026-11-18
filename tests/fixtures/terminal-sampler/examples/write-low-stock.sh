#| wait: grep -q restocked project/events.log
awk -F, 'NR > 1 && $2 < 10' project/inventory.csv > project/low-stock.csv
echo "restocked $(wc -l < project/low-stock.csv | tr -d ' ') items" >> project/events.log
cat project/low-stock.csv
