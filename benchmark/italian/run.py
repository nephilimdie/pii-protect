"""One-command runner for the Italian PII benchmark: engine in Docker + baselines + scoring.

Why: results must be reproducible by anyone with Docker and the pinned model caches.
What: starts an ephemeral PostgreSQL + the engine (current api/ source mounted read-only,
offline models), registers ablation context types (same generic_professional policy,
restricted detection layers), runs every system on the dataset via /v1/anonymize dry_run,
runs vanilla Presidio and Rizzo-PII in throwaway containers, then calls score.py and report.py.
Test: `python3 run.py --subset 2 --systems pseudora_generic,ablation_regex` finishes in ~1 min
and writes results-subset/; the scorer itself is unit-tested without Docker.

Usage:
  python3 benchmark/italian/run.py --image ENGINE_IMAGE --cache-volume HF_CACHE_VOLUME \
      [--rizzo-src PATH --rizzo-model-volume VOL] [--subset N] [--systems a,b,...]
"""
from __future__ import annotations

import argparse
import base64
import json
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "systems"))
from common import load_docs, run_system  # noqa: E402

RIZZO_COMMIT = "9057eeff88bdf0444e5d3361cf0766b60c5b8a95"
RIZZO_REV = "a1c3c83827eca22e9675e30c1111c4641caf5901"  # HF branch v1.5.0, pinned by the app
RIZZO_DEPS = "flask==3.1.1 pymupdf==1.26.3"
GENERIC = "generic_professional"
DOMAINS = ["generic_professional", "default", "hr_payroll", "tax_accounting", "real_estate_insurance",
           "contract_analysis", "fine_appeal", "condominio", "medical"]
# Preset a user would pick for each sub-genre ("matched"); no litigation preset exists, so
# citazioni/sentenze/procure use the generic professional preset.
MATCHED = {"genre": {"hr": "hr_payroll", "tax": "tax_accounting", "real_estate_insurance": "real_estate_insurance"},
           "subgenre": {"ricorso": "fine_appeal", "contratto_locazione": "contract_analysis"}}
ABLATIONS = {"regex": ["regex"], "presidio": ["presidio"], "privacy_filter": ["privacy_filter"],
             "ai4privacy": ["ai4privacy"], "regex_presidio": ["regex", "presidio"],
             "no_regex": ["presidio", "privacy_filter", "ai4privacy"]}
SYSTEMS = (["pseudora_matched"] + [f"pseudora_{d}" for d in DOMAINS] + [f"ablation_{a}" for a in ABLATIONS]
           + [f"pseudora_{GENERIC}_maximum", "pseudora_matched_maximum"]
           + ["presidio_vanilla_it", "rizzo_default", "rizzo_pii_only"])
MAXIMUM = "_maximum"  # system-name suffix: same preset at protection_level=maximum


