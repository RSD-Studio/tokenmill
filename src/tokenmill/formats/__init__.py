"""Serialisation formats for tabular data, and the registry that finds them.

`tokenmill compare --formats markdown,csv,toon,json` measures the same table in
each, so a user can see what a serialisation costs **on their own data** rather
than take a published benchmark's word for it.
"""

from tokenmill.formats.base import (
    FORMAT_ENTRY_POINT_GROUP,
    BaseTableEncoder,
    Table,
    TableEncoder,
    TableEncoderRegistry,
    TableError,
    default_format_registry,
    require_named_columns,
    reset_default_format_registry,
)

__all__ = [
    "FORMAT_ENTRY_POINT_GROUP",
    "BaseTableEncoder",
    "Table",
    "TableEncoder",
    "TableEncoderRegistry",
    "TableError",
    "default_format_registry",
    "require_named_columns",
    "reset_default_format_registry",
]
