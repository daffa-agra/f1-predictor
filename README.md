# F1 Race Winner Predictor

An ML-powered tool to predict Formula 1 race results using historical data from the `fastf1` library.

## Key Features
- **Stateful Feature Engineering**: Unified `FeatureProcessor` ensures consistency between training and inference.
- **Robust Data Fetching**: Exponential backoff retry logic for reliable API interactions.
- **Leakage-Free Modeling**: Strictly temporal rolling features to prevent look-ahead bias.
- **Dynamic Scheduling**: Automatically fetches upcoming race schedules.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/f1-predictor.git
   cd f1-predictor
   ```

2. Install the package in editable mode:
   ```bash
   pip install -e .
   ```

## Usage

### 1. Training the Model
Train the model on the last 5 years of historical data:
```bash
f1-predictor --train
```
This will save a `ModelPipeline` artifact to `models/f1_pipeline.joblib`.

### 2. Predicting Upcoming Races
Predict the results for the next upcoming race:
```bash
f1-predictor
```

Predict a specific round:
```bash
f1-predictor --predict 5 --year 2025
```

## Project Structure
- `src/f1_predictor/`: Core package.
  - `data_fetcher.py`: FastF1 API interactions with retry logic.
  - `preprocessor.py`: `FeatureProcessor` for point-in-time feature engineering.
  - `model.py`: `ModelPipeline` for model and metadata management.
  - `predictor.py`: CLI and prediction logic.
- `tests/`: Comprehensive test suite.
- `pyproject.toml`: Project configuration and entry points.

## Testing
Run the test suite using `pytest`:
```bash
pytest
```
# f1-predictor
