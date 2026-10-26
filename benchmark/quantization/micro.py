"""Per-layer micro benchmark of one detector variant (one process per variant).

Why: pick which quantized variants are worth a full eval, on prod hardware (AVX2, no VNNI).
What: loads one variant, times detect() on a fixed text (warm), prints load s, RSS MB,
s/call, entity count and the entity signature (written to /out/<variant>.json).
Test: variant pf-int8w (current prod graph) must reproduce prod's PF entity count on /tmp/perf-6k.txt.
"""
import json, os, sys, time
sys.path.insert(0, "/app")
THREADS = int(os.environ.get("Q_THREADS", "2"))
PF_REV = "7ffa9a043d54d1be65afb281eddf0ffbe629385b"
AI_MODEL, AI_REV = "Isotonic/distilbert_finetuned_ai4privacy_v2", "11795a7549030bb5a21832b09e712b19d39045a7"
DERIVED = "/derived"


def rss():
    for line in open("/proc/self/status"):
        if line.startswith("VmRSS"):
            return int(line.split()[1]) // 1024


def pf_session(graph, acc_level=None):
    import onnxruntime as ort
    from huggingface_hub import snapshot_download
    from tokenizers import Tokenizer
    from app.detection.layers.privacy_filter_layer import PrivacyFilterDetector, _materialize_onnx_files
    if graph == "quantized":
        d = f"/root/.cache/huggingface/hub/models--openai--privacy-filter/snapshots/{PF_REV}"
        path = os.path.join(d, ".materialized-onnx", "model_quantized.onnx")
    else:  # q4 / fp32 from throwaway cache, copied next to their external data
        import glob, shutil
        d = f"/q4hf/models--openai--privacy-filter/snapshots/{PF_REV}"
        name = "model.onnx" if graph == "fp32" else f"model_{graph}.onnx"
        path = os.path.join(DERIVED, f"pf-{graph}", name)
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            for f in sorted(glob.glob(os.path.join(d, "onnx", name + "*")), reverse=True):
                shutil.copyfile(f, os.path.join(os.path.dirname(path), os.path.basename(f)))
    if acc_level is not None:
        import onnx
        out = os.path.join(DERIVED, f"pf-{graph}-acc{acc_level}", os.path.basename(path))
        if not os.path.exists(out):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            m = onnx.load(path, load_external_data=False)
            for n in m.graph.node:
                if n.op_type == "MatMulNBits":
                    for a in list(n.attribute):
                        if a.name == "accuracy_level":
                            n.attribute.remove(a)
                    n.attribute.append(onnx.helper.make_attribute("accuracy_level", acc_level))
            onnx.save(m, out)
            src_data = path + "_data"
            try:
                os.link(src_data, out + "_data")
            except OSError:
                import shutil; shutil.copyfile(src_data, out + "_data")
        path = out
    so = ort.SessionOptions(); so.intra_op_num_threads = THREADS
    PrivacyFilterDetector._session = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])
    PrivacyFilterDetector._tokenizer = Tokenizer.from_file(os.path.join(d, "tokenizer.json"))
    return PrivacyFilterDetector()


class OrtTokenClassifier:
    """Stands in for the torch model inside the HF pipeline: same config, logits from ORT."""
    def __init__(self, session, config):
        self.session, self.config = session, config
        self.names = {i.name for i in session.get_inputs()}

    def __call__(self, **inputs):
        import torch
        feed = {k: v.numpy() for k, v in inputs.items() if k in self.names}
        return {"logits": torch.from_numpy(self.session.run(None, feed)[0])}


def ai_detector(backend):
    import torch
    from app.detection.layers.ai4privacy_layer import Ai4PrivacyDetector
    Ai4PrivacyDetector.preload(AI_MODEL, AI_REV)
    pipe = Ai4PrivacyDetector._pipeline
    if backend == "torch-int8":
        pipe.model = torch.ao.quantization.quantize_dynamic(pipe.model, {torch.nn.Linear}, dtype=torch.qint8)
    elif backend.startswith("onnx"):
        import onnxruntime as ort
        fp32 = os.path.join(DERIVED, "ai4privacy", "model.onnx")
        if not os.path.exists(fp32):
            os.makedirs(os.path.dirname(fp32), exist_ok=True)
            ids = pipe.tokenizer("Mario Rossi abita a Roma", return_tensors="pt")
            torch.onnx.export(pipe.model, (ids["input_ids"], ids["attention_mask"]), fp32, dynamo=False,
                              input_names=["input_ids", "attention_mask"], output_names=["logits"], opset_version=17,
                              dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}, "logits": {0: "b", 1: "s"}})
        path = fp32
        if backend == "onnx-opt":
            from onnxruntime.transformers.optimizer import optimize_model
            path = os.path.join(DERIVED, "ai4privacy", "model_opt.onnx")
            if not os.path.exists(path):
                optimize_model(fp32, model_type="bert", num_heads=12, hidden_size=768, opt_level=1).save_model_to_file(path)
        elif backend != "onnx":
            from onnxruntime.quantization import quantize_dynamic, QuantType
            kind = backend.split("-", 1)[1]  # int8 | int8rr | uint8 | int8pc
            path = os.path.join(DERIVED, "ai4privacy", f"model_{kind}.onnx")
            if not os.path.exists(path):
                quantize_dynamic(fp32, path, weight_type=QuantType.QUInt8 if kind == "uint8" else QuantType.QInt8,
                                 per_channel=kind == "int8pc", reduce_range=kind == "int8rr")
        so = ort.SessionOptions(); so.intra_op_num_threads = THREADS
        pipe.model = OrtTokenClassifier(ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"]), pipe.model.config)
    return Ai4PrivacyDetector()


def main(variant, text_path):
    import torch
    torch.set_num_threads(THREADS)
    text = open(text_path).read()
    r0, t0 = rss(), time.perf_counter()
    if variant.startswith("pf-"):
        graph, _, acc = variant[3:].partition("-acc")
        det = pf_session(graph, int(acc) if acc else None)
    else:
        det = ai_detector(variant[3:])
    load = time.perf_counter() - t0
    det.detect(text)  # warm
    times = []
    for _ in range(int(os.environ.get("Q_REPS", "3"))):
        t = time.perf_counter(); ents = det.detect(text); times.append(time.perf_counter() - t)
    sig = sorted((e.start, e.end, e.pii_type) for e in ents)
    json.dump(sig, open(f"/out/{variant}.json", "w"))
    print(json.dumps({"variant": variant, "threads": THREADS, "load_s": round(load, 1), "rss_mb": rss() - r0,
                      "s_per_call": round(min(times), 3), "s_all": [round(x, 2) for x in times], "entities": len(ents)}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
