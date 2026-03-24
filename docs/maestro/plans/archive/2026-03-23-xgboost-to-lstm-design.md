---
design_depth: deep
task_complexity: medium
---

# Design Document: XGBoost to LSTM Migration

## Problem Statement
The current F1 predictor uses an XGBoost Regressor (`xgboost.XGBRegressor`) operating on flat, rolling-average features to predict race finishing positions. While effective, this approach fails to explicitly model the temporal "form" of drivers and teams as sequences of distinct events, limiting the model's capacity to learn complex temporal patterns. The goal is to migrate the predictor to a sequence-based Deep Learning architecture (LSTM) using TensorFlow/Keras to improve prediction accuracy (Podium, Top 10, MAE).

## Requirements

**Functional Requirements:**
- `REQ-1`: The system must ingest raw F1 data (`fastf1`) and engineer temporal features (e.g., driver histories over the last N races).
- `REQ-2`: `preprocessor.py` must shape data into 3D tensors (`samples` x `timesteps` x `features`) grouped by driver.
- `REQ-3`: `model.py` must define a deep learning model using TensorFlow/Keras (`tf.keras.Sequential` or Functional API) incorporating LSTM layers to model sequence data.
- `REQ-4`: The model training loop must use a generator or `tf.data.Dataset` pipeline to manage sequence batching safely without overlapping driver histories improperly.
- `REQ-5`: The prediction pipeline (`predictor.py`) and evaluation scripts (`evaluate_model.py`) must be refactored to consume the new model format and handle `numpy`/`tensor` outputs rather than XGBoost estimators.
- `REQ-6`: `fine_tune.py` must be rewritten to support Keras hyperparameter tuning (e.g., using KerasTuner) instead of `scikit-learn`'s `RandomizedSearchCV`.

**Non-Functional Requirements:**
- The deep learning framework must be TensorFlow (Keras).
- The architecture must prioritize improving existing accuracy metrics (Podium, Top 10, MAE) over XGBoost.
- `pyproject.toml` and `requirements.txt` must be updated to remove XGBoost and include TensorFlow dependencies.

## Approach

### Approach 1: LSTM Sequence Model (Selected)

**Summary**: Replace XGBoost with a TensorFlow/Keras Recurrent Neural Network (LSTM). Instead of engineering rolling averages over the last N races, we will feed the model raw statistics of the last N races (timesteps) for a given driver. 

**Architecture**: 
- `Input Layer` (shape: `N_timesteps` x `M_features`)
- `LSTM Layer(s)` (to capture driver/team form)
- `Dense Layers` (to predict final continuous finish position)
- Custom data generator (`tf.keras.utils.Sequence`) grouping sequences by driver.

**Pros**: 
- Natively models temporal dynamics (driver form, car updates) over a season.
- Better capacity to learn complex interactions between track characteristics and team setups than tree methods.

**Cons**: 
- Data formatting is significantly more complex (3D tensors, padding).
- Longer training time and more hyperparameters to tune.

**Best When**: Modeling data with strong sequential dependencies (like a sports season).
**Risk Level**: High (Requires full pipeline rewrite).

### Approach 2: Feed-Forward MLP (Alternative)

**Summary**: Keep the existing 2D rolling-average feature set from `FeatureProcessor` but swap the `XGBRegressor` for a standard `tf.keras.Sequential` Multi-Layer Perceptron (MLP).

**Architecture**: 
- `Input Layer` (shape: `flat_features`)
- `Dense Layers` with Batch Normalization and Dropout
- Output node (finish position prediction)

**Pros**: 
- Minimal changes to `preprocessor.py`.
- Faster implementation and easier debugging.

**Cons**: 
- May not outperform XGBoost significantly since it uses the exact same feature representation.
- Does not explicitly model the temporal structure.

**Best When**: A quick transition to a Deep Learning framework is required without data re-engineering.
**Risk Level**: Low.

### Decision Matrix

