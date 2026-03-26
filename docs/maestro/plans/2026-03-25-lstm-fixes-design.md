# Design Document: F1 Predictor LSTM Fixes & CI Stabilization

**Status**: Approved
**Date**: 2026-03-25
**Design Depth**: deep
**Task Complexity**: medium

## 1. Problem Statement
The F1 Predictor recently migrated to a PyTorch LSTM model to capture temporal driver performance. However, three technical regressions and one CI environment error were identified:
1.  **Feature Lag**: The rolling average logic incorrectly "shifts" away the most recent race performance during real-time prediction, causing the model to use stale data (from 2 races ago).
2.  **API Loading Mismatch**: The model loading logic hardcodes hyperparameters, leading to errors when loading models trained with non-default configurations (e.g., hidden size 128).
3.  **Dropout Implementation**: LSTM dropout is only active for multi-layer models in the current PyTorch implementation.
4.  **CI Failure**: The GitHub Action environment is failing with a `ModuleNotFoundError` for `xgboost`, which was supposed to be removed.

## 2. Requirements

**Functional Requirements:**
- `REQ-1`: The preprocessor must provide a `transform_for_prediction` path that uses the *latest* historical race data without shifting it into the future.
- `REQ-2`: `ModelPipeline` must save and load hyperparameters (`hidden_size`, `num_layers`, `dropout`) to ensure consistency between training and inference.
- `REQ-3`: `LSTMModel` must apply dropout to the output of the LSTM layer regardless of the number of layers.
- `REQ-4`: The CI environment must be purged of `xgboost` and enforce clean dependency installation.

**Non-Functional Requirements:**
- **Reliability**: Model loading must not crash if training parameters change.
- **Accuracy**: Prediction inputs must reflect the most recent state of the F1 season.
- **Developer Experience**: Scripts must use consistent PyTorch-centric APIs.

**Constraints:**
- Must maintain compatibility with existing 2026 data schema (QualifyingPosition, Position, etc.).
- Must not introduce data leakage in the training path.

## 3. Approach

**Selected Approach: Unified Feature Adapter**
We will implement a robust fix that unifies the feature extraction logic while allowing for context-aware shifting.

**Implementation Details:**
1.  **Preprocessor Refactor**:
    - Update `_calculate_rolling_features` to accept an optional `shift_final_row=True` argument.
    - During training (`transform`), `shift_final_row` remains `True` to prevent leakage.
    - During prediction (`transform_for_prediction`), it will calculate features for the historical data *without* the final shift for the very last row, or by appending the current qualifying data to the history and calculating rolling stats up to that point.
    - **Rationale**: This ensures the model sees the driver's form from the *most recent* completed race. *(Traces To: REQ-1)*

2.  **Model Pipeline Update**:
    - Modify `ModelPipeline.save` to dump hyperparameters in the `checkpoint` dict.
    - Update `ModelPipeline.load` to read these parameters before creating the `LSTMModel` instance.
    - **Rationale**: Prevents weight size mismatch errors. *(Traces To: REQ-2)*

3.  **LSTM Layer Fix**:
    - Ensure `nn.Dropout` is applied explicitly in the `forward` pass after the LSTM output, rather than relying only on the `nn.LSTM` constructor's parameter.
    - **Rationale**: Enables dropout for single-layer models. *(Traces To: REQ-3)*

4.  **CI Cleanup**:
    - Update `.github/workflows/f1-prediction.yml` to use a new cache key and explicitly run `pip uninstall -y xgboost` before installing the package.
    - **Rationale**: Ensures a clean, PyTorch-only environment. *(Traces To: REQ-4)*

**Decision Matrix scoring**:
- Prediction Accuracy: 5/5
- Maintainability: 5/5
- Implementation Effort: 4/5
- System Robustness: 5/5
- **Weighted Total: 4.8**

**Alternatives Considered**:
- **Approach 2 (Parallel Extractors)**: Rejected because it creates technical debt by duplicating the feature definition logic. *(considered: Duplicate logic — rejected because it risks feature drift between training and inference)*

## 4. Risk Assessment

| Risk | Impact | Mitigation Strategy |
|------|--------|---------------------|
| **Data Leakage in Refactor** | High | Add a unit test that specifically checks if `transform` (training) produces identical results before and after the refactor for historical rows. |
| **Model Weight Incompatibility** | Medium | The `ModelPipeline.load` will be updated to be backward-compatible by falling back to default values if metadata is missing. |
| **CI Cache Persistence** | Low | Update the cache key in the GitHub Action workflow to force a fresh dependency installation. |
| **LSTM Prediction Scaling** | Low | Ensure the preprocessor handles cases where a driver has very little history by using baseline stats correctly. |

## 5. Success Criteria
1. `fine_tune.py` runs successfully on GitHub Action without `xgboost` error.
2. `ModelPipeline.load()` successfully loads a model with `hidden_size=128`.
3. Predictions for R3 2026 use the performance data from R2 2026 (Chinese GP).
4. `pytest tests/` passes 100%.
