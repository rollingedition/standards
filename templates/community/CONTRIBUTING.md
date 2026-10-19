# Contributing to Rolling Edition books

Rolling Edition books are free to read, and every book's text, examples and history are public. Agents publish every book, anyone can check it or correct it, and only serious risks go to a person. This guide covers every book repository in the organization.

## Ways to help

- **Report an error.** Open an issue on the book's repository with the "Report an error" form. Give the section's ID, the last part of the link beside each heading on the site, say what's wrong, and link a source if you have one.
- **Fix it.** Open a pull request. Small fixes are welcome without an issue first.
- **Check it.** Read the open pull requests and the latest edition, and say what you find: comment on a pull request, or open a fix of your own. Nothing waits for a review, so a correction is how a mistake gets fixed.
- **Ask a question.** Use the "Ask a question" form on the book's repository.

## How a change ships

1. **Checks run** on every pull request: every example runs in the book's pinned environment and must match its recorded output, the book's manifest and section IDs are validated, the writing standards' lint rules run, and the pull request needs one `kind:` label ({kinds}).
2. **The change is sorted and checked for serious risks.** An agent sorts it by kind: a typo fix, a version update or a change of meaning. Fixed rules, published in the [review tiers]({standards}/blob/main/data/review-tiers.toml), flag a serious risk, such as a change to the repository's workflows, a newly added package or a change to who the book credits; an agent's assessment can only add a flag, never remove one.
3. **It merges once its checks pass,** whatever kind of change it is: the agent approves it. A flagged change waits for a Rolling Edition maintainer instead. If something is still wrong after it ships, anyone can correct it with another pull request.
4. **The next edition is stamped** with its date, its examples passing and what changed.

## Writing

Follow the [writing standards]({standards}/blob/main/writing/README.md): every rule has an ID, and the checks and critics cite them. In short:

- Explain the idea, then make it concrete with the book's running case, then say what to do.
- Every claim about how a library or tool behaves is shown by an example in the book or sourced to its documentation, changelog or source code at the pinned version.
- Never type a number an example prints, or a library's version: write a binding, such as `{{out:example-id:label}}` or `{{version:pandas}}`, and the build fills it in.
- Examples run offline and give the same output every time. Model outputs are recorded once, with a manifest naming the model.

## Running the checks yourself

Install the standards and run the same checks as the pull request:

```sh
pip install "git+{standards}"
re-check examples --book . --backend venv
re-check style --book .
re-check section-ids --book .
```

## Using AI

You may use AI tools. You're responsible for what you contribute, and the same checks apply to it. Every book says plainly that it was written with AI and verified by people, which means in the open: anyone can check it and correct it.

## Credit

Everyone whose change ships is credited by name, or by the pseudonym you choose, in that edition. Nobody is credited for approving or checking a change. Rolling Edition is the author of every book.

## Conduct

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).

## Security

Don't report a security problem in an issue; see [SECURITY.md](SECURITY.md).
