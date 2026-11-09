# Detector quantization experiment (2026-10-26)

Outcome: **not shipped**. No accuracy-safe variant reaches the >=1.3x end-to-end bar.

Run inside the engine image (`--entrypoint python`, HF cache mounted read-only, offline):

- `gen_evalset.py OUT.json` - 240 synthetic Italian texts (8 presets) with gold spans, seeded.
- `micro.py VARIANT /text.txt` - one layer variant, warm s/call, RSS, span signature to `/out`.
  Variants: `pf-quantized` (prod 8-bit graph), `pf-q4`, `pf-fp32`, `pf-<graph>-acc4`,
  `ai-torch`, `ai-torch-int8`, `ai-onnx`, `ai-onnx-int8|int8rr|uint8|int8pc`.
- `e2e.py` - all four prod layers, ai4privacy torch vs ONNX fp32, plus evalset span diff.

Prod host (12 vCPU AVX2, 2 intra-op threads per call as in prod), 6k-char text:

| Variant | s/call | spans vs fp32 ref | Verdict |
|---|---|---|---|
| privacy_filter 8-bit (current prod) | 4.10 | 3 misses (1 PERSON, 2 ADDRESS) vs fp32 | baseline |
| privacy_filter q4 (repo-shipped) | 3.98 | 12 misses (3 PERSON, 2 ACCOUNT_NUMBER) | rejected |
| ai4privacy torch fp32 (current prod) | 3.17 | 29/29 | baseline |
| ai4privacy ONNX fp32 | 2.35 | identical; 0 miss / 0 new on 240 texts | safe, too small a gain |
| ai4privacy ONNX int8 / uint8 / reduce_range / per-channel | 2.0-2.16 | 16 / 17 / 10 / 0 of 29 | rejected |
| ai4privacy torch dynamic int8 | 2.13 | 11 of 29 | rejected |

End to end (presidio + privacy_filter + ai4privacy + regex): torch 7.36 s single / 1550 chars/s
3-parallel; ai4privacy ONNX fp32 7.10 s (1.04x) / 1521 chars/s (0.98x). privacy_filter is ~61%
of pipeline time and already ships 8-bit, so there is no remaining quantization headroom.
