# Design Document: F1 Predictor Accuracy Enhancements (v2.0)

**Status**: Proposed
**Date**: 2026-03-25
**Design Depth**: Deep
**Task Complexity**: Medium

## 1. Problem Statement
The current LSTM-based F1 Predictor achieves a mean absolute error (MAE) of ~5.0. Analysis reveals three primary areas for improvement:
1.  **Feature Granularity**: The model uses rank-based positions (1-20), which lose the "actual distance" between drivers (e.g., P1 vs P2 could be 0.01s or 1.0s).
2.  **Data Normalization**: Neural networks, including LSTMs, are sensitive to input scales. Current inputs mix IDs (0-100+) and positions (1-20) without scaling.
3.  **Temporal Weighting**: The LSTM weights all races in a sequence equally by only using the final hidden state. An Attention mechanism is needed to prioritize more recent or relevant events.

## 2. Requirements

- `REQ-1`: Calculate **Qualifying Time Delta** (percentage gap to pole) to capture raw pace.
- `REQ-2`: Implement **Standard Scaling** for all numerical features in `FeatureProcessor`.
- `REQ-3`: Update `LSTMModel` to include a **Self-Attention Layer**.
- `REQ-4`: Categorize **Status** into `is_mechanical_dnf` to separate reliability from driver form.
- `REQ-5`: Make `time_steps` a tunable hyperparameter in the fine-tuning pipeline.

## 3. Proposed Approach

### Layer 1: Data Acquisition (data_fetcher.py)
- **Qualifying Pace**: Extract the best lap time (Q1/Q2/Q3) for each driver. Calculate `QDelta = (DriverLapTime - PoleLapTime) / PoleLapTime`.
- **Reliability Signal**: Map `Status` strings (e.g., 'Engine', 'Gearbox') to a binary `is_mechanical` flag.

### Layer 2: Feature Processing (preprocessor.py)
- **Standardization**: Fit a `sklearn.preprocessing.StandardScaler` on historical data and apply it to `QualifyingPosition`, `QDelta`, and rolling averages.
- **Flexible Windows**: Refactor `transform` to accept `time_steps` dynamically.

### Layer 3: Model Architecture (model.py)
- **AttentionMechanism**: 
  - Input: LSTM hidden states for all time steps.
  - Logic: Compute alignment scores via a linear layer, apply softmax, and return a weighted sum of hidden states.
  - Benefit: Allows the model to focus on "peak performance" or "recent trends" rather than just the last race.

## 4. Decision Matrix

| Criterion | Weight | Simple LSTM (Current) | Attention LSTM (Proposed) |
| :--- | :---: | :--- | :--- |
| **Accuracy (MAE)** | 40% | 3: Baseline performance | 5: Better granular pace & focus |
| **Robustness** | 30% | 4: Simple, few failure points | 4: Scaling prevents gradient explosion |
| **Explainability** | 20% | 2: Black box | 4: Attention weights show "important" races |
| **Latency** | 10% | 5: Very fast | 4: Slightly higher complexity |
| **Weighted Total** | | **3.3** | **4.6** |

## 5. Risk Assessment

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **Inconsistent Q-Data** | Medium | Use percentage deltas instead of raw seconds to handle different track lengths. |
| **Overfitting** | High | Increase dropout and use early stopping during hyperparameter tuning. |
| **Scaling Leakage** | Medium | Fit the scaler ONLY on training data; transform test data using the fitted parameters. |

## 6. Success Criteria
1. **MAE Reduction**: Achieve Avg Position MAE < 4.5 on 2026 R1-R2.
2. **Top 10 Accuracy**: Increase from 60% to >70%.
3. **Hyperparameter Tuning**: Successfully determine the optimal `time_steps` via grid search.
