from __future__ import annotations

import io
import zipfile
from collections import defaultdict

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.part import XmlPart
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from lxml import etree

from app.documents.models import DocumentError, DocumentFormat, SegmentEdit

_UNCOMPRESSED_RATIO = 10  # zip-bomb guard: max inflated size = ratio x upload limit

_W_P, _W_T, _W_INSTR = qn("w:p"), qn("w:t"), qn("w:instrText")
_EDITABLE = {_W_T, _W_INSTR}
_FIXED_ATOMS = {qn("w:tab"): "\t", qn("w:br"): "\n", qn("w:cr"): "\n"}

_CONTENT_RELS = {RT.HEADER, RT.FOOTER, RT.FOOTNOTES, RT.ENDNOTES}
# Parts dropped from the package by relationship-type suffix: they carry
# authors, comment text, cached data bindings or a first-page thumbnail.
_DROPPED_REL_SUFFIXES = {
    "comments", "commentsExtended", "commentsIds", "commentsExtensible", "people",
    "glossaryDocument", "customXml", "extended-properties", "custom-properties", "thumbnail",
}
# Removed with their content: tracked deletions, revision history, comment anchors.
_REMOVED_TAGS = [qn(f"w:{t}") for t in (
    "del", "moveFrom", "rPrChange", "pPrChange", "sectPrChange", "tblPrChange", "trPrChange",
    "tcPrChange", "tblGridChange", "numberingChange", "moveFromRangeStart", "moveFromRangeEnd",
    "moveToRangeStart", "moveToRangeEnd", "commentRangeStart", "commentRangeEnd", "commentReference",
    "attachedTemplate", "docVars",
)]
_UNWRAPPED_TAGS = [qn("w:ins"), qn("w:moveTo")]  # accepted insertions keep their runs
_CORE_TEXT_PROPS = (
    "author", "category", "comments", "content_status", "identifier", "keywords",
    "language", "last_modified_by", "subject", "title", "version",
)
DOCX_SANITIZED = (
    "core_properties", "app_properties", "custom_properties", "thumbnail", "comments",
    "tracked_changes", "hyperlink_targets", "image_alt_text", "attached_template",
    "custom_xml", "glossary",
)


def _check_zip(payload: bytes, max_bytes: int) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise DocumentError(422, "INVALID_DOCUMENT", "The DOCX file is corrupted.") from exc
    if not any(info.filename == "word/document.xml" for info in infos):
        raise DocumentError(415, "UNSUPPORTED_DOCUMENT_TYPE", "Only PDF, DOCX and plain-text files are supported.")
    if sum(info.file_size for info in infos) > max_bytes * _UNCOMPRESSED_RATIO:
        raise DocumentError(413, "DOCUMENT_TOO_LARGE", "The DOCX file expands beyond the allowed size.")


def _owner_paragraph(node):
    parent = node.getparent()
    while parent is not None and parent.tag != _W_P:
        parent = parent.getparent()
    return parent


def _atom_text(node) -> str:
    return (node.text or "") if node.tag in _EDITABLE else _FIXED_ATOMS[node.tag]


def _units(root) -> list[list]:
    """Paragraphs (own runs only, so nested text boxes are separate units) plus field codes."""
    units = []
    for paragraph in root.iter(_W_P):
        atoms = [n for n in paragraph.iter(_W_T, *_FIXED_ATOMS) if _owner_paragraph(n) is paragraph]
        units.append(atoms)
    units.extend([instr] for instr in root.iter(_W_INSTR))
    return units


def _apply(atoms: list, edits: list[SegmentEdit]) -> None:
    """Put each replacement in the first run it touches and cut the rest of the span
    out of following runs, so entities split across runs keep the first run's format."""
    starts, cursor = [], 0
    for atom in atoms:
        starts.append(cursor)
        cursor += len(_atom_text(atom))
    lengths = [len(_atom_text(a)) for a in atoms]
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        placed = False
        for atom, start, length in zip(atoms, starts, lengths):
            lo, hi = max(edit.start, start), min(edit.end, start + length)
            if lo >= hi or atom.tag not in _EDITABLE:
                continue
            current = atom.text or ""
            atom.text = current[:lo - start] + ("" if placed else edit.replacement) + current[hi - start:]
            atom.set(qn("xml:space"), "preserve")
            placed = True


