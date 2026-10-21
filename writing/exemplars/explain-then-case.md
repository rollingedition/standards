# Exemplar: explain, then make it concrete

One section written to the house pattern (W-8), followed by notes on the rules it shows.

In a book, the code and the output blocks come from example files and their recorded outputs. The numbers in the prose are bindings to those outputs (W-26), so they change when the outputs do. Its running case is the orders table from the pipeline demo, run with pandas 2.2.2.

---

## Coerce bad values, then count them {#coerce-bad-values}

A column that should hold numbers often holds a few values that aren't numbers: a placeholder, a typo, a unit pasted into a cell. A strict conversion stops at the first bad value, which tells you that something is wrong but not how much. Coercing turns every value that can't be parsed into a missing value instead, so you can count the damage and choose a rule for it. In pandas, that's `pd.to_numeric` with `errors="coerce"`.

In the orders export, the `amount` column is stored as text, because one order says `pending` instead of a price. You need revenue per customer, so first find out how many orders you can't use. A strict conversion fails on the first bad value:

```python
pd.to_numeric(orders["amount"])
```

```
ValueError: Unable to parse string "pending" at position 3
```

Coercing turns that value into a gap you can count:

```python
orders["amount"] = pd.to_numeric(orders["amount"], errors="coerce")
print("unreadable amounts:", orders["amount"].isna().sum())
```

```
unreadable amounts: 1
```

Of 10 orders, 1 has no usable amount. That's few enough to drop and mention in the report. If a third of them were unreadable, the problem would be the export itself, and you'd ask for a better one before computing anything.

**Working rule:** Coerce, count, then decide. Drop the rows when the count is small and you know why the values are bad, and say so in your output. Use a strict conversion instead when one bad value means the whole source is wrong, as in a column of IDs.

---

## Notes

| Rule | Where the section applies it |
| --- | --- |
| W-8 Explain, then make it concrete | The first paragraph explains coercion in general terms. The second places it in the orders case and says what's at stake: revenue per customer. |
| W-9 Show the failure | The strict conversion runs, and its real error appears before the fix. |
| W-21 Print what the prose discusses | The example prints the one count the text uses. |
| W-26 Bind numbers from outputs | In the source, the sentence reads "Of {{out:load-orders:rows}} orders, {{out:fix-types:unreadable amounts}} has no usable amount." The build fills both in from labelled output lines, so `load-orders` prints a `rows: 10` line. "A third" is judgement, not output. |
| W-10 End with the working rule | "Working rule" closes the section, including when to choose differently. |
| W-13 Take positions | "Coerce, count, then decide" is a recommendation with a stated exception. |
| W-40 Sections stand alone | The section names its case ("the orders export", "the `amount` column") instead of pointing back to an earlier section. |
| W-41 Headings say what the section does | "Coerce bad values, then count them". |
| W-7 Length | About 250 words, near the short end for a section. |

What the section leaves out: the history of the function, every other value of `errors`, and any preview of the next section (W-6).
