# Design Document: F1 Predictor Dynamic Context & Robustness

**Date**: 2026-03-18
**Project**: f1-predictor

## 1. Problem Statement
The current `f1-predictor` project, while structured, suffers from several technical risks identified in the latest code review:
- **Stale Cache Bug**: The historical data fetcher ignores requested year ranges if a file exists, preventing the model from seeing new data.
- **Hardcoded Logic**: Fine-tuning and CI/CD workflows rely on specific round numbers, requiring manual updates as the season progresses.
- **Inference Inefficiency**: Redundant fetching of historical data during every prediction to calculate baseline statistics.
- **Metadata Gaps**: Missing standard configuration (license) in project files.

## 2. Requirements
### Functional
- **Dynamic Range Caching**: Invalidate or partition the historical data cache based on requested start/end years.
- **Autonomous Fine-Tuning**: Automatically identify and fetch data for all completed rounds in the current season.
- **Stateful Pipeline**: Store pre-calculated driver/team baseline stats in the `ModelPipeline` for efficient inference.
- **Parameter-Free CI/CD**: Default to predicting the next upcoming race without hardcoded arguments.

### Non-Functional
- **Performance**: Eliminate network/IO overhead for historical years during prediction.
- **Maintainability**: Centralize all dynamic schedule logic to use `fastf1` as the source of truth.

## 3. Selected Approach: Integrated Pipeline & Dynamic Context
We will evolve the architecture to be range-aware and state-persistent. The data layer will partition caches by year range, and the model artifact will become a self-contained execution context containing all statistics needed for inference.

## 4. Architecture
### 4.1 Components
- **`DataFetcher` (Refactor)**: 
  - `fetch_historical_data(start, end)`: Uses range-based naming (e.g., `historical_data_2020_2025.csv`).
- **`ModelPipeline` (Refactor)**: 
  - New `baselines` attribute to store pre-calculated stats (driver/team means).
- **`FeatureProcessor` (Refactor)**: 
  - `fit()` now explicitly exposes the calculated baselines for storage in the pipeline.
  - `transform_for_prediction()` uses provided baselines instead of raw historical dataframes.
- **`FineTuner` (Refactor)**: 
  - Uses `fastf1.get_event_schedule()` to dynamically determine which 2026 rounds to fetch.
- **`Predictor` (Refactor)**: 
  - Simplifies logic to use `ModelPipeline.baselines`.

### 4.2 Data Flow
1. **Training**: `Fetcher(range)` -> `Processor.fit` (gen baselines) -> `Model.fit` -> `Save Pipeline(model, processor, baselines)`.
2. **Inference**: `Load Pipeline` -> `Fetch Target Qual` -> `Processor.transform_for_prediction(target, pipeline.baselines)` -> `Model.predict`.

## 5. Agent Team
- **Architect**: Oversees the ModelPipeline schema change and cache naming conventions.
- **Coder**: Implements the logic changes in data fetching, preprocessing, and prediction.
- **Tester**: Validates the dynamic behavior across different year ranges and rounds.

## 6. Risk Assessment & Mitigation
- **Risk**: Cache Bloat from multiple range files. **Mitigation**: Use consistent naming to allow manual pruning; consider a maximum number of cache files.
- **Risk**: Pipeline version mismatch. **Mitigation**: Ensure `load()` handles missing properties gracefully or triggers a recalculation.

## 7. Success Criteria
- **Correctness**: Requesting `2020-2026` after `2020-2025` triggers a new data fetch.
- **Autonomy**: `fine_tune.py` works correctly mid-season without code changes.
- **Speed**: Predictor executes without re-reading historical CSV files.
- **Compliance**: `pyproject.toml` includes a license field.