def _strip(root, part) -> None:
    for tag in _REMOVED_TAGS:
        for node in list(root.iter(tag)):
            node.getparent().remove(node)
    for tag in _UNWRAPPED_TAGS:
        for node in list(root.iter(tag)):
            parent, index = node.getparent(), node.getparent().index(node)
            for offset, child in enumerate(list(node)):
                parent.insert(index + offset, child)
            parent.remove(node)
    for link in root.iter(qn("w:hyperlink")):
        rid = link.attrib.pop(qn("r:id"), None)
        if rid and rid in part.rels and part.rels[rid].is_external:
            part.rels.pop(rid)
    for doc_pr in root.iter(qn("wp:docPr")):
        doc_pr.attrib.pop("descr", None)
        doc_pr.attrib.pop("title", None)


def _drop_rels(rels) -> None:
    for rid in [rid for rid, rel in rels.items() if rel.reltype.rsplit("/", 1)[-1] in _DROPPED_REL_SUFFIXES]:
        rels.pop(rid)


class DocxDocument:
    """Why: DOCX redaction must keep formatting while guaranteeing no PII survives in
    metadata, comments, revision history or link targets.
    What: sanitizes on load (accepts tracked changes, drops comments/metadata parts), exposes
    paragraph/field-code segments from body, tables, text boxes, headers, footers and notes,
    and renders in-place run edits. render() mutates the document and is single-use.
    Test: build a DOCX with author + a split-run name, render a redaction, re-open and assert
    the name and author are gone while the surrounding text and bold formatting remain.
    """

    format = DocumentFormat.DOCX
    SANITIZED = DOCX_SANITIZED
    pages = None

    def __init__(self, payload: bytes, max_bytes: int) -> None:
        _check_zip(payload, max_bytes)
        try:
            self._doc = Document(io.BytesIO(payload))
        except Exception as exc:
            raise DocumentError(422, "INVALID_DOCUMENT", "The DOCX file could not be read.") from exc
        self.warnings: list[str] = []
        self._roots: list[tuple[object, object]] = []  # (part, xml root)
        main = self._doc.part
        parts = [main] + [rel.target_part for rel in main.rels.values()
                          if not rel.is_external and rel.reltype in _CONTENT_RELS]
        for part in parts:
            root = part.element if isinstance(part, XmlPart) else parse_xml(part.blob)
            _strip(root, part)
            self._roots.append((part, root))
            if any(rel.reltype in (RT.IMAGE, RT.OLE_OBJECT, RT.PACKAGE) for rel in part.rels.values()):
                self.warnings.append("embedded_images_or_objects_not_inspected")
        self._sanitize_package(main)
        self._units = [unit for _, root in self._roots for unit in _units(root)]
        self.segments = ["".join(_atom_text(a) for a in unit) for unit in self._units]
        self.warnings = sorted(set(self.warnings))

    def _sanitize_package(self, main) -> None:
        _drop_rels(main.rels)
        _drop_rels(main.package.rels)
        props = self._doc.core_properties
        for name in _CORE_TEXT_PROPS:
            setattr(props, name, "")
        props.revision = 1
        settings = main.rels.part_with_reltype(RT.SETTINGS) if any(
            rel.reltype == RT.SETTINGS for rel in main.rels.values()) else None
        if settings is not None:
            _strip(settings.element, settings)
            for rid in [rid for rid, rel in settings.rels.items() if rel.is_external]:
                settings.rels.pop(rid)

    def page_of(self, segment: int) -> int | None:
        return None

    def render(self, edits: list[SegmentEdit]) -> bytes:
        grouped: dict[int, list[SegmentEdit]] = defaultdict(list)
        for edit in edits:
            grouped[edit.segment].append(edit)
        for segment, unit_edits in grouped.items():
            _apply(self._units[segment], unit_edits)
        for part, root in self._roots:
            if not isinstance(part, XmlPart):
                part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        out = io.BytesIO()
        self._doc.save(out)
        return out.getvalue()