def sh(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


class Engine:
    """Why: the benchmark must hit the real engine HTTP path (policy, merger, denylist, snapping).
    What: context manager starting PG + API on localhost with random credentials; removed on exit.
    Test: `with Engine(img, vol, 15691) as e: e.post('/v1/anonymize', {...})` returns 200.
    """

    def __init__(self, image: str, cache_volume: str, port: int) -> None:
        self.image, self.volume, self.port = image, cache_volume, port
        self.prefix = "bench-it-" + secrets.token_hex(3)
        self.key, self.internal = secrets.token_hex(24), secrets.token_hex(24)

    def __enter__(self) -> "Engine":
        pw, pg, api = secrets.token_hex(16), self.prefix + "-db", self.prefix + "-api"
        sh("docker", "network", "create", self.prefix)
        sh("docker", "run", "-d", "--name", pg, "--network", self.prefix, "--tmpfs", "/var/lib/postgresql/data",
           "-e", f"POSTGRES_PASSWORD={pw}", "-e", "POSTGRES_USER=bench", "-e", "POSTGRES_DB=bench", "pgvector/pgvector:pg17")
        for _ in range(60):
            if sh("docker", "exec", pg, "pg_isready", "-U", "bench", check=False).returncode == 0:
                break
            time.sleep(1)
        time.sleep(2)
        sh("docker", "run", "-d", "--name", api, "--network", self.prefix, "-p", f"127.0.0.1:{self.port}:8000",
           "-v", f"{ROOT / 'api'}:/app:ro", "-v", f"{self.volume}:/root/.cache/huggingface",
           "-e", f"DATABASE_URL=postgresql+asyncpg://bench:{pw}@{pg}:5432/bench",
           "-e", "ENCRYPTION_KEY=" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
           "-e", f"ADMIN_INITIAL_KEY={self.key}", "-e", f"PII_INTERNAL_API_KEY={self.internal}",
           "-e", "HF_HUB_OFFLINE=1", "-e", "TRANSFORMERS_OFFLINE=1", "--entrypoint", "sh", self.image, "/app/entrypoint.sh")
        for _ in range(120):
            try:
                status, body = self.call("GET", "/readiness")
                if status == 200 and all(body["checks"]["detector_layers"].values()):
                    self.readiness = body
                    return self
            except (urllib.error.URLError, ConnectionError, KeyError, json.JSONDecodeError):
                pass
            if sh("docker", "inspect", "-f", "{{.State.Running}}", api, check=False).stdout.strip() != "true":
                break
            time.sleep(2)
        logs = sh("docker", "logs", "--tail", "40", api, check=False)
        self.__exit__()
        raise RuntimeError("engine not ready (all detector layers required):\n" + logs.stdout + logs.stderr)

    def __exit__(self, *_: object) -> None:
        sh("docker", "rm", "-f", self.prefix + "-api", self.prefix + "-db", check=False)
        sh("docker", "network", "rm", self.prefix, check=False)

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "X-Api-Key": self.key,
                                              "X-Internal-Api-Key": self.internal})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as err:
            return err.code, json.load(err)

    def anonymize(self, text: str, target: dict) -> list[tuple[str, int, int]]:
        status, res = self.call("POST", "/v1/anonymize", {"text": text, "context_id": "bench-" + secrets.token_hex(4),
                                                          "language": "it", "dry_run": True, **target})
        if status != 200 or not res.get("safe"):
            raise RuntimeError(f"anonymize failed: HTTP {status} {str(res)[:200]}")
        return [(e["type"], e["start"], e["end"]) for e in res["entities"]]


def engine_meta(engine: Engine, label: str, target: dict | str) -> dict:
    return {"label": label, "target": target, "readiness": engine.readiness["checks"]["detector_layers"],
            "engine_commit": sh("git", "-C", str(ROOT), "rev-parse", "HEAD").stdout.strip(),
            "engine_image": engine.image, "transport": "HTTP /v1/anonymize dry_run (masked spans only)"}


def run_engine(args: argparse.Namespace, docs: list[dict], todo: list[str], out: Path) -> None:
    with Engine(args.image, args.cache_volume, args.port) as eng:
        # an unknown domain silently resolves to "no protect/keep filter": refuse to benchmark that
        _, policies = eng.call("GET", "/v1/admin/domain-policies")
        missing = set(DOMAINS) - {"default"} - {p["domain"] for p in policies}
        assert not missing, f"domain presets missing in engine: {missing}"
        for name, layers in ABLATIONS.items():
            status, res = eng.call("POST", "/v1/admin/context-types", {
                "code": f"bench_{name}", "display_name": f"bench {name}", "domain": GENERIC,
                "default_mode": "tag", "detection_layers": layers})
            assert status in (200, 201), (status, res)
        for system in todo:
            level = {"protection_level": "maximum"} if system.endswith(MAXIMUM) else {}
            note = ", protection_level maximum" if level else ""
            if system.removesuffix(MAXIMUM) == "pseudora_matched":
                pick = lambda t: {"domain": MATCHED["subgenre"].get(t["subgenre"]) or MATCHED["genre"].get(t["genre"], GENERIC), **level}  # noqa: E731
                by_text = {d["text"]: pick(d) for d in docs}
                run_system(docs, lambda text: eng.anonymize(text, by_text[text]), out / f"{system}.json", system,
                           "pseudora", engine_meta(eng, f"Pseudora full pipeline, preset matched to genre{note}", {"matched": MATCHED, **level}))
            elif system.startswith("pseudora_"):
                dom = system.removeprefix("pseudora_").removesuffix(MAXIMUM)
                target = {**({"context_type": "default"} if dom == "default" else {"domain": dom}), **level}
                run_system(docs, lambda text: eng.anonymize(text, target), out / f"{system}.json", system, "pseudora",
                           engine_meta(eng, f"Pseudora full pipeline, preset {dom}{note}", target))
            else:
                name = system.removeprefix("ablation_")
                target = {"context_type": f"bench_{name}"}
                run_system(docs, lambda text: eng.anonymize(text, target), out / f"{system}.json", system, "pseudora",
                           engine_meta(eng, f"Ablation: layers {'+'.join(ABLATIONS[name])} only ({GENERIC} policy)",
                                       {**target, "layers": ABLATIONS[name]}))


