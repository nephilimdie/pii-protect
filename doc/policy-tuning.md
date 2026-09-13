# Policy tuning

Domain policies support two optional JSON objects:

```json
{
  "confidence_thresholds": {"PERSON": 0.8, "EMAIL": 0.95},
  "allowlist": {"ORGANIZATION": ["Pseudora", "ACME S.p.A."]}
}
```

`confidence_thresholds` is applied after detection and reclassification. An
entity is included only when its score is at least the configured threshold
for its final PII type. Types without a threshold preserve the existing
behaviour.

`allowlist` is matched case-insensitively after trimming whitespace and is
scoped by the final PII type. In Pseudora Cloud these fields are saved as
tenant-scoped overrides, so another tenant keeps its own effective policy.
Both values are included in the policy hash for auditability.

Keep allow-lists short and limited to stable public values. A lower threshold
usually improves recall but can increase false positives; validate changes
against the benchmark before enabling them for production traffic.
