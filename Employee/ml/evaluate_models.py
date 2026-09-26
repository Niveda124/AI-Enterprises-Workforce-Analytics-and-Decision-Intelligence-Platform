from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
)


def evaluate_classifier(model, X_test, y_test, labels_order=None):
    """
    Never evaluates on training rows — caller must pass a held-out X_test/y_test.
    Returns a plain-dict report, all values computed from y_test vs predictions.
    """
    y_pred = model.predict(X_test)
    cm = confusion_matrix(y_test, y_pred, labels=labels_order)
    return {
        'accuracy': round(accuracy_score(y_test, y_pred), 3),
        'precision': round(precision_score(y_test, y_pred, average='weighted', zero_division=0), 3),
        'recall': round(recall_score(y_test, y_pred, average='weighted', zero_division=0), 3),
        'f1_score': round(f1_score(y_test, y_pred, average='weighted', zero_division=0), 3),
        'confusion_matrix': cm.tolist(),
        'confusion_matrix_labels': list(labels_order) if labels_order is not None else sorted(set(y_test)),
        'test_samples': len(y_test),
    }


def evaluate_cross_val(cv_results, best_index):
    """Summarizes a fitted GridSearchCV/RandomizedSearchCV object's CV results
    for the selected best_index — real numbers from sklearn's own scoring."""
    return {
        'cv_mean_f1': round(float(cv_results['mean_test_score'][best_index]), 3),
        'cv_std_f1': round(float(cv_results['std_test_score'][best_index]), 3),
        'cv_folds': int(sum(1 for k in cv_results if k.startswith('split') and k.endswith('_test_score'))),
    }


from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def evaluate_regressor(model, X_test, y_test):
    """Never evaluates on training rows. Uses MAE/RMSE/R² — never accuracy, per academic requirement."""
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    return {
        'mae': round(float(mean_absolute_error(y_test, y_pred)), 3),
        'rmse': round(float(mse ** 0.5), 3),
        'r2_score': round(float(r2_score(y_test, y_pred)), 3),
        'test_samples': len(y_test),
    }
