# Benchmark results

Run at **2026-08-27T20:40:02+00:00** on Linux 6.18.44-fc-v22 on x86_64, Python 3.11.15, 4 cores.

- tokenmill `0.1.0` at commit `e8a206556e7678b58299d8c8d67a2c5d34dc70c0`
- corpus digest `cd2d48ccf99bddb4`
- **N = 5** timed repeats per cell, plus one discarded warm-up and one instrumented pass for memory
- counted in: `bytes`

**About this run:**

- Run with --allow-network, so backends that fetch were able to. repomix's first conversion may include an npx package download; its warm-up run absorbs it, but treat its timing as the least reliable figure here.
- Counted in UTF-8 bytes only. A byte figure is NOT a token figure: on this project's own tabular data the two disagreed by 24 points and did not rank the serialisation formats in the same order. Model-token rows come from a CI run and are merged in.
- No usable GPU (none), so no heavy backend took part. Every OCR row is absent rather than zero.
- backends not installed here, so they have no rows: code2prompt, crawl4ai, deepseek_ocr, docling, dots_ocr, marker, mineru, olmocr, surya

## Counted in `bytes`

Counts are UTF-8 bytes, **not model tokens**.

Rows are in the registry's preference order within each fixture, **not**
sorted by size. On `tables.pdf` the cheapest backend is the one that
flattens the table, so a leaderboard here would recommend whichever
converter destroyed the most.

