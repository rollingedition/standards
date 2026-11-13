# Exemplar: an example that explains itself

An example from a released book, before and after it was commented to W-68, with notes. It's `measure-decoding.py` from "Choosing the next token", chapter 9 of *Language models from the ground up*. It measures seven ways of choosing a small language model's next token on the same 20 product descriptions from an online furniture store, the book's running case. Its code is unchanged, so its output is too.

Readers copy examples into their own work, and the first thing they lose is why each line is there. The prose beside the example explains the idea; the comments explain the code, in the prose's words, wherever the code doesn't say why.

---

## Before

```python
import numpy as np

from lib import decoding
from lib.products import product_texts

longest, sample, seed = 60, 20, 2026
described = [(ids, sep) for ids, sep in product_texts("validation") if sep < len(ids) - 2]
products = [described[i] for i in np.random.default_rng(seed).choice(len(described), sample, replace=False)]
print("products, drawn at random from the validation products with a description:", sample)
print("longest description, in tokens:", longest)


settings = [("real descriptions", None), ("greedy", {}), ("greedy, repetition penalty 1.3", {"penalty": 1.3}),
            ("sampling, temperature 1.0", {"sample": True}), ("sampling, temperature 0.7", {"sample": True, "temperature": 0.7}),
            ("top-k 20", {"sample": True, "top_k": 20}), ("top-p 0.9", {"sample": True, "top_p": 0.9})]
for label, chosen in settings:
    rows = []
    for number, (ids, sep) in enumerate(products):
        start = ids[:sep + 1]
        if chosen is None:
            written = ids[sep + 1:][:longest]
        else:
            options = {option: value for option, value in chosen.items() if option != "sample"}
            rng = np.random.default_rng(seed + number) if chosen.get("sample") else None
            written = decoding.generate(start, rng=rng, longest=longest, **options)
        rows.append(decoding.measures(start, written))
    repeated, log_p, ended, uses_name, length = zip(*rows)
    print(f"{label}, repeated 4-token phrases:", f"{np.mean(repeated):.0%}")
    print(f"{label}, the model's perplexity of the text:", f"{np.exp(-np.concatenate(log_p).mean()):.1f}")
    print(f"{label}, ended within {longest} tokens:", f"{np.mean(ended):.0%}")
    print(f"{label}, uses a whole word of the name:", f"{np.mean(uses_name):.0%}")
    print(f"{label}, average length in tokens:", f"{np.mean(length):.0f}")
```

## After

```python
"""Seven ways of choosing the next token, measured on the same 20 product descriptions: how often each repeats
itself, how likely the model finds its own text, whether it ends, and whether it stays on the product. The real
descriptions come first, as the bar the others are read against."""
import numpy as np

from lib import decoding                    # the store's model, and the decoding methods this chapter builds
from lib.products import product_texts

longest, sample, seed = 60, 20, 2026
# Validation products, which the model never trained on, that have at least one token of description after <sep>
described = [(ids, sep) for ids, sep in product_texts("validation") if sep < len(ids) - 2]
products = [described[i] for i in np.random.default_rng(seed).choice(len(described), sample, replace=False)]
print("products, drawn at random from the validation products with a description:", sample)
print("longest description, in tokens:", longest)


settings = [("real descriptions", None), ("greedy", {}), ("greedy, repetition penalty 1.3", {"penalty": 1.3}),
            ("sampling, temperature 1.0", {"sample": True}), ("sampling, temperature 0.7", {"sample": True, "temperature": 0.7}),
            ("top-k 20", {"sample": True, "top_k": 20}), ("top-p 0.9", {"sample": True, "top_p": 0.9})]
for label, chosen in settings:
    rows = []
    for number, (ids, sep) in enumerate(products):
        start = ids[:sep + 1]                                 # the start marker, the name and <sep>: the model writes on from here
        if chosen is None:
            written = ids[sep + 1:][:longest]                 # the description as sold, cut where generating would stop
        else:
            options = {option: value for option, value in chosen.items() if option != "sample"}
            # generate samples when it's given a generator, and is greedy without one. Each product gets its own
            # seed, the same for every sampling setting, so the settings differ only in how they choose.
            rng = np.random.default_rng(seed + number) if chosen.get("sample") else None
            written = decoding.generate(start, rng=rng, longest=longest, **options)
        rows.append(decoding.measures(start, written))        # repetition, each token's log-probability, ended, uses the name, length
    repeated, log_p, ended, uses_name, length = zip(*rows)
    print(f"{label}, repeated 4-token phrases:", f"{np.mean(repeated):.0%}")
    print(f"{label}, the model's perplexity of the text:", f"{np.exp(-np.concatenate(log_p).mean()):.1f}")   # over all 20 texts' tokens at once
    print(f"{label}, ended within {longest} tokens:", f"{np.mean(ended):.0%}")
    print(f"{label}, uses a whole word of the name:", f"{np.mean(uses_name):.0%}")
    print(f"{label}, average length in tokens:", f"{np.mean(length):.0f}")
```

---

## Notes

| What | Why it's there |
| --- | --- |
| The docstring | What the example shows, and how to read its output: seven settings, five measures each, the real descriptions as the bar. It doesn't say what the output found; the prose does that. |
| `from lib import decoding` | `generate` and `measures` live in the book's shared module. A reader who copies the file needs to know that, and what the module holds. |
| The block comment on `described` | `sep < len(ids) - 2` encodes a fact about the data: a text is the start marker, the name, `<sep>`, the description and the end marker, so a product with a description has at least one token between `<sep>` and the end. And the comment says why validation products: the model never saw them. |
| `ids[:sep + 1]`, `ids[sep + 1:][:longest]` | Offsets are where copied code breaks. Each says, in the prose's words, which part of the text it keeps. |
| The comment on `rng` | Two hidden decisions: `generate` samples only when it gets a generator, and `seed + number` gives each product the same stream in every sampling setting, so the settings differ only in how they choose. Without it, a reader can't tell whether the differences are the method or the luck. |
| `decoding.measures` | The five-tuple's order is otherwise documented only inside `lib`. |
| The perplexity line | Pooled over every token of every text, not averaged per text. The two differ, and the prose quotes this one. |

What the example doesn't comment: the `print` lines, whose labels already say what each prints; `zip(*rows)`; and the settings list, which names each setting in words. And no comment says what the output found, such as "greedy repeats itself most": that's the prose's job, and it changes when the model does.

The docstring and the comment lines don't count toward W-18's limit, so explaining an example never pushes it over.
