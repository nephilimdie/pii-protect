"""Span-level evaluation of actual /v1/detect responses, without demo detectors."""

from collections import Counter
from math import ceil
from time import perf_counter


def _spans(entities, text):
    spans = []
    for entity in entities:
        kind, start, end = entity['type'], entity['start'], entity['end']
        if (not isinstance(kind, str) or not kind
                or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(text)):
            raise ValueError('Invalid annotated or returned entity span')
        spans.append((kind, start, end))
    return Counter(spans)


def _metrics(tp, fp, fn):
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return dict(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=f1)


def evaluate(rows, request):
    """request(path, payload) returns (HTTP status, parsed JSON).

    Exact type+offset matching counts every occurrence. Missing entities and
    duplicate predictions cannot inflate recall. Reports never contain text.
    """
    if not rows:
        raise ValueError('Dataset must not be empty')
    counts = Counter()
    per_type = {}
    samples = []
    latencies = []
    ids = set()
    for row in rows:
        if row['id'] in ids:
            raise ValueError('Duplicate sample ID')
        ids.add(row['id'])
        text = row['text']
        expected = _spans(row['entities'], text)
        if any(count > 1 for count in expected.values()):
            raise ValueError('Duplicate annotation')
        started = perf_counter()
        status, response = request('/v1/detect', {
            'text': text, 'language': row['language'],
        })
        elapsed = (perf_counter() - started) * 1000
        if status != 200 or not isinstance(response.get('entities'), list):
            raise RuntimeError(f'Detection failed for sample {row["id"]}: HTTP {status}')
        predicted = _spans(response['entities'], text)
        correct = predicted & expected
        extra, missing = predicted - expected, expected - predicted
        tp, fp, fn = sum(correct.values()), sum(extra.values()), sum(missing.values())
        counts.update(tp=tp, fp=fp, fn=fn)
        for name, counter in [('tp', correct), ('fp', extra), ('fn', missing)]:
            for (kind, _, _), count in counter.items():
                per_type.setdefault(kind, Counter())[name] += count
        samples.append({'id': row['id'], **_metrics(tp, fp, fn),
                        'missing': list(missing.elements()), 'unexpected': list(extra.elements())})
        latencies.append(elapsed)
    latencies.sort()
    return {
        'measurement': 'real-engine-http-exact-spans',
        'dataset_size': len(rows),
        **_metrics(counts['tp'], counts['fp'], counts['fn']),
        'per_type': {kind: _metrics(c['tp'], c['fp'], c['fn']) for kind, c in sorted(per_type.items())},
        'latency_ms': {f'p{p}': latencies[ceil(len(latencies) * p / 100) - 1] for p in (50, 95, 99)},
        'samples': samples,
        'limitations': 'Synthetic regression corpus; not a representative accuracy certification.',
    }