| Fixture | Backend | Tokens | Change | Fidelity | Scored | Median | N | Spread |
|---|---|---|---|---|---|---|---|---|
| `article.html` | `trafilatura` | 2,854 | −19.8% | 1.000 | 3 | 4 ms | 5 | 1.4x |
| `article.html` | `readability` | 2,864 | −19.6% | 1.000 | 3 | 8 ms | 5 | 1.1x |
| `article.html` | `markdownify_html` | 2,916 | −18.1% | 1.000 | 3 | 5 ms | 5 | 1.2x |
| `article.html` | `markitdown` | 2,864 | −19.6% | 1.000 | 3 | 38 ms | 5 | 2.7x |
| `article.html` | `kreuzberg` | 3,063 | −14.0% | 1.000 | 3 | 1 ms | 5 | 1.3x |
| `article.html` | `pandoc` | 3,072 | −13.7% | 1.000 | 3 | 56 ms | 5 | 1.0x |
| `boilerplate.html` | `trafilatura` | 2,854 | −77.1% | 1.000 | 4 | 10 ms | 5 | 1.1x |
| `boilerplate.html` | `readability` | 2,864 | −77.1% | 1.000 | 4 | 19 ms | 5 | 1.2x |
| `boilerplate.html` | `markdownify_html` | 6,802 | −45.5% | 0.750 | 4 | 21 ms | 5 | 1.1x |
| `boilerplate.html` | `markitdown` | 6,713 | −46.2% | 0.750 | 4 | 49 ms | 5 | 1.2x |
| `boilerplate.html` | `kreuzberg` | 6,120 | −51.0% | 0.750 | 4 | 2 ms | 5 | 1.2x |
| `boilerplate.html` | `pandoc` | 7,346 | −41.1% | 0.750 | 4 | 76 ms | 5 | 1.4x |
| `corrupt.pdf` | `pdfplumber` | **fail** | — | n/a | 0 | — | 0 | — |
| `corrupt.pdf` | `kreuzberg` | **fail** | — | n/a | 0 | — | 0 | — |
| `corrupt.pdf` | `markitdown` | **fail** | — | n/a | 0 | — | 0 | — |
| `corrupt.pdf` | `pypdf` | **fail** | — | n/a | 0 | — | 0 | — |
| `corrupt.pdf` | `pymupdf4llm` | **fail** | — | n/a | 0 | — | 0 | — |
| `data.xlsx` | `markitdown` | 675 | — | 0.667 | 1 | 54 ms | 5 | 1.1x |
| `data.xlsx` | `kreuzberg` | 664 | — | 1.000 | 1 | 3 ms | 5 | 1.1x |
| `data.xlsx` | `libreoffice` | **fail** | — | n/a | 0 | — | 0 | — |
| `deck.pptx` | `markitdown` | 753 | — | 1.000 | 1 | 54 ms | 5 | 1.6x |
| `deck.pptx` | `kreuzberg` | 398 | — | 1.000 | 1 | 3 ms | 5 | 1.1x |
| `deck.pptx` | `libreoffice` | **fail** | — | n/a | 0 | — | 0 | — |
| `jsrendered.html` | `trafilatura` | 140 | −90.7% | 0.000 | 3 | 2 ms | 5 | 1.3x |
| `jsrendered.html` | `readability` | 167 | −89.0% | 0.000 | 3 | 2 ms | 5 | 1.1x |
| `jsrendered.html` | `markdownify_html` | 165 | −89.1% | 0.000 | 3 | 1 ms | 5 | 1.3x |
| `jsrendered.html` | `markitdown` | 140 | −90.7% | 0.000 | 3 | 35 ms | 5 | 1.2x |
| `jsrendered.html` | `kreuzberg` | 180 | −88.1% | 0.000 | 3 | 0 ms | 5 | 1.2x |
| `jsrendered.html` | `pandoc` | 225 | −85.1% | 0.000 | 3 | 15 ms | 5 | 1.1x |
| `long_context.md` | `plaintext` | 79,255 | −0.0% | n/a | 0 | 1 ms | 5 | 1.2x |
| `long_context.md` | `pandoc` | 79,255 | −0.0% | n/a | 0 | 237 ms | 5 | 1.1x |
| `report.docx` | `markitdown` | 3,494 | — | 0.841 | 4 | 346 ms | 5 | 1.4x |
| `report.docx` | `kreuzberg` | 3,472 | — | 0.614 | 4 | 7 ms | 5 | 1.1x |
| `report.docx` | `pandoc` | 3,567 | — | 0.841 | 4 | 167 ms | 5 | 1.1x |
| `report.docx` | `libreoffice` | 3,418 | — | 0.375 | 4 | 1,466 ms | 5 | 1.0x |
| `scanned.pdf` | `pdfplumber` | 0 **(empty)** | — | 0.000 | 2 | 3 ms | 5 | 1.3x |
| `scanned.pdf` | `kreuzberg` | 0 **(empty)** | — | 0.000 | 2 | 5 ms | 5 | 1.2x |
| `scanned.pdf` | `markitdown` | 0 **(empty)** | — | 0.000 | 2 | 37 ms | 5 | 1.2x |
| `scanned.pdf` | `pypdf` | 0 **(empty)** | — | 0.000 | 2 | 2 ms | 5 | 1.3x |
| `scanned.pdf` | `pymupdf4llm` | **fail** | — | n/a | 0 | — | 0 | — |
| `simple.pdf` | `pdfplumber` | 2,370 | — | 0.500 | 2 | 79 ms | 5 | 3.4x |
| `simple.pdf` | `kreuzberg` | 2,371 | — | 0.900 | 2 | 15 ms | 5 | 1.1x |
| `simple.pdf` | `markitdown` | 2,377 | — | 0.500 | 2 | 135 ms | 5 | 1.9x |
| `simple.pdf` | `pypdf` | 2,371 | — | 0.500 | 2 | 9 ms | 5 | 1.0x |
| `simple.pdf` | `pymupdf4llm` | 2,410 | — | 1.000 | 2 | 1,152 ms | 5 | 1.1x |
| `structured.md` | `plaintext` | 1,466 | −0.2% | 1.000 | 4 | 0 ms | 5 | 1.5x |
| `structured.md` | `pandoc` | 1,609 | +9.5% | 0.977 | 4 | 35 ms | 5 | 1.0x |
| `tables.pdf` | `pdfplumber` | 599 | — | 0.667 | 3 | 26 ms | 5 | 1.1x |
| `tables.pdf` | `kreuzberg` | 466 | — | 0.500 | 3 | 9 ms | 5 | 1.1x |
| `tables.pdf` | `markitdown` | 769 | — | 0.606 | 3 | 50 ms | 5 | 1.1x |
| `tables.pdf` | `pypdf` | 481 | — | 0.333 | 3 | 5 ms | 5 | 1.1x |
| `tables.pdf` | `pymupdf4llm` | 553 | — | 0.848 | 3 | 1,168 ms | 5 | 1.1x |
| `twocolumn.pdf` | `pdfplumber` | 4,050 | — | 0.528 | 3 | 151 ms | 5 | 1.8x |
| `twocolumn.pdf` | `kreuzberg` | 4,061 | — | 0.667 | 3 | 24 ms | 5 | 1.1x |
| `twocolumn.pdf` | `markitdown` | 4,062 | — | 0.528 | 3 | 311 ms | 5 | 1.5x |
| `twocolumn.pdf` | `pypdf` | 4,050 | — | 0.667 | 3 | 13 ms | 5 | 1.1x |
| `twocolumn.pdf` | `pymupdf4llm` | 4,069 | — | 0.972 | 3 | 1,316 ms | 5 | 1.1x |
| `unicode.docx` | `markitdown` | 1,312 | — | 0.955 | 2 | 322 ms | 5 | 1.3x |
| `unicode.docx` | `kreuzberg` | 1,314 | — | 1.000 | 2 | 7 ms | 5 | 1.1x |
| `unicode.docx` | `pandoc` | 1,327 | — | 1.000 | 2 | 167 ms | 5 | 1.2x |
| `unicode.docx` | `libreoffice` | 1,274 | — | 0.500 | 2 | 1,446 ms | 5 | 1.2x |
| `sample_repo` | `gitingest` | 2,944 | — | 1.000 | 2 | 271 ms | 5 | 2.9x |
| `sample_repo` | `repomix` | 3,786 | — | 1.000 | 2 | 1,518 ms | 5 | 1.2x |

