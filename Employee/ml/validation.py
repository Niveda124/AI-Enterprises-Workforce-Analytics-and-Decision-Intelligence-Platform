import pandas as pd


def validate_dataset(df, labels, min_samples_per_class=5, min_classes=2):
    """
    Returns (is_valid: bool, report: dict).
    Checks: missing values, duplicate rows, class distribution, minimum
    samples per class. Never fabricates data — only reports.
    """
    report = {}

    report['total_rows'] = len(df)
    report['missing_values'] = int(df.isnull().sum().sum())
    report['duplicate_rows'] = int(df.duplicated().sum())

    class_counts = pd.Series(labels).value_counts().to_dict()
    report['class_distribution'] = class_counts
    report['num_classes'] = len(class_counts)

    issues = []
    if report['missing_values'] > 0:
        issues.append(f"{report['missing_values']} missing value(s) found in feature matrix.")
    if report['num_classes'] < min_classes:
        issues.append(f"Only {report['num_classes']} class(es) present; need at least {min_classes}.")
    for cls, count in class_counts.items():
        if count < min_samples_per_class:
            issues.append(f"Class '{cls}' has only {count} sample(s); need at least {min_samples_per_class}.")

    report['issues'] = issues
    report['is_valid'] = len(issues) == 0
    return report['is_valid'], report


def can_cross_validate(labels, n_splits=3):
    """StratifiedKFold requires every class to have >= n_splits members."""
    counts = pd.Series(labels).value_counts()
    return (counts >= n_splits).all() and len(counts) >= 2


def can_hold_out_test(labels, test_size=0.25, min_per_class_after_split=1):
    counts = pd.Series(labels).value_counts()
    min_count = counts.min()
    test_count = max(1, int(min_count * test_size))
    return (min_count - test_count) >= min_per_class_after_split

def validate_regression_dataset(df, min_rows=10):
    """Regression has no class distribution to check — only row count and missing values."""
    report = {'total_rows': len(df) if df is not None else 0}
    if df is None or len(df) == 0:
        report['issues'] = ['No records found.']
        report['is_valid'] = False
        return False, report

    report['missing_values'] = int(df.isnull().sum().sum())
    issues = []
    if report['missing_values'] > 0:
        issues.append(f"{report['missing_values']} missing value(s) found.")
    if report['total_rows'] < min_rows:
        issues.append(f"Only {report['total_rows']} row(s); need at least {min_rows}.")
    report['issues'] = issues
    report['is_valid'] = len(issues) == 0
    return report['is_valid'], report     