---
chapter_id: files-and-folders
---
# Files and folders

By the end of this chapter, you can make a project folder and count what's in a file.

## Make a project folder {#make-a-project}

Every chapter starts in a fresh workspace that holds the book's files. Make a folder for the project, with a README.

[Step: make-project](../examples/make-project.sh)

[Check: project-has-readme](../examples/project-has-readme.sh)

## Count the lines {#count-the-lines}

The inventory is a small CSV file: one header line, then an item and its quantity on each line.

[File: inventory](../examples/data/inventory.csv)

[Step: copy-inventory](../examples/copy-inventory.sh)

[Step: count-items](../examples/count-items.sh)
