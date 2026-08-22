"""Repository backends: a whole checkout as one prompt-ready document.

Three engines with one interface — gitingest in Python, Repomix in Node and
code2prompt in Rust. What they share, and what makes them one product rather
than three wrappers, lives in :mod:`tokenmill.backends.repo._common`: the same
include and exclude globs, the same ``.gitignore`` respect, the same budget
truncation in the run's own tokenizer, the same per-directory breakdown, and the
same shallow-clone-and-clean-up for a remote Git URL.
"""
