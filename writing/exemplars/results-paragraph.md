# Exemplar: results that lead with the point

Two passages from released books, before and after they were rewritten to W-61, with notes. Numbers in the prose are bindings to the examples' recorded outputs (W-26), shown here as written in the source.

A results paragraph opens with the sentence the reader should keep, then quotes the one to three numbers that show it. Everything else the example printed stays in its output, which the page shows beside the prose, or goes in a table.

---

## 1. A count is a number, not a subject

From "Lexical retrieval", chapter 5 of *A primer on search relevance*. A shopper typed `7qt slow cooker`, and the example shows what the tokenizer did to it.

### Before

The number of products that the hand-written tokenizer and bm25s's split differently is {{out:tokenize-product-text:products tokenized differently}}. The trouble is in the rules they share. The shopper wants a 7-quart slow cooker, and `7qt` survives as one token. But the number of products that contain the term `7qt` is {{out:tokenize-product-text:products with the term 7qt}}, because product text writes the size apart: the text of {{out:tokenize-product-text:products whose text says 7 qt}} products says `7 qt`, and the tokenizer drops their `7`, which is one character long. The size plays no part in the ranking, on the query's side or the products'. The judges marked {{out:tokenize-product-text:exact products judged for query 62}} products [exact](#store-data) for this query, and BM25's top 10 holds {{out:tokenize-product-text:exact products in bm25's top 10}} of them. Without the size, the terms can't tell a 7-quart cooker from any other slow cooker.

### After

The hand-written tokenizer splits every product exactly as bm25s does, which the example checks, so the trouble isn't in either one: it's in the rules they share. A shopper who types `7qt slow cooker` wants a 7-quart cooker, and `7qt` does survive as a token. But it matches {{out:tokenize-product-text:products with the term 7qt}} products, because product text writes the size apart, as `7 qt` in {{out:tokenize-product-text:products whose text says 7 qt}} products, and the tokenizer drops the one-character `7`. So the size disappears from both sides of the match, and BM25 can't tell a 7-quart cooker from any other: of the {{out:tokenize-product-text:exact products judged for query 62}} products the judges marked [exact](#store-data) for this query, its top 10 holds {{out:tokenize-product-text:exact products in bm25's top 10}}.

### Notes

The same claims, and six of the seven bindings. The seventh, the count of products the two tokenizers split differently, is 0, and the paragraph relies on its being 0: that's a yes or no in disguise, so the example asserts it and the prose states it (W-61). No sentence has a count as its subject ("The number of products that … is"), so each verb says something, and each sentence stays true if a bound number changes. The paragraph's point, "the size disappears from both sides of the match", is its own clause, and the judged products come after it as the evidence, not before it as an inventory.

---

## 2. When the numbers disagree, say so first

From "Measuring search", chapter 3 of the same book. Two rankers, scored four ways on the train queries.

### Before

Semantic retrieval scores higher on {{out:metric-choice-on-train:metrics won by semantic}} of the four metrics and the hybrid on {{out:metric-choice-on-train:metrics won by hybrid}}. Precision@10 puts `{{out:metric-choice-on-train:higher precision@10}}` ahead ({{out:metric-choice-on-train:semantic precision@10}} for semantic retrieval, {{out:metric-choice-on-train:hybrid precision@10}} for the hybrid), and MRR puts `{{out:metric-choice-on-train:higher mrr}}` ahead ({{out:metric-choice-on-train:semantic mrr}} and {{out:metric-choice-on-train:hybrid mrr}}, in the same order). nDCG@10 favours `{{out:metric-choice-on-train:higher ndcg@10}}` ({{out:metric-choice-on-train:semantic ndcg@10}} and {{out:metric-choice-on-train:hybrid ndcg@10}}), and exponential gains favour `{{out:metric-choice-on-train:higher ndcg@10 with exponential gains}}` ({{out:metric-choice-on-train:semantic ndcg@10 with exponential gains}} and {{out:metric-choice-on-train:hybrid ndcg@10 with exponential gains}}). The largest of the four gaps is {{out:metric-choice-on-train:largest gap}}. These are train queries, so the gaps say nothing about which ranker is better. They show that when two rankers are this close, the metric decides which way the gap falls.

### After

The four metrics don't agree on a winner. Semantic retrieval leads on {{out:metric-choice-on-train:metrics won by semantic}} of them and the hybrid on {{out:metric-choice-on-train:metrics won by hybrid}}, and no gap between the two is larger than {{out:metric-choice-on-train:largest gap}}. When two rankers are this close, the metric decides which way the gap falls; the scores beside this paragraph show each ranker on each metric. nDCG@10, the headline [chapter 1](#score-one-ranking) chose, favours `{{out:metric-choice-on-train:higher ndcg@10}}`. These are train queries, so none of this says which ranker is better.

### Notes

Fifteen bindings became four. The point, which came last before, comes first: the metrics disagree, and with rankers this close, the metric picks the winner. The three numbers that show it follow. Each ranker's score on each metric is already in the output beside the paragraph, so the prose points to it instead of reading it out. The caveat about train queries is said once (W-66).

---

## 3. A yes or no is a fact, not a value

From "Attention", chapter 6 of *Language models from the ground up*. The example changes the last token of `sled coffee table` and checks whether the output at `coffee` changes, without the causal mask and with it.

### Before

The example printed two yes-or-no lines:

```
output at coffee changes with the last token, without the mask: True
output at coffee changes with the last token, with the mask: False
```

and the prose quoted them:

Without the mask, changing the last token changes the output at `coffee`: {{out:causal-mask:output at coffee changes with the last token, without the mask}}. With it, `coffee`'s output can't depend on what comes later: {{out:causal-mask:output at coffee changes with the last token, with the mask}}.

On the page, the second sentence reads "`coffee`'s output can't depend on what comes later: False", a double negative the reader has to undo.

### After

The example measures the change, prints it, and asserts what the prose relies on:

```python
for mask in [False, True]:
    before, after = attend(x, mask)[1][2], attend(changed, mask)[1][2]   # coffee is position 2
    change = float(np.abs(after - before).max())
    print(f"largest change in coffee's output, {'with' if mask else 'without'} the mask: {change:.2f}")
    assert (change == 0) == mask        # the mask's whole job: with it, nothing after coffee reaches coffee
```

```
largest change in coffee's output, without the mask: 4.69
largest change in coffee's output, with the mask: 0.00
```

The prose states the fact and quotes the measurement:

Without the mask, a different last token moves the output at `coffee` by as much as {{out:causal-mask:largest change in coffee's output, without the mask}}. With the mask, it can't move it at all, because `coffee` no longer sees anything after it.

### Notes

The `assert` makes the claim a check: if a change to the code let a later token leak into `coffee`, the example would fail its run instead of printing `True` into a sentence that says the opposite. The printed number is something the reader can use, and the prose binds it (W-26). The second sentence binds nothing: it states what the assert guarantees.
