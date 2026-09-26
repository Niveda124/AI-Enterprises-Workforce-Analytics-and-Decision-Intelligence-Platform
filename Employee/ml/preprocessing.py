from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler


def build_preprocessing_pipeline():
    """
    Kept minimal and honest: our features are already numeric
    (counts, rates, encoded priority). Imputation guards against any
    missing value; scaling helps distance/gradient-based candidates
    (HistGradientBoosting is scale-invariant but this keeps the pipeline
    reusable across candidate algorithms without special-casing).
    """
    return Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler()),
    ])