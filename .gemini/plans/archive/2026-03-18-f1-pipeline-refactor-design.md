# Design Document: F1 Predictor Pipeline Refactor

**Date**: 2026-03-18
**Project**: f1-predictor

## 1. Problem Statement
The current `f1-predictor` project has several architectural flaws and technical debt:
- **Critical Data Leakage**: Features like rolling averages are calculated using the global mean of the target variable (`Position`), introducing look-ahead bias.
- **Feature Inconsistency**: Inference-time features are manually reconstructed and do not match the training-time features (e.g., hardcoded driver/team IDs).
- **Environment Fragility**: Manual `sys.path` manipulation and hardcoded dates (e.g., 2026) make the project difficult to run and maintain across different environments.

## 2. Requirements
### Functional
- **Point-in-Time Prediction**: Features (rolling averages, track history) must only use data available *prior* to the race being predicted.
- **Unified Feature Encoding**: Categorical encoders (`LabelEncoder`, `StandardScaler`) must be fitted during training and reused identically during inference.
- **Dynamic Date Handling**: Use `fastf1` APIs to fetch the current or next upcoming race schedule dynamically.

### Non-Functional
- **Reliability**: Implement retry logic with exponential backoff for `fastf1` API calls.
- **Maintainability**: Transition to a standard Python project structure with `pyproject.toml`.
- **Testability**: Increase unit test coverage for core prediction and feature engineering logic to >80%.

### Constraints
- Must continue to use `fastf1` and `xgboost`.
- Support Python 3.9+ environments.

## 3. Selected Approach: Shared Feature Pipeline
We will implement a stateful `FeatureProcessor` class that serves as the single source of truth for feature engineering, encoding, and imputation. This ensures that training and inference paths use identical logic, eliminating the risk of feature drift or inconsistency.

## 4. Architecture
### 4.1 Components
- **`FeatureProcessor` Class**: 
  - `fit(training_df)`: Fits `LabelEncoder` and `StandardScaler` objects and calculates historical baseline statistics.
  - `transform(df)`: Computes rolling averages and expanding means based on provided data, ensuring strictly temporal shifts to avoid leakage.
  - `transform_for_prediction(race_df, historical_df)`: Maps the current race's features using the fitted encoders and pre-calculated baseline statistics.
- **`ModelPipeline`**: A wrapper object that stores the `FeatureProcessor` and the `XGBoost` model as a single, loadable joblib artifact (`models/f1_pipeline.joblib`).
- **`fastf1` Retry Decorator**: A utility in `data_fetcher.py` that wraps API calls with exponential backoff.
- **Project Structure**: Use `pyproject.toml` for dependency management and a console script entry point for CLI access.

### 4.2 Data Flow
1. **Training**: `fetch_historical_data` -> `FeatureProcessor.fit_transform` -> `XGBRegressor.fit` -> `Save ModelPipeline`.
2. **Inference**: `fetch_race_context` -> `Load ModelPipeline` -> `FeatureProcessor.transform_for_prediction` -> `XGBRegressor.predict`.

## 5. Agent Team
- **Architect**: Oversees the `FeatureProcessor` implementation and project restructuring.
- **Coder**: Implements the `FeatureProcessor`, `ModelPipeline`, and `fastf1` retry logic.
- **Tester**: Develops a comprehensive suite of unit tests for the feature engineering and prediction logic.
- **DevOps Engineer**: Configures `pyproject.toml` and ensures the environment setup is robust.

## 6. Risk Assessment & Mitigation
- **Risk**: Feature Drift Over Seasons. **Mitigation**: Implement `FeatureProcessor` versioning in `ModelPipeline`.
- **Risk**: `fastf1` API Stability. **Mitigation**: Exponential backoff retry logic and robust local caching.
- **Risk**: Inconsistent Categorical IDs. **Mitigation**: Store and reuse `LabelEncoder` objects within the `ModelPipeline` artifact.

## 7. Success Criteria
- **Correctness**: Zero data leakage (look-ahead bias) during training.
- **Feature Consistency**: Identical feature mapping for training and inference.
- **Robustness**: 100% success rate for predicting current or next upcoming races (if data is available).
- **Usability**: Single-command install and run via `pip install -e .` and `f1-predictor`.
