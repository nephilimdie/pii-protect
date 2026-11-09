"""End-to-end check of all four prod layers with ai4privacy on torch vs ONNX fp32.

Why: a per-layer speedup only matters if it survives the full pipeline under prod threading.
What: 2 intra-op threads (prod PII_INFERENCE_THREADS), per-layer s on /text.txt, single-call
latency, 3-way parallel chars/s, then ai4privacy span diff on /s/evalset.json (torch = reference).
Test: run in the engine image (see micro.py header); torch-vs-torch must report 0 miss / 0 new.
"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/app"); sys.path.insert(0, "/s")
import torch
torch.set_num_threads(2)
from app.detection.layers.presidio_layer import PresidioDetector
from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector
from app.detection.layers.ai4privacy_layer import Ai4PrivacyDetector
from app.detection.layers.regex_layer import ItalianRegexDetector
import onnxruntime as ort
import micro as qm
PresidioDetector.preload([{"lang_code": "it", "model_name": "it_core_news_lg"}])
PrivacyFilterDetector.preload("openai/privacy-filter", qm.PF_REV, 2)
Ai4PrivacyDetector.preload(qm.AI_MODEL, qm.AI_REV)
pipe = Ai4PrivacyDetector._pipeline
torch_model = pipe.model
so = ort.SessionOptions(); so.intra_op_num_threads = 2
onnx_model = qm.OrtTokenClassifier(ort.InferenceSession("/derived/ai4privacy/model.onnx", sess_options=so, providers=["CPUExecutionProvider"]), torch_model.config)
dets = [PresidioDetector(), PrivacyFilterDetector(), Ai4PrivacyDetector(), ItalianRegexDetector([])]
text = open("/text.txt").read()
rows = json.load(open("/s/evalset.json"))
res = {}
for backend, model in [("torch", torch_model), ("onnx", onnx_model)]:
    pipe.model = model
    per = {}
    for d in dets:
        d.detect(text); ts = []
        for _ in range(3):
            t = time.perf_counter(); d.detect(text); ts.append(time.perf_counter() - t)
        per[d.layer_name] = round(min(ts), 3)
    def full(t):
        return [e for d in dets for e in d.detect(t)]
    full(text)
    t = time.perf_counter(); full(text); single = time.perf_counter() - t
    batch = [text] * 9
    t = time.perf_counter()
    with ThreadPoolExecutor(3) as ex: list(ex.map(full, batch))
    thr = len(text) * len(batch) / (time.perf_counter() - t)
    sigs = []
    t = time.perf_counter()
    for r in rows:
        sigs.append(sorted((e.start, e.end, e.pii_type) for e in dets[2].detect(r["text"])))
    eval_s = time.perf_counter() - t
    res[backend] = dict(per_layer_s=per, single_6k_s=round(single, 3), chars_per_s_3par=round(thr), ai_eval_s=round(eval_s, 1))
    json.dump(sigs, open(f"/out/ai-{backend}-eval.json", "w"))
    print(json.dumps({backend: res[backend]}), flush=True)
a = json.load(open("/out/ai-torch-eval.json")); b = json.load(open("/out/ai-onnx-eval.json"))
from collections import Counter
miss, new, tot = Counter(), Counter(), Counter()
for x, y in zip(a, b):
    X, Y = set(map(tuple, x)), set(map(tuple, y))
    for e in X: tot[e[2]] += 1
    for e in X - Y: miss[e[2]] += 1
    for e in Y - X: new[e[2]] += 1
print(json.dumps({"ref_total": dict(tot), "miss": dict(miss), "new": dict(new), "texts": len(a)}))
