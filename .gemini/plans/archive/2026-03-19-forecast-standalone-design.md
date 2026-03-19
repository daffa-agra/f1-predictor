# Design Document: 2026 F1 Standalone Forecast Script

## 1. Problem Statement
The 2026 F1 Predictor currently relies on real-time qualifying or practice session data (e.g., `QualifyingPosition`, `GridPosition`) to generate race winner predictions. However, during early race weeks or in the absence of session data, the model cannot provide a prediction. This refactor aims to introduce a standalone forecasting capability that uses available 2026 historical data and metadata (`config/drivers_2026.json`) to generate "preliminary" predictions (forecasts) when session data is unavailable.

## 2. Requirements
### Functional Requirements:
- **Standalone Forecasting**: Create a new script `forecast_2026.py` specifically for generating pre-race forecasts when session data is missing.
- **Data Fallback**: Use `config/drivers_2026.json` for 2026 driver/team metadata and any available 2026 season stats for historical performance.
- **Grid Proxy**: If `QualifyingPosition` and `GridPosition` are missing, use the driver's average 2026 qualifying position (if available) or a default value (e.g., P20).
- **Forecast JSON**: Output the prediction to `website/forecast.json` with a flag `is_preliminary: true`.
- **UI Integration**: Update `website/index.html` to first check for `predictions.json` (live session data). If it's missing or from a previous race, fallback to `forecast.json` and display a "Preliminary" or "Forecast" tag.

### Non-Functional Requirements:
- **Data Integrity**: Ensure the forecast doesn't overwrite the main `predictions.json` file.
- **Accuracy**: Provide a clear UI indication that the forecast is based on historical data only.
- **Stability**: The forecast script should be robust to missing 2026 stats (e.g., at the start of the season).

### Constraints:
- Must use the existing XGBoost model.
- Must follow the 2026 metadata format in `config/drivers_2026.json`.

## 3. Architecture
### Components:
- `forecast_2026.py`: A new script that loads the model, fetches 2026 historical results (if available), and calculates the forecast using `drivers_2026.json`.
- `data_fetcher.py`: May need a small utility to fetch 2026-only stats for forecasting.
- `website/forecast.json`: The new output file for pre-race forecasts.
- `website/index.html`: The updated frontend that dynamically selects between `predictions.json` and `forecast.json` based on a "freshness" check.

### Data Flow:
1. `forecast_2026.py` is executed (manually or via a new GitHub Action).
2. It fetches historical 2026 results from the FastF1 API (if any races have occurred).
3. It loads the `config/drivers_2026.json` for current entry list.
4. It fits the `FeatureProcessor` with historical data.
5. It applies the "Avg Quali" proxy for the missing session features.
6. It runs the XGBoost model and exports `website/forecast.json`.
7. `website/index.html` loads the JSON and displays the "Forecast" tag if the `is_preliminary` flag is present.

## 4. Agent Team
- `data_engineer`: Create `forecast_2026.py` and implement the 2026 stats fetching and grid proxy logic.
- `coder`: Update `website/index.html` to handle the `forecast.json` fallback and "Forecast" tag.
- `tester`: Verify the forecast script with mock 2026 data and ensure UI fallback works correctly.

## 5. Risk Assessment & Mitigation
- **Risk**: No 2026 data available (early season).
- **Mitigation**: Fallback to P20 for all drivers and use global historical means from the training set.
- **Risk**: Forecast overwriting live predictions.
- **Mitigation**: Use a distinct file name (`forecast.json`) and explicit flag.

## 6. Success Criteria
1. `forecast_2026.py` generated and functional.
2. `website/forecast.json` correctly contains the `is_preliminary` flag.
3. `website/index.html` correctly fallbacks to `forecast.json` with a "Forecast" tag.
4. All tests pass and the pipeline is stable.
