---
task_complexity: medium
---

# Implementation Plan: XGBoost to LSTM Migration

## Plan Overview
- **Total Phases**: 4
- **Agents Involved**: `data_engineer`, `ai_engineer`, `coder`, `tester`
- **Estimated Effort**: High

## Dependency Graph
```mermaid
graph TD
    P1[Phase 1: Dependencies & Preprocessor (3D Tensors)]
    P2[Phase 2: LSTM Model Architecture & Generator]
    P3[Phase 3: Prediction & Evaluation Pipeline Update]
    P4[Phase 4: Tests Update]
    
    P1 --> P2
    P1 --> P4
    P2 --> P3
    P2 --> P4
    P3 --> P4
```

## Execution Strategy

| Stage | Phases | Execution Mode | Rationale |
|---|---|---|---|
| Stage 1 | Phase 1 | Sequential | Foundational data shape changes. |
| Stage 2 | Phase 2 | Sequential | Core ML architecture relies on new data shape. |
| Stage 3 | Phase 3 | Sequential | Updates to prediction and evaluation scripts using the new model. |
| Stage 4 | Phase 4 | Sequential | Fixes tests across all modified modules. |

## Phase Details

### Phase 1: Dependencies & Preprocessor (3D Tensors)
- **Objective**: Update dependencies to use TensorFlow. Rewrite `FeatureProcessor` to generate sliding windows (3D Tensors) instead of 2D DataFrames.
- **Agent Assignment**: `data_engineer`
- **Files to Modify**:
  - `pyproject.toml`
  - `requirements.txt`
  - `src/f1_predictor/preprocessor.py`
- **Implementation Details**:
  - Replace `xgboost` with `tensorflow` in dependency files. Keep `scikit-learn` for encoders/scalers.
  - In `preprocessor.py` (`FeatureProcessor` class):
    - Introduce a `time_steps` parameter (e.g., default 5) representing the sequence length.
    - Modify the `transform` method to group the data by `DriverID` and generate sliding windows. Given `N` total races for a driver, it should generate `N - time_steps` sequences, each of shape `(time_steps, M_features)`.
    - Modify `transform_for_prediction` to take the last `time_steps` races for each driver in the current grid, ensuring it returns a shape of `(N_drivers, time_steps, M_features)`.
- **Validation Criteria**:
  - `pip install -e .` succeeds.
  - A simple manual test script calling `FeatureProcessor.transform` yields a numpy array of shape `(samples, time_steps, features)`.
- **Dependencies**: 
  - `blocked_by`: []
  - `blocks`: [2, 4]

### Phase 2: LSTM Model Architecture & Generator
- **Objective**: Replace the `xgboost` model with a `tf.keras` LSTM model in `ModelPipeline`. Add a Keras-compatible sequence generator if needed.
- **Agent Assignment**: `ai_engineer`
- **Files to Modify**:
  - `src/f1_predictor/model.py`
- **Implementation Details**:
  - Import `tensorflow as tf` and remove XGBoost imports.
  - In `ModelPipeline.train`, instantiate a `tf.keras.Sequential` model:
    - `Input` layer with shape `(time_steps, features)`.
    - 1-2 `LSTM` layers (e.g., 64 or 128 units, with dropout).
    - `Dense` output layer for continuous prediction (finish position).
    - Compile with `adam` optimizer and `mse` loss.
  - Update `ModelPipeline.predict` to use `self.model.predict`.
  - Handle model saving and loading using `tf.keras.models.save_model` and `load_model` instead of `joblib` for the model part (the preprocessor can still be saved via joblib).
- **Validation Criteria**:
  - Dummy 3D numpy arrays can be passed to `ModelPipeline.train` and `predict` without shape errors.
- **Dependencies**: 
  - `blocked_by`: [1]
  - `blocks`: [3, 4]

### Phase 3: Prediction & Evaluation Pipeline Update
- **Objective**: Update the main prediction and evaluation scripts to pass the correct sequence history to the preprocessor and handle Keras outputs.
- **Agent Assignment**: `coder`
- **Files to Modify**:
  - `src/f1_predictor/predictor.py`
  - `scripts/evaluate_model.py`
  - `scripts/fine_tune.py`
