---
chapter_id: graded-gains
---

# Graded gains

By the end of this chapter you can compute DCG and nDCG by hand and check them against scikit-learn. Precision at k
counts a partial match as relevant or not; a graded metric uses the grade itself.

## Gains and discounts {#dcg}

A **gain** is what a result's grade is worth to the score. **Discounted cumulative gain** (DCG) is the sum of the top k
results' gains, each divided by a discount that grows with its position. The **discount** is the part of DCG that
shrinks a gain lower down: the logarithm, base 2, of the position plus one.

**Working rule:** Use the grades as the gains, and say so.

## Normalize by the ideal ranking {#ndcg}

A DCG has no fixed top, so its scores can't be compared across queries. **Normalized DCG** (nDCG) divides a ranking's
DCG by the DCG of the ideal ranking, the judged results sorted by grade, so a perfect ranking scores 1:

```text
nDCG@k = DCG@k / DCG@k of the ideal ranking
```

At scikit-learn {{version:scikit-learn}}, `ndcg_score` uses the same gains and the same discount.

[Example: ndcg-by-hand](../examples/ndcg-by-hand.py)

By hand and with scikit-learn alike, the ranking scores an nDCG@3 of {{out:ndcg-by-hand:ndcg@3}}.

**Working rule:** Compare nDCG only between rankings scored on the same judgments.
