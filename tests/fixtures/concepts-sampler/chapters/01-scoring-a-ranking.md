---
chapter_id: scoring-a-ranking
---

# Scoring a ranking

By the end of this chapter you can score one ranking with precision at k and recall at k, and say what each misses.
**Relevance** is how well a result meets the need behind a query, and every score here starts from people's judgments
of it. [Chapter 2](#ndcg) builds nDCG on the same judgments.

## Judge each result {#judge-each-result}

A **relevance judgment** is a person's label for one pair of a query and a result. A grade is the number that stands
for the label: 2 for exact, 1 for partial and 0 for irrelevant.

**Working rule:** Judge a result against the need behind the query, never against its words.

## Count what's relevant at the top {#count-relevant-at-the-top}

Shoppers read from the top, so a score looks at the first k results. **Precision at k**, written precision@k, is the
share of the top k results that are relevant. **Recall at k**, recall@k, is the share of all relevant results that
appear in the top k. Raising one usually costs the other.

```text
precision@k = relevant results in the top k / k
```

[Example: precision-and-recall](../examples/precision-and-recall.py)

One relevant result in the top three gives a precision@3 of {{out:precision-and-recall:precision@3}}, and with three
relevant results in all, a recall@3 of {{out:precision-and-recall:recall@3}}.

**Working rule:** Report precision and recall at the same k.

### Metrics that score a whole ranking {#ranking-metrics}

A **ranking metric** is a number that scores a whole ranking against the judgments. Precision at k and recall at k are
the simplest; [nDCG](#ndcg) also weighs each result by its position.

**Working rule:** Choose the metric before you compare rankings.
