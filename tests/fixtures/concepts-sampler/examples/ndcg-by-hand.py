"""nDCG at 3 by hand, checked against scikit-learn's ndcg_score: the prose reads the printed nDCG."""
import math

from sklearn.metrics import ndcg_score

grades = [1, 2, 0]                                     # the top three results' grades, in ranked order


def dcg(gains: list[int]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))   # positions count from 0 here, so log2(i + 2)


by_hand = dcg(grades) / dcg(sorted(grades, reverse=True))
assert abs(by_hand - ndcg_score([grades], [[3, 2, 1]])) < 1e-12   # scores that rank the results in the order above
print(f"ndcg@3: {by_hand:.3f}")
