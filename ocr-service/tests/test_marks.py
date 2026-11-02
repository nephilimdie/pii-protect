"""SIGNATURE / STAMP marks on /v1/ocr and face recall passes (procedural, licence-clean fixtures)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.errors import OcrError
from app.pipeline import parse_marks
from conftest import png, post
from synth import make_page
from synth_marks import make_form, scan
from test_visual import mona, real_detectors, real_vclient  # noqa: F401 (fixtures)


def covered(truth: tuple[int, int, int, int], box: list[int]) -> float:
    w = max(0, min(truth[2], box[2]) - max(truth[0], box[0]))
    h = max(0, min(truth[3], box[3]) - max(truth[1], box[1]))
    return w * h / ((truth[2] - truth[0]) * (truth[3] - truth[1]))


def marks_of(client: TestClient, image: Image.Image, marks: str = "signature,stamp") -> list[dict]:
    response = post(client, png(image), dpi="200", marks=marks)
    assert response.status_code == 200, response.text
    return response.json()["pages"][0]["marks"]


def test_parse_marks_validates() -> None:
    assert parse_marks(None) == () and parse_marks("") == ()
    assert parse_marks("stamp, signature") == ("signature", "stamp")
    with pytest.raises(OcrError):
        parse_marks("logo")


def test_marks_are_opt_in(client: TestClient) -> None:
    response = post(client, png(Image.new("L", (400, 300), 255)))
    assert response.json()["pages"][0]["marks"] == []
    assert post(client, png(Image.new("L", (400, 300), 255)), marks="logo").status_code == 422


@pytest.mark.parametrize(("stamp", "ink", "gray"), [("round", "red", False), ("oval", "violet", False),
                                                     ("rect", "blue", False), ("round", "black", True)])
def test_signature_and_stamp_found(real_client: TestClient, stamp: str, ink: str, gray: bool) -> None:
    form = make_form(seed=11, stamp=stamp, stamp_ink=ink, sig_ink="black" if gray else "blue")
    marks = marks_of(real_client, scan(form.image, 11, gray=gray))
    for kind, truth in form.truth:
        assert any(m["type"] == kind and covered(truth, m["bbox"]) >= 0.95 for m in marks), (kind, truth, marks)
    signature = next(m for m in marks if m["type"] == "SIGNATURE")
    assert not signature["needs_review"]  # next to "Firma del dichiarante"
    truth = dict(form.truth)["SIGNATURE"]
    assert signature["bbox"][2] - signature["bbox"][0] > 1.2 * (truth[2] - truth[0])  # padded generously


def test_unlabelled_signature_is_reviewed(real_client: TestClient) -> None:
    form = make_form(seed=12, stamp=None, label=False)
    (mark,) = marks_of(real_client, scan(form.image, 12))
    assert mark["type"] == "SIGNATURE" and mark["needs_review"]


@pytest.mark.parametrize("seed", [21, 22, 23])
def test_no_marks_on_text_tables_and_logos(real_client: TestClient, seed: int) -> None:
    assert marks_of(real_client, scan(make_form(seed=seed, stamp=None, signature=False).image, seed)) == []
    assert marks_of(real_client, make_page(dpi=200).image) == []


def test_marks_subset(real_client: TestClient) -> None:
    form = make_form(seed=13)
    assert {m["type"] for m in marks_of(real_client, scan(form.image, 13), "stamp")} == {"STAMP"}


@pytest.mark.parametrize("angle", [60, -50, 75])
def test_steeply_tilted_face_found(real_vclient: TestClient, angle: int) -> None:
    from test_visual import visual

    turned = mona().rotate(angle, expand=True, fillcolor=(200, 200, 195))
    boxes = json.loads(visual(real_vclient, png(turned), detectors="face").text)["boxes"]
    assert [b["type"] for b in boxes] == ["FACE"], boxes


def test_small_face_in_mid_size_image_found(real_vclient: TestClient) -> None:
    from test_visual import visual

    scene = Image.new("RGB", (900, 600), (225, 228, 230))
    scene.paste(mona().resize((40, 60)), (540, 270))  # face ~16 px wide
    boxes = json.loads(visual(real_vclient, png(scene), detectors="face").text)["boxes"]
    assert len(boxes) == 1 and boxes[0]["bbox"][0] <= 552 and boxes[0]["bbox"][2] >= 563, boxes


def test_face_duplicates_merge_into_their_union() -> None:
    from app.detectors import Hit
    from app.detectors.faces import _merge

    (hit,) = _merge([Hit("FACE", (0, 0, 10, 10), 0.9, False), Hit("FACE", (2, 2, 20, 20), 0.6, True)])
    assert hit.bbox == (0, 0, 20, 20) and hit.score == 0.9 and not hit.needs_review
    assert len(_merge([Hit("FACE", (0, 0, 10, 10), 0.9, False), Hit("FACE", (30, 30, 40, 40), 0.6, True)])) == 2


@pytest.mark.parametrize("angle", [0, 50])
def test_no_marks_on_a_picture_in_a_photo(real_client: TestClient, angle: int) -> None:
    scene = Image.new("RGB", (1400, 900), (238, 236, 230))
    scene.paste(mona().resize((260, 388)).rotate(angle, expand=True, fillcolor=(238, 236, 230)), (900, 300))
    assert marks_of(real_client, scene) == []