## Failures and empty outputs

These are results rather than omissions. A benchmark that reported only
the cells that worked would be a marketing document.

| Fixture | Backend | Error | Message |
|---|---|---|---|
| `corrupt.pdf` | `pdfplumber` | `CorruptSource` | corrupt.pdf could not be parsed: PdfminerException: Unexpected EOF: caused by PSEOF: Unexpected EOF: caused by PDFNoValidXRef: Unexpected EOF (the file appears  |
| `corrupt.pdf` | `kreuzberg` | `CorruptSource` | corrupt.pdf could not be parsed: ParsingError: ParsingError: Invalid PDF: PdfiumLibraryInternalError: FormatError: Invalid PDF: PdfiumLibraryInternalError: Form |
| `corrupt.pdf` | `markitdown` | `CorruptSource` | corrupt.pdf could not be parsed: FileConversionException: File conversion failed after 1 attempts:  - PdfConverter threw PSEOF with message: Unexpected EOF (the |
| `corrupt.pdf` | `pypdf` | `CorruptSource` | corrupt.pdf could not be parsed: PdfStreamError: Stream has ended unexpectedly (the file appears damaged or truncated; check it opens in a normal viewer) |
| `corrupt.pdf` | `pymupdf4llm` | `CorruptSource` | corrupt.pdf could not be parsed: pymupdf.FileDataError: Failed to open file '<repo>/tests/fixtures/corrupt.pdf' as type pdf. (the file appears damaged or trunca |
| `data.xlsx` | `libreoffice` | `BackendFailed` | libreoffice wrote no output for data.xlsx (it exits 0 even when it converts nothing) (check that the file really is the format its extension claims) |
| `deck.pptx` | `libreoffice` | `BackendFailed` | libreoffice wrote no output for deck.pptx (it exits 0 even when it converts nothing) (check that the file really is the format its extension claims) |
| `scanned.pdf` | `pymupdf4llm` | `BackendFailed` | pymupdf4llm produced no text for scanned.pdf (the PDF may be a scan with no text layer; try an OCR backend) |

**Succeeded and produced nothing**, which is the single most
misleading cell a benchmark can contain: it scores a 100% reduction.

| Fixture | Backend | Fidelity |
|---|---|---|
| `scanned.pdf` | `pdfplumber` | 0.000 |
| `scanned.pdf` | `kreuzberg` | 0.000 |
| `scanned.pdf` | `markitdown` | 0.000 |
| `scanned.pdf` | `pypdf` | 0.000 |

## Wall time and memory

**N = 5** timed repeats per cell, median and spread. The
spread is `slowest / fastest`, which says more on this sample size than a
standard deviation would.

`added RSS` is how much resident memory the conversion added to this
process **and its descendants**, sampled every 5 ms: the peak during the
cell minus the reading taken immediately before it. It is the only
figure here that means anything for a subprocess backend, and the only
one that is comparable between rows.

`peak RSS` is the raw peak, published beside it so the subtraction is
checkable. **Do not compare peaks between rows.** A Python process's
resident set does not shrink, so the peak column climbs through the run
as each cell inherits every library the earlier cells imported; the last
row's peak is mostly the first fifty rows' imports. Both figures are
lower bounds: a peak occurring between two samples is missed.

`peak Python` is `tracemalloc`'s peak: exact for Python objects, blind to
everything else. The two are different measurements and neither is *the*
memory used.

| Fixture | Backend | Median | Min | Max | Spread | Added RSS | Peak RSS | Peak Python | Version |
|---|---|---|---|---|---|---|---|---|---|
| `article.html` | `trafilatura` | 4 ms | 4 ms | 6 ms | 1.4x | 0 MiB | 50 MiB | 0.1 MiB | 2.2.0 |
| `article.html` | `readability` | 8 ms | 7 ms | 8 ms | 1.1x | 0 MiB | 53 MiB | 0.1 MiB | 0.8.4.1 |
| `article.html` | `markdownify_html` | 5 ms | 5 ms | 6 ms | 1.2x | 0 MiB | 54 MiB | 0.1 MiB | 1.2.3 |
| `article.html` | `markitdown` | 38 ms | 36 ms | 99 ms | 2.7x | 8 MiB | 217 MiB | 0.3 MiB | 0.1.7 |
| `article.html` | `kreuzberg` | 1 ms | 1 ms | 1 ms | 1.3x | 0 MiB | 251 MiB | 0.0 MiB | 4.10.2 |
| `article.html` | `pandoc` | 56 ms | 56 ms | 56 ms | 1.0x | 108 MiB | 359 MiB | 0.1 MiB | pandoc 3.1.3 |
| `boilerplate.html` | `trafilatura` | 10 ms | 10 ms | 11 ms | 1.1x | 0 MiB | 251 MiB | 0.2 MiB | 2.2.0 |
| `boilerplate.html` | `readability` | 19 ms | 17 ms | 20 ms | 1.2x | 0 MiB | 251 MiB | 0.3 MiB | 0.8.4.1 |
| `boilerplate.html` | `markdownify_html` | 21 ms | 20 ms | 23 ms | 1.1x | 0 MiB | 251 MiB | 0.5 MiB | 1.2.3 |
| `boilerplate.html` | `markitdown` | 49 ms | 45 ms | 54 ms | 1.2x | 10 MiB | 259 MiB | 0.6 MiB | 0.1.7 |
| `boilerplate.html` | `kreuzberg` | 2 ms | 2 ms | 2 ms | 1.2x | 0 MiB | 259 MiB | 0.1 MiB | 4.10.2 |
| `boilerplate.html` | `pandoc` | 76 ms | 76 ms | 106 ms | 1.4x | 111 MiB | 371 MiB | 0.1 MiB | pandoc 3.1.3 |
| `data.xlsx` | `markitdown` | 54 ms | 51 ms | 58 ms | 1.1x | 10 MiB | 305 MiB | 0.5 MiB | 0.1.7 |
| `data.xlsx` | `kreuzberg` | 3 ms | 3 ms | 3 ms | 1.1x | 0 MiB | 306 MiB | 0.0 MiB | 4.10.2 |
| `deck.pptx` | `markitdown` | 54 ms | 54 ms | 85 ms | 1.6x | 0 MiB | 340 MiB | 0.5 MiB | 0.1.7 |
| `deck.pptx` | `kreuzberg` | 3 ms | 3 ms | 3 ms | 1.1x | 0 MiB | 340 MiB | 0.2 MiB | 4.10.2 |
| `jsrendered.html` | `trafilatura` | 2 ms | 1 ms | 2 ms | 1.3x | 0 MiB | 340 MiB | 0.0 MiB | 2.2.0 |
| `jsrendered.html` | `readability` | 2 ms | 2 ms | 3 ms | 1.1x | 0 MiB | 340 MiB | 0.0 MiB | 0.8.4.1 |
| `jsrendered.html` | `markdownify_html` | 1 ms | 1 ms | 2 ms | 1.3x | 0 MiB | 340 MiB | 0.0 MiB | 1.2.3 |
| `jsrendered.html` | `markitdown` | 35 ms | 32 ms | 38 ms | 1.2x | 0 MiB | 360 MiB | 0.3 MiB | 0.1.7 |
| `jsrendered.html` | `kreuzberg` | 0 ms | 0 ms | 0 ms | 1.2x | 0 MiB | 341 MiB | 0.0 MiB | 4.10.2 |
| `jsrendered.html` | `pandoc` | 15 ms | 14 ms | 15 ms | 1.1x | 28 MiB | 369 MiB | 0.1 MiB | pandoc 3.1.3 |
| `long_context.md` | `plaintext` | 1 ms | 1 ms | 1 ms | 1.2x | 0 MiB | 341 MiB | 0.3 MiB | — |
| `long_context.md` | `pandoc` | 237 ms | 217 ms | 248 ms | 1.1x | 123 MiB | 464 MiB | 0.3 MiB | pandoc 3.1.3 |
| `report.docx` | `markitdown` | 346 ms | 329 ms | 445 ms | 1.4x | 0 MiB | 357 MiB | 15.5 MiB | 0.1.7 |
| `report.docx` | `kreuzberg` | 7 ms | 6 ms | 7 ms | 1.1x | 0 MiB | 357 MiB | 0.1 MiB | 4.10.2 |
| `report.docx` | `pandoc` | 167 ms | 167 ms | 177 ms | 1.1x | 125 MiB | 482 MiB | 0.1 MiB | pandoc 3.1.3 |
| `report.docx` | `libreoffice` | 1,466 ms | 1,433 ms | 1,490 ms | 1.0x | 263 MiB | 620 MiB | 0.1 MiB | LibreOffice 24.2.7.2 420(Build:2) |
| `scanned.pdf` | `pdfplumber` | 3 ms | 3 ms | 4 ms | 1.3x | 0 MiB | 357 MiB | 0.4 MiB | 0.11.10 |
| `scanned.pdf` | `kreuzberg` | 5 ms | 4 ms | 5 ms | 1.2x | 0 MiB | 360 MiB | 0.2 MiB | 4.10.2 |
| `scanned.pdf` | `markitdown` | 37 ms | 34 ms | 40 ms | 1.2x | 0 MiB | 360 MiB | 0.7 MiB | 0.1.7 |
| `scanned.pdf` | `pypdf` | 2 ms | 2 ms | 3 ms | 1.3x | 0 MiB | 360 MiB | 0.5 MiB | 6.16.1 |
| `simple.pdf` | `pdfplumber` | 79 ms | 75 ms | 255 ms | 3.4x | 0 MiB | 366 MiB | 4.4 MiB | 0.11.10 |
| `simple.pdf` | `kreuzberg` | 15 ms | 15 ms | 17 ms | 1.1x | 0 MiB | 366 MiB | 0.0 MiB | 4.10.2 |
| `simple.pdf` | `markitdown` | 135 ms | 131 ms | 248 ms | 1.9x | 0 MiB | 363 MiB | 2.3 MiB | 0.1.7 |
| `simple.pdf` | `pypdf` | 9 ms | 9 ms | 9 ms | 1.0x | 0 MiB | 363 MiB | 0.2 MiB | 6.16.1 |
| `simple.pdf` | `pymupdf4llm` | 1,152 ms | 1,136 ms | 1,203 ms | 1.1x | 322 MiB | 685 MiB | 0.1 MiB | pymupdf4llm 1.28.2 |
| `structured.md` | `plaintext` | 0 ms | 0 ms | 0 ms | 1.5x | 0 MiB | 363 MiB | 0.0 MiB | — |
| `structured.md` | `pandoc` | 35 ms | 35 ms | 35 ms | 1.0x | 64 MiB | 428 MiB | 0.1 MiB | pandoc 3.1.3 |
| `tables.pdf` | `pdfplumber` | 26 ms | 25 ms | 29 ms | 1.1x | 0 MiB | 363 MiB | 1.1 MiB | 0.11.10 |
| `tables.pdf` | `kreuzberg` | 9 ms | 8 ms | 9 ms | 1.1x | 0 MiB | 364 MiB | 0.0 MiB | 4.10.2 |
| `tables.pdf` | `markitdown` | 50 ms | 47 ms | 54 ms | 1.1x | 0 MiB | 364 MiB | 1.0 MiB | 0.1.7 |
| `tables.pdf` | `pypdf` | 5 ms | 5 ms | 5 ms | 1.1x | 0 MiB | 364 MiB | 0.1 MiB | 6.16.1 |
| `tables.pdf` | `pymupdf4llm` | 1,168 ms | 1,148 ms | 1,228 ms | 1.1x | 280 MiB | 644 MiB | 0.1 MiB | pymupdf4llm 1.28.2 |
| `twocolumn.pdf` | `pdfplumber` | 151 ms | 129 ms | 235 ms | 1.8x | 0 MiB | 364 MiB | 7.7 MiB | 0.11.10 |
| `twocolumn.pdf` | `kreuzberg` | 24 ms | 24 ms | 25 ms | 1.1x | 0 MiB | 365 MiB | 0.0 MiB | 4.10.2 |
| `twocolumn.pdf` | `markitdown` | 311 ms | 231 ms | 344 ms | 1.5x | 0 MiB | 364 MiB | 7.6 MiB | 0.1.7 |
| `twocolumn.pdf` | `pypdf` | 13 ms | 12 ms | 13 ms | 1.1x | 0 MiB | 364 MiB | 0.2 MiB | 6.16.1 |
| `twocolumn.pdf` | `pymupdf4llm` | 1,316 ms | 1,255 ms | 1,329 ms | 1.1x | 282 MiB | 646 MiB | 0.1 MiB | pymupdf4llm 1.28.2 |
| `unicode.docx` | `markitdown` | 322 ms | 304 ms | 409 ms | 1.3x | 0 MiB | 364 MiB | 15.5 MiB | 0.1.7 |
| `unicode.docx` | `kreuzberg` | 7 ms | 7 ms | 8 ms | 1.1x | 0 MiB | 364 MiB | 0.1 MiB | 4.10.2 |
| `unicode.docx` | `pandoc` | 167 ms | 157 ms | 188 ms | 1.2x | 124 MiB | 488 MiB | 0.1 MiB | pandoc 3.1.3 |
| `unicode.docx` | `libreoffice` | 1,446 ms | 1,432 ms | 1,683 ms | 1.2x | 263 MiB | 626 MiB | 0.1 MiB | LibreOffice 24.2.7.2 420(Build:2) |
| `sample_repo` | `gitingest` | 271 ms | 243 ms | 713 ms | 2.9x | 0 MiB | 368 MiB | 0.1 MiB | 0.3.1 |
| `sample_repo` | `repomix` | 1,518 ms | 1,452 ms | 1,707 ms | 1.2x | 279 MiB | 647 MiB | 0.1 MiB | — |

