# Dataset license

`it_pii_v1.jsonl` and `it_pii_v1.stats.json` are released under the
Creative Commons Attribution 4.0 International license (CC BY 4.0,
https://creativecommons.org/licenses/by/4.0/).
Attribution: "Pseudora Italian PII benchmark it_pii_v1 (nephilimdie/pii-protect)".

Every document is synthetic: produced by `benchmark/italian/generate.py` (Apache-2.0,
like the rest of the repository) from a fixed seed. No real person, file or case was
used. Identifiers are random but checksum-valid, so a generated codice fiscale, IBAN or
card number can coincide with a real one by chance; such a coincidence carries no
information about that person.