| Criterion | Weight | LSTM Sequence Model | Feed-Forward MLP |
|---|---|---|---|
| Captures Temporal Form | 40% | 5: Natively models form using recurrent cells. | 2: Relies on simple rolling averages (status quo). |
| Potential Accuracy Gain | 40% | 4: High ceiling if data is structured correctly. | 2: Unlikely to beat XGBoost without new feature representations. |
| Implementation Simplicity | 20% | 2: Requires full rewrite of preprocessor and training loops. | 5: Drop-in replacement for XGBRegressor. |
| **Weighted Total** | 100% | **4.0** | **2.6** |

*The LSTM approach was selected despite higher implementation complexity because it offers the highest potential for accuracy improvement by natively modeling driver form (Traces To: REQ-1, REQ-3).* 

## Architecture

The `FeatureProcessor` in `preprocessor.py` will transition from producing flat DataFrames to yielding 3D sequences (driver x timesteps x features). A new `SequenceGenerator` class will be created in `model.py` to batch sequences per driver and ensure the data isn't leaked across races. The core `ModelPipeline` will instantiate a `tf.keras.Sequential` model (LSTM layers followed by Dense layers). Prediction and evaluation scripts will handle tensors directly and expect shapes of `(samples, timesteps, features)` instead of Pandas Series. *We will use TensorFlow Datasets or custom sequence generators for training (Traces To: REQ-2, REQ-4).* 

## Agent Team

The following agents will be assigned to implement the transition:
- **`data_engineer`**: Responsible for rewriting `src/f1_predictor/preprocessor.py` to create the 3D tensor sequences per driver and generating new temporal features (e.g., historical lap times, track characteristics).
- **`ai_engineer`**: Responsible for defining the `tf.keras.Sequential` LSTM architecture in `src/f1_predictor/model.py`, creating the `tf.data.Dataset` / `SequenceGenerator` for training, and refactoring `predictor.py` and evaluation/fine-tuning scripts.
- **`tester`**: Responsible for writing unit tests for the sequence generation logic, ensuring no data leakage across time boundaries, and validating model input shapes.

## Risk Assessment

**Data Leakage Across Time Boundaries**
*Risk:* Grouping data by driver for sequence generation could accidentally include future race data in the training set.
*Mitigation:* The `SequenceGenerator` must strictly enforce temporal order and pad sequences only with historical data. A dedicated suite of tests will validate sequence integrity (Traces To: REQ-4).

**Overfitting on Limited History**
*Risk:* Deep models with LSTM cells are prone to overfitting on small datasets like F1 races, especially with complex new features.
*Mitigation:* We will incorporate Dropout, L2 regularization, and Early Stopping. Hyperparameter optimization via `KerasTuner` will be constrained to simpler LSTM architectures initially (Traces To: REQ-6).

**Incompatible Evaluation Loop**
*Risk:* The evaluation and prediction scripts currently expect scikit-learn compatible objects.
*Mitigation:* `predictor.py` and `evaluate_model.py` will be rewritten to expect native Keras predictions, handling array shapes explicitly instead of DataFrames (Traces To: REQ-5).

## Success Criteria

1. `src/f1_predictor/preprocessor.py` successfully generates 3D tensors (`samples` x `timesteps` x `features`) grouped by driver without exposing future race data.
2. `src/f1_predictor/model.py` trains an LSTM-based deep learning model using TensorFlow/Keras on historical F1 data without data leakage.
3. The hyperparameter optimization script (`scripts/fine_tune.py`) is rewritten to support Keras tuning (e.g., KerasTuner) instead of scikit-learn.
4. Evaluation scripts (`scripts/evaluate_model.py`) and predictions correctly handle the new Keras output shapes.
5. Project dependencies (`pyproject.toml`, `requirements.txt`) successfully migrate from XGBoost to TensorFlow.
6. Tests pass for the new sequence generation logic.
7. The LSTM model achieves a measurable improvement (or near-parity as a baseline) in Podium Accuracy and Top 10 Accuracy over the previous XGBoost baseline.
