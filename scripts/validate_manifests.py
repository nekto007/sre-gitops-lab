from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]

def require(document, dotted_path):
    value = document
    for key in dotted_path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"Missing required field: {dotted_path}")
        value = value[key]

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Expected non-empty string: {dotted_path}")
    
    return value


paths = sorted(ROOT.glob("bootstrap/*yaml"))
paths += sorted(ROOT.glob("apps/monitoring/*yaml"))

if not paths:
    raise ValueError("No manifests found")

for path in paths:
    print(f"Checking {path.relative_to(ROOT)}", flush=True)

    for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        if document is None:
            continue
        
        require(document, "apiVersion")
        kind = require(document, "kind")
        name = require(document, "metadata.name")
        require(document, "metadata.namespace")

        if kind == "ConfigMap":
            if not isinstance(document.get("data"), dict):
                raise ValueError("ConfigMap must contain a data mapping")
            continue

        if kind != "Application":
            raise ValueError(f"Unexpected manifest kind: {kind}")

        if document["apiVersion"] != "argoproj.io/v1alpha1":
            raise ValueError("Unexpected Application apiVersion")

        repo = require(document, "spec.source.repoURL")
        revision = require(document, "spec.source.targetRevision")
        require(document, "spec.destination.server")
        namespace = require(document, "spec.destination.namespace")
        source = document["spec"]["source"]

        if "chart" not in source:
            require(document, "spec.source.path")
            print(f"  Git Application validated: {name}", flush=True)
            continue

        chart = require(document, "spec.source.chart")
        values = source.get("helm", {}).get("valuesObject", {})

        result = subprocess.run(
            [
                "helm", "template", name, chart,
                "--repo", repo,
                "--version", revision,
                "--namespace", namespace,
                "--kube-version", "1.37.0",
                "--values", "-",
            ],
            input=yaml.safe_dump(values),
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout)

        resources = [
            item for item in yaml.load_all(result.stdout, Loader=yaml.CSafeLoader)
            if item is not None
        ]
        if not resources:
            raise ValueError(f"Chart produced no resources: {name}")

        print(f"  Helm render passed: {name}, {len(resources)} resources")

print("All manifest checks passed")