- **Implementation Details**:
  - **`predictor.py`**: Update `predict_upcoming_race`. It must now fetch the *past N races* (where N = `time_steps`) for the drivers, rather than just the current event details, and pass this history to `transform_for_prediction`.
  - **`evaluate_model.py`**: Ensure metrics handling works with the output shape of `model.predict()`, which usually returns `(samples, 1)`. Flatten or reshape it to compute MAE and Accuracy. Ensure the test data split correctly preserves temporal order.
  - **`fine_tune.py`**: Switch from `RandomizedSearchCV` to `keras_tuner.RandomSearch` or `Hyperband`. Define a model-building function for KerasTuner.
- **Validation Criteria**:
  - `python scripts/evaluate_model.py` runs end-to-end and prints accuracy metrics without crashing.
- **Dependencies**: 
  - `blocked_by`: [2]
  - `blocks`: [4]

### Phase 4: Tests Update
- **Objective**: Fix failing tests resulting from the change in data shapes and model types.
- **Agent Assignment**: `tester`
- **Files to Modify**:
  - `tests/test_preprocessor.py`
  - `tests/test_feature_processor.py`
  - `tests/test_encoding_stability.py`
  - `tests/test_forecast_integration.py`
- **Implementation Details**:
  - Update `test_feature_processor.py` assertions: instead of checking that the output DataFrame length matches the input length, check that the output numpy array has shape `(expected_samples, time_steps, features)`.
  - Update `test_preprocessor.py` and `test_encoding_stability.py` to expect 3D arrays or handle the new model serialization logic (joblib + Keras `.keras` / `.h5` files).
  - Update mock data in tests to have enough historical "races" to satisfy the `time_steps` requirement (e.g., at least 6 mock races if `time_steps`=5).
- **Validation Criteria**:
  - `pytest tests/` passes successfully.
- **Dependencies**: 
  - `blocked_by`: [1, 2, 3]
  - `blocks`: []

## File Inventory

| File | Phase | Purpose |
|---|---|---|
| `pyproject.toml` | 1 | Update dependencies |
| `requirements.txt` | 1 | Update dependencies |
| `src/f1_predictor/preprocessor.py` | 1 | 3D tensor logic |
| `src/f1_predictor/model.py` | 2 | Keras LSTM architecture |
| `src/f1_predictor/predictor.py` | 3 | Pass sequence history |
| `scripts/evaluate_model.py` | 3 | Handle Keras evaluation |
| `scripts/fine_tune.py` | 3 | Implement KerasTuner |
| `tests/test_preprocessor.py` | 4 | Fix test assertions |
| `tests/test_feature_processor.py` | 4 | Fix test assertions |
| `tests/test_encoding_stability.py` | 4 | Fix mock model types |
| `tests/test_forecast_integration.py` | 4 | Update mock data history length |

## Risk Classification
- Phase 1: HIGH - Core data shape change. Must avoid look-ahead bias.
- Phase 2: MEDIUM - Standard Keras implementation, but must handle mixed data types cleanly.
- Phase 3: HIGH - Integrating sequence fetching in production inference is tricky.
- Phase 4: LOW - Standard test refactoring.

## Execution Profile
- Total phases: 4
- Parallelizable phases: 0 (in 0 batches)
- Sequential-only phases: 4
- Estimated sequential wall time: ~15 minutes

## Cost Estimate

| Phase | Agent | Model | Est. Input | Est. Output | Est. Cost |
|-------|-------|-------|-----------|------------|----------|
| 1 | `data_engineer` | Pro | ~2000 | ~1000 | $0.06 |
| 2 | `ai_engineer` | Pro | ~1500 | ~800 | $0.05 |
| 3 | `coder` | Pro | ~2500 | ~1200 | $0.07 |
| 4 | `tester` | Pro | ~3000 | ~1500 | $0.09 |
| **Total** | | | **~9000** | **~4500** | **$0.27** |