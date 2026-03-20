---
name: pdf-convert
description: Convert PDF files to text, markdown, or structured data — extract content, tables, and metadata. Auto-triggers when user shares a PDF path.
---

Convert PDF files to readable text, markdown, or structured data.

## When to Trigger

- User shares a PDF file path
- User says "convert this PDF", "extract text from PDF", "read this PDF"
- User drops a PDF path in the conversation
- User asks to summarize or analyze a PDF document

## Steps

### 1. Extract text from PDF
Use pypdf (already a dependency) to extract text:

```python
from pypdf import PdfReader

reader = PdfReader("path/to/file.pdf")
text = ""
for page in reader.pages:
    text += page.extract_text() + "\n\n"
```

Or use the Read tool directly — elephant-coder's Read tool supports PDF files natively.

### 2. Choose output format

**Plain text** (default):
- Raw extracted text, page-separated
- Best for: quick reading, searching, copying

**Markdown** (when user wants structured output):
- Detect headings (larger font, bold, ALL CAPS) → `##` headers
- Detect lists → markdown lists
- Detect tables → markdown tables
- Best for: documentation, notes, further processing

**Structured data** (when user wants to analyze):
- Extract metadata (title, author, creation date, page count)
- Extract per-page text
- Detect and extract tables if present
- Best for: data extraction, analysis pipelines

### 3. Handle the output

**For small PDFs (< 10 pages)**:
- Display the full text directly

**For large PDFs (10+ pages)**:
- Show metadata and page count first
- Ask which pages to extract, or summarize
- Use `Read` tool with `pages` parameter for specific page ranges

**For ingestion into elephant-coder memory**:
- Call `ingest_knowledge()` to index the PDF content
- Or call `remember()` with key findings as notes

### 4. Post-processing options
Offer the user:
- "Save as markdown?" → write to `.md` file
- "Index into memory?" → call `ingest_knowledge()`
- "Summarize?" → provide a concise summary
- "Extract tables?" → detect and format tables

## Tips

- pypdf handles most PDFs well but scanned/image PDFs need OCR (not supported natively)
- For large PDFs, always use the `pages` parameter with the Read tool
- Maximum 20 pages per Read call — batch if needed
- The indexer already supports PDF files — `index_all()` processes `.pdf` files automatically
