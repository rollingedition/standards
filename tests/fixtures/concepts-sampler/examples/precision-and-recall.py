"""Precision and recall at 3 for one ranking: the prose reads both printed lines."""
ranking = ["lamp-a", "lamp-b", "rug-c", "lamp-d"]     # the system's order, best first
relevant = {"lamp-a", "lamp-d", "lamp-e"}              # every result the judges called relevant, ranked or not
hits = sum(result in relevant for result in ranking[:3])
print(f"precision@3: {hits / 3:.2f}")
print(f"recall@3: {hits / len(relevant):.2f}")
