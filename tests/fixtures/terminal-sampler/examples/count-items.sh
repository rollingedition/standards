#| compare: lines
grep -c widget project/inventory.csv
awk -F, 'NR > 1 { n += $2 } END { print "total:", n }' project/inventory.csv
