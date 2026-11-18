---
chapter_id: sort-and-filter
setup: [make-project, copy-inventory]
---
# Sort and filter

By the end of this chapter, you can sort the inventory and keep the items that run low.

## Sort by quantity {#sort-by-quantity}

Sort the items by their quantity, lowest first, leaving out the header.

[Step: sort-low-first](../examples/sort-low-first.sh)

## Keep the low stock {#keep-low-stock}

Follow the project's log in a second tab while the next steps write to it.

[Step: follow-log](../examples/follow-log.sh)

[Step: write-low-stock](../examples/write-low-stock.sh)

[Check: low-stock-written](../examples/low-stock-written.sh)

No gadget runs low, so `grep` finds nothing and exits 1.

[Step: no-gadgets-low](../examples/no-gadgets-low.sh)

[Step: stamp-the-check](../examples/stamp-the-check.sh)
