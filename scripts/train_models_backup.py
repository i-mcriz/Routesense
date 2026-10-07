import pandas as pd
import numpy as np
from sklearn.model_selection import GroupShuffleSplit, GroupKFold, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble._forest import RandomForestClassifier, ExtraTreesClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report, confusion_matrix
import joblib
import json
import matplotlib.pyplot as plt
import seaborn as sns
import os

def main():
    print("Loading dataset...", flush=True)
    df = pd.read_csv('data/processed/ml_dataset_clean.csv')

    # Drop features that shouldn't be used for training, but keep osm_id for grouping
    X = df.drop(columns=['name', 'risk_level']) # Keep osm_id in X for now to split, or split using df
    y = df['risk_level']
    groups = df['osm_id']

    # 1. Spatial Split: 80% train, 20% test using GroupShuffleSplit on osm_id
    print("Performing Spatial Group Split...", flush=True)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(gss.split(X, y, groups=groups))
    
    X_train_full = X.iloc[train_idx].drop(columns=['osm_id'])
    X_test = X.iloc[test_idx].drop(columns=['osm_id'])
    y_train_full = y.iloc[train_idx]
    y_test = y.iloc[test_idx]
    groups_train_full = groups.iloc[train_idx]

    numeric_features = ['elevation', 'slope', 'rainfall', 'distance_to_water']
    categorical_features = ['highway']

    # Preprocessing
    numeric_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())])

    categorical_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='constant', fill_value='missing')),
        ('onehot', OneHotEncoder(handle_unknown='ignore'))])

    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features),
            ('cat', categorical_transformer, categorical_features)])

    # Subsample for faster hyperparameter tuning (e.g., 10% of train set), respecting groups
    print("Subsampling for tuning...", flush=True)
    gss_tune = GroupShuffleSplit(n_splits=1, train_size=0.1, random_state=42)
    tune_idx, _ = next(gss_tune.split(X_train_full, y_train_full, groups=groups_train_full))
    X_tune = X_train_full.iloc[tune_idx]
    y_tune = y_train_full.iloc[tune_idx]
    groups_tune = groups_train_full.iloc[tune_idx]

    cv = GroupKFold(n_splits=3)

    # 1. Decision Tree Tuning
    print("Tuning Decision Tree...", flush=True)
    dt_pipeline = Pipeline(steps=[('preprocessor', preprocessor),
                                  ('classifier', DecisionTreeClassifier(random_state=42, class_weight='balanced'))])
    dt_param_grid = {
        'classifier__max_depth': [5, 10, 20, None],
        'classifier__min_samples_split': [2, 5, 10],
        'classifier__min_samples_leaf': [1, 2, 4]
    }
    dt_search = RandomizedSearchCV(dt_pipeline, dt_param_grid, n_iter=10, cv=cv, scoring='f1_macro', n_jobs=4, random_state=42)
    dt_search.fit(X_tune, y_tune, groups=groups_tune)
    dt_best = dt_search.best_estimator_
    dt_cv_score = dt_search.best_score_
    print("DT Best CV F1:", dt_cv_score, flush=True)

    # 2. Random Forest Tuning
    print("Tuning Random Forest...", flush=True)
    rf_pipeline = Pipeline(steps=[('preprocessor', preprocessor),
                                  ('classifier', RandomForestClassifier(random_state=42, class_weight='balanced'))])
    rf_param_grid = {
        'classifier__n_estimators': [100, 200],
        'classifier__max_depth': [10, 20, None],
        'classifier__min_samples_split': [2, 5],
        'classifier__min_samples_leaf': [1, 2],
        'classifier__max_features': ['sqrt']
    }
    rf_search = RandomizedSearchCV(rf_pipeline, rf_param_grid, n_iter=10, cv=cv, scoring='f1_macro', n_jobs=4, random_state=42)
    rf_search.fit(X_tune, y_tune, groups=groups_tune)
    rf_best = rf_search.best_estimator_
    rf_cv_score = rf_search.best_score_
    print("RF Best CV F1:", rf_cv_score, flush=True)

    # 3. Extra Trees Tuning
    print("Tuning Extra Trees...", flush=True)
    et_pipeline = Pipeline(steps=[('preprocessor', preprocessor),
                                  ('classifier', ExtraTreesClassifier(random_state=42, class_weight='balanced'))])
    et_search = RandomizedSearchCV(et_pipeline, rf_param_grid, n_iter=10, cv=cv, scoring='f1_macro', n_jobs=4, random_state=42)
    et_search.fit(X_tune, y_tune, groups=groups_tune)
    et_best = et_search.best_estimator_
    et_cv_score = et_search.best_score_
    print("ET Best CV F1:", et_cv_score, flush=True)

    # Train best models on full training data
    print("Training models on full train dataset (approx 396k rows)...", flush=True)
    dt_best.fit(X_train_full, y_train_full)
    rf_best.fit(X_train_full, y_train_full)
    et_best.fit(X_train_full, y_train_full)

    # Evaluate on Test Set
    print("Evaluating models...", flush=True)
    def evaluate_model(model, name):
        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, average='macro', zero_division=0)
        rec = recall_score(y_test, y_pred, average='macro')
        f1 = f1_score(y_test, y_pred, average='macro')
        return {'Model': name, 'Test Accuracy': acc, 'Test Precision': prec, 'Test Recall': rec, 'Test F1': f1}

    results = []
    results.append({'Model': 'Decision Tree', 'CV F1': dt_cv_score, **evaluate_model(dt_best, 'Decision Tree')})
    results.append({'Model': 'Random Forest', 'CV F1': rf_cv_score, **evaluate_model(rf_best, 'Random Forest')})
    results.append({'Model': 'Extra Trees', 'CV F1': et_cv_score, **evaluate_model(et_best, 'Extra Trees')})

    results_df = pd.DataFrame(results)
    os.makedirs('models', exist_ok=True)
    results_df.to_csv('models/model_comparison.csv', index=False)
    print("\n--- Model Comparison ---", flush=True)
    print(results_df.to_string(), flush=True)

    # Select Best Model based on CV F1 and Test F1
    best_model_name = results_df.sort_values(by=['CV F1', 'Test F1'], ascending=[False, False]).iloc[0]['Model']
    print(f"\nBEST MODEL SELECTED: {best_model_name}", flush=True)

    if best_model_name == 'Random Forest':
        final_model = rf_best
    elif best_model_name == 'Extra Trees':
        final_model = et_best
    else:
        final_model = dt_best

    # Final Evaluation
    y_train_pred = final_model.predict(X_train_full)
    train_f1 = f1_score(y_train_full, y_train_pred, average='macro')
    print(f"Train F1: {train_f1}", flush=True)

    y_pred = final_model.predict(X_test)
    print("\nClassification Report:", flush=True)
    print(classification_report(y_test, y_pred), flush=True)

    # Confusion Matrix
    print("Generating Confusion Matrix...", flush=True)
    cm = confusion_matrix(y_test, y_pred)
    plt.figure(figsize=(8,6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=['Low', 'Medium', 'High'], yticklabels=['Low', 'Medium', 'High'])
    plt.xlabel('Predicted')
    plt.ylabel('Actual')
    plt.title(f'Confusion Matrix - {best_model_name}')
    plt.savefig('models/confusion_matrix.png')

    # Test metrics JSON
    test_metrics = evaluate_model(final_model, best_model_name)
    test_metrics['Train F1'] = train_f1
    with open('models/test_metrics.json', 'w') as f:
        json.dump(test_metrics, f, indent=4)

    # Feature Importance
    print("Extracting feature importance...", flush=True)
    clf = final_model.named_steps['classifier']
    cat_encoder = final_model.named_steps['preprocessor'].named_transformers_['cat'].named_steps['onehot']
    cat_features = cat_encoder.get_feature_names_out(categorical_features)
    all_features = numeric_features + list(cat_features)
    importances = clf.feature_importances_

    fi_df = pd.DataFrame({'Feature': all_features, 'Importance': importances})
    fi_df = fi_df.sort_values(by='Importance', ascending=False).head(20)
    fi_df.to_csv('models/feature_importance.csv', index=False)

    # Save best model
    joblib.dump(final_model, 'models/routesense_best_model.joblib')
    print("Model saved to models/routesense_best_model.joblib", flush=True)

    # Predict on all data
    print("Predicting on full dataset...", flush=True)
    X_full_predict = X.drop(columns=['osm_id'])
    df['predicted_risk'] = final_model.predict(X_full_predict)
    probs = final_model.predict_proba(X_full_predict)
    df['low_probability'] = probs[:, 0]
    df['medium_probability'] = probs[:, 1]
    df['high_probability'] = probs[:, 2]

    df.to_csv('data/processed/ml_dataset_predictions.csv', index=False)
    print("Predictions saved to data/processed/ml_dataset_predictions.csv", flush=True)

if __name__ == '__main__':
    main()