def container(args: argparse.Namespace, out: Path, mounts: list[str], script: str) -> None:
    cmd = ["docker", "run", "--rm", "-v", f"{HERE}:/bench:ro", "-v", f"{args.dataset.resolve().parent}:/data:ro", "-v", f"{out}:/out", *mounts,
           "-e", "PYTHONPATH=/tmp/deps:/bench/systems", "-e", f"RIZZO_COMMIT={RIZZO_COMMIT}", "-e", f"RIZZO_REV={RIZZO_REV}",
           "--entrypoint", "sh", args.image, "-c", script]
    proc = subprocess.run(cmd, text=True)
    if proc.returncode:
        raise RuntimeError(f"container run failed: {script[:120]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--image", required=True, help="engine image built from api/Dockerfile")
    ap.add_argument("--cache-volume", required=True, help="HF cache volume with the pinned engine models")
    ap.add_argument("--rizzo-src", type=Path, help=f"checkout of Rizzo-AI-Academy/rizzo-pii at {RIZZO_COMMIT[:10]}")
    ap.add_argument("--rizzo-model-volume", help=f"volume with rizzoaiacademy/rizzo-pii-0.3B@{RIZZO_REV[:10]} in /rizzo-pii-0.3B-v1.5.0")
    ap.add_argument("--dataset", type=Path, default=HERE / "dataset" / "it_pii_v1.jsonl", help="gold JSONL (e.g. the held-out corpus)")
    ap.add_argument("--systems", default="all")
    ap.add_argument("--subset", type=int, default=0, help="first N docs per sub-genre (0 = full dataset)")
    ap.add_argument("--port", type=int, default=15691)
    ap.add_argument("--skip-run", action="store_true", help="only re-score existing predictions")
    ap.add_argument("--out", type=Path, help="results directory (default results/ or results-subset/)")
    args = ap.parse_args()
    results = (args.out or HERE / ("results" if not args.subset else "results-subset")).resolve()
    out = results / "predictions"
    out.mkdir(parents=True, exist_ok=True)
    dataset = args.dataset
    data = f"/data/{dataset.name}"
    docs = load_docs(dataset, args.subset)
    todo = SYSTEMS if args.systems == "all" else args.systems.split(",")
    unknown = sorted(set(todo) - set(SYSTEMS))
    if unknown:
        raise SystemExit(f"unknown systems {unknown}; choose from {SYSTEMS}")
    if not args.skip_run:
        engine_systems = [s for s in todo if s.startswith(("pseudora_", "ablation_"))]
        if engine_systems:
            run_engine(args, docs, engine_systems, out)
        sub = f" {args.subset}" if args.subset else ""
        if "presidio_vanilla_it" in todo:
            container(args, out, [], f"python /bench/systems/presidio_vanilla.py {data} /out/presidio_vanilla_it.json{sub}")
        rizzo = [s.removeprefix("rizzo_") for s in todo if s.startswith("rizzo_")]
        if rizzo:
            if not (args.rizzo_src and args.rizzo_model_volume):
                raise SystemExit("rizzo systems need --rizzo-src and --rizzo-model-volume (see README)")
            container(args, out, ["-v", f"{args.rizzo_src.resolve()}:/rizzo:ro", "-v", f"{args.rizzo_model_volume}:/models:ro",
                                  "-e", "PII_MODEL_DIR=/models/rizzo-pii-0.3B-v1.5.0", "-e", "HF_HUB_OFFLINE=1"],
                      f"pip install -q --no-deps --target /tmp/deps {RIZZO_DEPS} blinker itsdangerous werkzeug jinja2 markupsafe click >/dev/null"
                      f" && cd /tmp && python /bench/systems/rizzo_pii.py {data} /out {','.join(rizzo)}{sub}")
    subprocess.run([sys.executable, str(HERE / "score.py"), "--dataset", str(dataset), "--predictions", str(out),
                    "--out", str(results / "summary.json")] + (["--subset", str(args.subset)] if args.subset else []), check=True)
    subprocess.run([sys.executable, str(HERE / "report.py"), "--results", str(results)], check=True)


if __name__ == "__main__":
    main()
