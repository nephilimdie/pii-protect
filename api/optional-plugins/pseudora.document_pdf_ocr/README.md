# Pseudora PDF OCR plugin

This optional plugin renders PDF pages, runs Tesseract OCR, sends only the OCR
text to the core detector, and returns an image-only PDF with detected regions
redacted. It does not persist the source document or OCR text.

Install the dependencies from `requirements.txt`, install the `ita` and `eng`
Tesseract language data, then set `PLUGIN_DIR` to the parent `optional-plugins`
directory and `PLUGIN_AUTOLOAD=true`.

The output intentionally removes the searchable text layer. This is a baseline
redaction plugin, not a claim of document or biometric coverage. Validate it
with authorized PDFs, rotated text, low-quality scans, multiple languages and
false-positive review before enabling it for customer traffic.
