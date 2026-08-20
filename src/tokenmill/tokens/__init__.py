"""Token measurement: tokenizer adapters, the registry and the meter.

Token counting is the product's central feature, not a reporting detail, so this
package holds to one rule above all others: **never report a count we did not
measure.** When a tokenizer cannot be loaded the count is ``None`` and the user
is told why. There is no estimate, no rule-of-thumb fallback, no
characters-divided-by-four.
"""

from __future__ import annotations

__all__: list[str] = []
