# Data Residency Controls

The engine exposes explicit deployment controls for model-cache placement and
residency declarations. They do not move a database or prove a provider's
physical region; the database and backup locations must be selected and
verified in the infrastructure layer.

## Configuration

```dotenv
PII_MODEL_CACHE_DIR=/root/.cache/huggingface
PII_DATA_RESIDENCY_REGION=eu-central
PII_REQUIRE_DATA_RESIDENCY=true
```

`PII_MODEL_CACHE_DIR` is used for Hugging Face and Transformers downloads and
is the target of the Compose cache volume. `PII_DATA_RESIDENCY_REGION` is a
deployment declaration such as `eu-central` or `us-east`. When enforcement is
enabled, the engine refuses to start with the default `unspecified` value.

Before enabling enforcement, record the actual PostgreSQL, backup, log and
metric destinations in the infrastructure release record. A matching label in
the application environment is not evidence that those services are physically
located in the declared region.

Self-hosted installations may leave enforcement disabled and use the default
cache path. Cloud deployments should set the region per environment and keep
the value consistent with the Cloud control plane and provider contracts.
