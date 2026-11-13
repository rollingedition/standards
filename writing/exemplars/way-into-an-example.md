# Exemplar: leading into an example

How a released chapter led into an example and read its output, before and after it was rewritten to W-63 and W-67, with notes; then other ways in that the released books already use well. The passage is from "Attention", chapter 6 of *Language models from the ground up*, whose running case is the text of an online furniture store's product names and descriptions, called the store. `[Example: …]` marks where the page shows the example's code and output.

An example needs a reason to be read. Before it, say what the reader is about to see and why it's worth running, in words that differ from the last example's. After it, read the output with the reader: point at what matters, then say what it means.

---

## Before

For the store, take four tokens, the start marker and `sled coffee table`, a table whose base is shaped like a sled's runners. Give each a random vector of 8 numbers, as an untrained embedding table would, and compute attention with random 8-by-4 query, key and value matrices:

[Example: attention-by-hand](../examples/attention-by-hand.py)

Each row of the printed weights is one position's average: which positions it draws from, and how much. Every row sums to one, as the line `each row sums to 1: {{out:attention-by-hand:each row sums to 1}}` confirms, and the output has one 4-number vector per position. The weights are random, because the matrices are, but they already show attention's freedom: `coffee` puts most of its weight on `table`, and the start marker on `sled`, because nothing restricts which positions a row can draw from. For predicting the next token, that freedom is a bug, as the [next section](#hide-the-future) shows.

## After

To watch the arithmetic on something small, take one name from the store, `sled coffee table`, a table whose base is shaped like a sled's runners, with its start marker: four tokens. Give each a random vector of 8 numbers, as an untrained embedding table would, and use random 8-by-4 query, key and value matrices. Nothing has been learned yet, so what the example shows is the machinery alone:

[Example: attention-by-hand](../examples/attention-by-hand.py)

Read the weight matrix row by row. Each row is one position's average, and says which positions that position draws from and how much; every row sums to one, which the example checks, and the output keeps one 4-number vector per position. The weights mean nothing yet, because the matrices are random, but notice what they're free to do: `coffee` puts most of its weight on `table`, a token that comes after it, and the start marker puts most of its weight on `sled`. Nothing in the arithmetic stops a position from looking ahead. For a model that predicts the next token, that freedom is a bug, and the [next section](#hide-the-future) closes it.

---

## Notes

| Rule | What changed, and why |
| --- | --- |
| W-63 Vary the way in | "For the store, …" opened 76 sentences in this book. Here the sentence starts from the reader's purpose, "to watch the arithmetic on something small", and the store comes in where the sentence needs it. The line after the setup says why the example is worth running: it shows the machinery with nothing learned. |
| W-67 Write as the author | "Read the weight matrix row by row." and "notice what they're free to do" guide the reader's eye before the claim. "Nothing in the arithmetic stops a position from looking ahead." is the point, in a sentence of its own. |
| W-61 A yes or no is a fact | The output's line `each row sums to 1: True` is no longer quoted in the prose. The example asserts it, and the prose says it. |
| W-52 Connect each step to the last | The last sentence still hands the reader to the next section, now as a promise ("closes it") instead of a pointer ("as the next section shows"). |

---

## Other ways in

Vary how examples are introduced across a chapter. These are from the released books, and each gives the reader a reason to look:

- **A question the reader would ask.** "Why not put the whole catalog in the prompt and skip retrieval?" (*A primer on search relevance*, chapter 10), before the example that measures how much of it would fit.
- **A puzzle in the output.** "For `luau string lights`, BM25's top 10 holds {{out:ndcg-from-scratch:exact in the top 10}} exact products and scores {{out:ndcg-from-scratch:ndcg@10}}. That's not a mistake." (the same book, chapter 3), after the example, before the explanation of what a perfect nDCG@10 means.
- **The failure, set up in the case.** "One that sees only the last four tokens, `this outdoor patio furniture`, has to guess among everything that follows those words in other products." (*Language models from the ground up*, chapter 6), before the example that looks further back.
- **A claim to test.** "If the model predicts `cover` by copying it from the name, then changing the name should change the prediction." (the same chapter), before the example that changes it.

## Asking for the prediction

W-11 allows one prediction a chapter. Ask it in that chapter's words: "Before you run it, predict …" opened the prediction in 7 of the 11 chapters of one book, and 6 of another, word for word. Instead:

- "Make a guess first: with 256 numbers and no division, how much of a row's weight will the strongest key take?"
- "Which do you expect to win on the test queries, and by how much?"

And close the loop in words of the chapter's own, not "If you predicted X, you …" every time.

## Pointing a working rule at its example

Name the example only when the rule is to do what it did. "Print the weight matrix, as this example does" tells the reader to copy a step. "Measure the share of padding in your batches, as here; if it's large, pack texts or group them by length before you buy a bigger machine" points back at the section the rule closes, which the reader has just read. Without "as here", the rule says the same.
