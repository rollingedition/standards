# Exemplar: a figure drawn by an example

A passage from *Time series forecasting*, chapter 4, "Fit a statistical model for each client", with the figure its example draws (W-82), and notes. Numbers in the prose are bindings to the examples' recorded outputs (W-26), shown here as written in the source.

A figure carries a concept the chapter teaches. An example draws it from the book's own data and prints every value the prose says about it. The prose names what to see in it, next to it, so a listener who never sees the picture still gets its point (W-54).

---

## The example

`examples/figure-smoothing-weights.py` draws the weights exponential smoothing gives each of the last 24 readings, and prints the values the paragraphs below quote:

```python
"""Draw the weight exponential smoothing gives each of the last 24 readings, for alpha 0.2 and 0.5.
The lines name the weight on the newest reading, how many readings hold half the weight, and what is left past a day."""
import numpy as np

from lib.figures import ACCENT, MUTED, new_figure, save
from lib.settings import show

ages = np.arange(24)                                            # 0 is the newest reading, 23 the oldest in a day
fig, ax = new_figure(height=2.6)
for alpha, color in ((0.2, MUTED), (0.5, ACCENT)):
    weights = alpha * (1 - alpha) ** ages                       # level_t = alpha*y_t + (1-alpha)*level_(t-1), unrolled
    half = int(np.argmax(np.cumsum(weights) >= 0.5)) + 1        # the fewest newest readings that carry half the weight
    show(f"weight on the newest reading, alpha {alpha}", weights[0])
    show(f"readings that carry half the weight, alpha {alpha}", half)
    show(f"weight left on readings older than a day, alpha {alpha}", (1 - alpha) ** 24, digits=4)
    ax.plot(ages, weights, color=color, marker="o", markersize=3, linewidth=1.4, label=f"alpha = {alpha}")
ax.set_xlabel("age of the reading, hours")
ax.set_ylabel("weight in the level")
ax.set_ylim(bottom=0)
ax.legend(frameon=False)
save(fig, "smoothing-weights")
```

## The passage

Unrolled all the way back, the newest reading has weight alpha and each older one the weight before it times `1 - alpha`, so the weights decrease exponentially, as [*Forecasting: Principles and Practice*, section 8.1](https://otexts.com/fpp3/ses.html) puts it. {{fig:smoothing-weights}} draws the weights for two values of alpha, 0.2 and 0.5.

![The newest reading weighs most, and a smaller alpha spreads weight back](../examples/figures/smoothing-weights.svg "The weight each of the last 24 readings carries")

[Example: figure-smoothing-weights](../examples/figure-smoothing-weights.py)

At alpha 0.5 the newest reading carries {{out:figure-smoothing-weights:weight on the newest reading, alpha 0.5}}, and {{out:figure-smoothing-weights:readings that carry half the weight, alpha 0.5}} reading holds half. At alpha 0.2 it carries {{out:figure-smoothing-weights:weight on the newest reading, alpha 0.2}}, and {{out:figure-smoothing-weights:readings that carry half the weight, alpha 0.2}} readings hold at least half.

The weight past a day is {{out:figure-smoothing-weights:weight left on readings older than a day, alpha 0.2}} at alpha 0.2 and {{out:figure-smoothing-weights:weight left on readings older than a day, alpha 0.5}} at alpha 0.5. At alpha 1 the level is the last reading, so the forecast is the [naive](#three-baselines-to-beat) one. Near alpha 0 the level barely moves. At any alpha the forecast is flat and cannot follow {{fig:lead-client-fortnight}}'s daily rise and fall, so ETS adds a season.

## Notes

- **It carries a concept.** The formula says the weights fall with age; the figure shows how fast, and how alpha changes that, which a column of 48 numbers hides. From the weights the passage reaches the formula's two limits and the reason the next model adds a season.
- **The prose says what to see, and nothing the example doesn't print.** Each number is a printed line, bound. "At least half" is there because 4 readings hold 59%, not half: the first draft said "hold half", and the fact-check caught it. A sentence about a figure rests on a line the example prints, never on reading a value off the picture.
- **The alt text states the point** ("the newest reading weighs most, and a smaller alpha spreads weight back"); the caption says what it draws. Neither is "Smoothing weights chart".
- **No number is typed for the figure.** `{{fig:smoothing-weights}}` becomes "Figure 4.2", and the last paragraph points back to another figure the same way.
- **Colour isn't alone.** Each line is named in the legend, and the prose names them by alpha, not by colour.
- **The rest of the section is unchanged.** The figure came with the two paragraphs it needed, and nothing else in the section moved.
