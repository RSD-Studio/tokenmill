"""Not a library — a package marker.

`docs/article/` holds two generator scripts and a test that imports them, and
without `__init__.py` here mypy sees `make_tables` and `docs.article.make_tables`
as two different modules for one file and refuses to check either. Nothing
imports `docs` itself, and nothing should.
"""
