# Pseudora OCR image plugin

This optional plugin redacts detected PII from PNG and JPEG images. It uses
Tesseract for OCR, passes OCR text through the existing engine detector, and
returns blacked-out regions plus coordinates. It does not create reversible
mapping entries or persist OCR text.

Install `requirements.txt` and the Tesseract binary with Italian and English
language packs in the image that loads the plugin. Review the source and
manifest, then set `PLUGIN_DIR` to this directory and enable
`PLUGIN_AUTOLOAD=true`.

The core remains text-first when the plugin is absent;
`POST /v1/anonymize/image` fails closed with `image_plugin_not_installed`.
The endpoint accepts JSON fields `image_base64`, `content_type`, `context_id`,
`context_type`, `language`, and `mode`, and returns JSON containing the
redacted image as base64 and non-sensitive region coordinates. Limits are
controlled by `PII_IMAGE_MAX_BYTES` and `PII_IMAGE_MAX_PIXELS`.
