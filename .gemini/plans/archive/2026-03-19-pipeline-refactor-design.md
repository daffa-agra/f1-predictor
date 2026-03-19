# Design Document: 2026 F1 Predictor Pipeline Refactor

## Problem Statement
The 2026 F1 Winner Prediction pipeline contains a Major severity bug in its category encoding logic. `FeatureProcessor` uses `LabelEncoder` without an `UNKNOWN` class, mapping new 2026 entries (drivers/teams) to ID `0`, resulting in clustered, inaccurate predictions. Additionally, the UI relies on a mock win probability, the 2026 race calendar mapping in `index.html` is incomplete, and driver/team metadata is hardcoded, hindering maintenance.

## Requirements

### Functional
- **Encoding Stability**: Replace `LabelEncoder` with `OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)` in `FeatureProcessor`.
- **Probabilistic UI**: Replace the linear win probability mock `(100 - (prediction * 5))` with a Gaussian distribution centered at P1, using model MSE (~18.0) to model uncertainty.
- **Complete Venue Support**: Manually populate `circuitMap` in `index.html` for all 22 venues of the 2026 season.
- **Configurable Metadata**: Extract 2026 driver/team metadata from `predictor.py` into `config/drivers_2026.json`.

### Non-Functional
- **Scalability**: Encoders must support dynamic fitting to new seasons without manual ID remapping.
- **Maintainability**: Clear separation between season-specific data (config) and prediction logic (source code).

## Approach

### Selected Approach: Robust Pipeline Refactor
Leverage `OrdinalEncoder` with `handle_unknown='use_encoded_value', unknown_value=-1` to ensure that any new driver, team, or event in 2026 that wasn't in the training data gets a unique `UNKNOWN` ID instead of being aliased to an existing driver.

### Data Flow
1. **Training**: `FeatureProcessor` fits `OrdinalEncoder` on 2020-2025 data.
2. **Config Load**: `predictor.py` loads `config/drivers_2026.json` for 2026 driver mapping.
3. **Inference**:
   - `FeatureProcessor.transform_for_prediction` applies fitted encoders.
   - `XGBRegressor` predicts a continuous `Position` value.
4. **UI Visualization**: `index.html` calculates win probability $P(Win)$ using a Gaussian distribution centered at 1:
   $P(Win) = \exp\left(-\frac{(prediction - 1)^2}{2 \cdot 18.0}\right) \cdot 100$

## Architecture

### Component Architecture
- **Config Store**: `config/drivers_2026.json` (Static JSON).
- **Pre-processing**: `src/f1_predictor/preprocessor.py` (OrdinalEncoder logic).
- **Inference**: `src/f1_predictor/predictor.py` (Metadata merging logic).
- **UI**: `website/index.html` (Probabilistic JS logic).

## Agent Team
- **data_engineer**: Refactor `FeatureProcessor` and create `config/drivers_2026.json`.
- **coder**: Update `predictor.py` and `website/index.html`.
- **tester**: Validate that new 2026 labels don't cause ID collisions.
- **code_reviewer**: Conduct a final quality gate.

## Success Criteria
1. **Unique Encoding**: Correct encoding of new 2026 labels as `-1` (or unique ID).
2. **Externalized Config**: Successful metadata loading from `config/drivers_2026.json`.
3. **Probabilistic UI**: Non-linear win probability display.
4. **Complete Circuit Map**: All 22 2026 races display correct circuit layout images.
5. **Clean Review**: Zero `Critical` or `Major` findings in the final `code_reviewer` pass.
