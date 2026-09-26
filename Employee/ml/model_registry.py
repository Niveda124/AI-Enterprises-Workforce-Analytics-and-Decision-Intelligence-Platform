import json
from Employee.models import ModelVersion


def register_model(name, version, algorithm, metrics, file_path, active=True, status="ACTIVE"):
    """
    Deactivates any prior active version of this model, then records the new
    one. Only ever called with metrics actually computed from a real
    train/test or cross-validation run — never invented values.
    """
    ModelVersion.objects.filter(model_name=name, is_active=True).update(is_active=False)
    return ModelVersion.objects.create(
        model_name=name,
        version=version,
        algorithm=algorithm,
        metrics=json.dumps(metrics),
        model_file_path=file_path,
        is_active=active,
    )


def register_insufficient_data(name, reason_metrics):
    """
    Records that training was attempted but skipped for legitimate reasons.
    Does NOT mark any version active — prediction_service must then report
    the model as unavailable rather than silently reusing a stale one.
    """
    ModelVersion.objects.filter(model_name=name, is_active=True).update(is_active=False)
    return ModelVersion.objects.create(
        model_name=name,
        version="INSUFFICIENT_DATA",
        algorithm="N/A",
        metrics=json.dumps(reason_metrics),
        model_file_path=None,
        is_active=False,
    )


def register_not_ready(name, algorithm, metrics, file_path):
    """
    Records that a model WAS trained and evaluated, but its held-out/CV
    performance fell below the documented minimum bar for production use.
    The real metrics are stored for academic transparency (so the training
    attempt is auditable), but is_active=False means prediction_service will
    NOT load or serve predictions from this artifact.
    """
    ModelVersion.objects.filter(model_name=name, is_active=True).update(is_active=False)
    return ModelVersion.objects.create(
        model_name=name,
        version="MODEL_NOT_READY",
        algorithm=algorithm,
        metrics=json.dumps(metrics),
        model_file_path=file_path,
        is_active=False,
    )


def get_active_model_version(name):
    return ModelVersion.objects.filter(model_name=name, is_active=True).first()

def register_regressor_not_ready(name, algorithm, metrics, file_path):
    """Same purpose as register_not_ready but named separately for clarity
    when a regression model (not a classifier) fails its quality bar."""
    ModelVersion.objects.filter(model_name=name, is_active=True).update(is_active=False)
    return ModelVersion.objects.create(
        model_name=name, version="MODEL_NOT_READY", algorithm=algorithm,
        metrics=json.dumps(metrics), model_file_path=file_path, is_active=False,
    )