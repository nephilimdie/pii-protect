"""Document detection throughput: sequential vs parallel windows, real models.

Why: document jobs are CPU-bound on the three detector layers; the speed-up from
parallel window detection must be measured on the real models, and the parallel
output must be identical to the sequential output (same entities, same order).
What: generates synthetic dense PDFs (about 2,200 chars per page with Italian PII:
names, fiscal codes, IBANs, e-mails, phones, addresses), extracts their text with
the engine's PDF loader, runs the engine's windowed detection once per worker
setting and prints chars/s, wall time and whether the entities equal the
sequential baseline. No document content is printed; only counts and timings.
Test: run inside the engine image with the API mounted at /app and a populated
model cache (see benchmark/README.md, "Document throughput").
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import io
import json
import os
import random
import sys
import time

sys.path.insert(0, "/app")

FIRST = ["Mario", "Giulia", "Luca", "Francesca", "Marco", "Chiara", "Alessandro", "Sara", "Paolo", "Elena"]
LAST = ["Rossi", "Bianchi", "Esposito", "Romano", "Colombo", "Ricci", "Marino", "Greco", "Bruno", "Gallo"]
CITY = ["Milano", "Roma", "Torino", "Napoli", "Bologna", "Firenze", "Padova", "Verona"]
FILLER = (
    "Le parti convengono che il presente accordo disciplina in modo esclusivo gli obblighi reciproci. ",
    "Ogni comunicazione dovra essere inviata per iscritto agli indirizzi indicati di seguito. ",
    "Il corrispettivo sara versato entro trenta giorni dalla ricezione della fattura. ",
    "In caso di inadempimento la parte non inadempiente potra recedere con preavviso. ",
)


def _cf(rng: random.Random) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    pick = lambda n: "".join(rng.choice(letters) for _ in range(n))  # noqa: E731
    return f"{pick(6)}{rng.randint(10, 99)}{rng.choice('ABCDEHLMPRST')}{rng.randint(10, 69)}{pick(1)}{rng.randint(100, 999)}{pick(1)}"


def _sentence(rng: random.Random) -> str:
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    kind = rng.randrange(6)
    if kind == 0:
        return f"Il sig. {name}, nato a {rng.choice(CITY)}, codice fiscale {_cf(rng)}, dichiara quanto segue. "
    if kind == 1:
        return f"Il pagamento avverra sul conto IBAN IT{rng.randint(10, 99)}X0542811101000000{rng.randint(100000, 999999)}. "
    if kind == 2:
        return f"Per informazioni contattare {name} all'indirizzo {name.split()[0].lower()}.{name.split()[1].lower()}@example.it. "
    if kind == 3:
        return f"Recapito telefonico: +39 3{rng.randint(10, 99)} {rng.randint(1000000, 9999999)}. "
    if kind == 4:
        return f"Residente in Via {rng.choice(LAST)} {rng.randint(1, 200)}, {rng.randint(10100, 98100)} {rng.choice(CITY)}. "
    return rng.choice(FILLER)


def dense_pdf(pages: int, seed: int = 7) -> bytes:
    """About 2,200 extracted characters per A4 page, about 25% PII-bearing sentences."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    rng = random.Random(seed)
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=A4)
    for _ in range(pages):
        pdf.setFont("Helvetica", 8)
        text, rows = "", 0
        while rows < 40:
            text += _sentence(rng)
            while len(text) >= 55 and rows < 40:
                cut = text.rfind(" ", 0, 56)
                cut = cut if cut > 0 else 55
                pdf.drawString(40, 800 - rows * 19, text[:cut])
                text, rows = text[cut:].lstrip(), rows + 1
        pdf.showPage()
    pdf.save()
    return out.getvalue()


async def _anonymizer():
    from app.anonymization.anonymizer import PiiAnonymizer
    from app.main import app

    context = app.router.lifespan_context(app)
    await context.__aenter__()
    return context, PiiAnonymizer(app.state.registry, denylist=app.state.denylist)


def _detect(anonymizer, text: str, workers: int) -> tuple[list, float]:
    from app.config import settings
    from app.documents import chunking

    kwargs = {}
    if "executor" in inspect.signature(chunking.detect_in_windows).parameters and workers > 1:
        kwargs["executor"] = chunking.detection_executor(workers)
    started = time.perf_counter()
    entities = chunking.detect_in_windows(
        lambda chunk: anonymizer.detect_only(chunk, "bench", "generic", "it").entities, text,
        settings.document_detection_window_chars, settings.document_detection_window_overlap, **kwargs)
    return entities, time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", default="40,180", help="comma-separated page counts")
    parser.add_argument("--workers", default="1,4", help="comma-separated window worker counts (1 = sequential)")
    parser.add_argument("--output", help="write the JSON result here")
    args = parser.parse_args()

    from app.documents.models import DocumentLimits, JoinedText
    from app.documents.service import load_document

    context, anonymizer = asyncio.run(_anonymizer())
    limits = DocumentLimits(max_bytes=200_000_000, max_pages=2_000, pdf_dpi=200, max_pixels=16_000_000)
    rows = []
    for pages in [int(p) for p in args.pages.split(",")]:
        text = JoinedText(load_document(dense_pdf(pages), limits).segments).text
        baseline = None
        for workers in [int(w) for w in args.workers.split(",")]:
            entities, seconds = _detect(anonymizer, text, workers)
            key = [(e.start, e.end, e.pii_type, round(e.score, 6)) for e in entities]
            baseline = key if baseline is None else baseline
            row = {"pages": pages, "chars": len(text), "workers": workers, "seconds": round(seconds, 2),
                   "chars_per_s": round(len(text) / seconds), "entities": len(entities),
                   "identical_to_first": key == baseline, "cpus": os.cpu_count()}
            rows.append(row)
            print(json.dumps(row), flush=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as out:
            json.dump(rows, out, indent=2)
    del context


if __name__ == "__main__":
    main()
