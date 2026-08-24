---
title: A Structured Document
tags: [fixture, markdown, phase-5]
draft: false
---

## A Structured Document

An opening paragraph with an [inline link](https://example.com/inline) and a
[reference link][ref-one] in it.

![A diagram of the pipeline](images/pipeline.png)

#### A heading that skips a level

Converters routinely emit headings that start at H2 and skip levels. Heading
normalisation exists to repair that, and it is destructive because the original
levels are not recoverable afterwards.

- Strip navigation
- Strip advertising
- Strip cookie banners

1. Keep headings
2. Keep list markers
3. Keep table structure
   1. Nested detail under the last item

```python
# This is a comment, not a heading.
def render(cell: str) -> str:
    return f"| {cell} |"
```

Structure carries meaning: headings say how a document is organised, list markers say that items are peers, and table pipes say which cell belongs to which column.

### Measurements

| Stage | Tokens | Delta |
| --- | --- | --- |
| source | 16180 | - |
| converted | 3150 | -80.5% |
| post-processed | 2980 | -81.6% |

Structure carries meaning: headings say how a document is organised, list markers say that items are peers, and table pipes say which cell belongs to which column.

A closing paragraph.   
This file carries trailing spaces above and a run of blank lines below, so
the whitespace post-processors have something real to collapse.



[ref-one]: https://example.com/reference
