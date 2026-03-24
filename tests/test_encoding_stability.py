import pandas as pd
import numpy as np
import pytest
from f1_predictor.preprocessor import FeatureProcessor
from f1_predictor.model import ModelPipeline
import os

@pytest.fixture
def historical_df():
    """Mock historical data for fitting the processor. Need enough for time_steps=2"""
    # Create 3 races per driver
    data = []
    for rnd in [1, 2, 3]:
        data.extend([
            {'Year': 2024, 'RoundNumber': rnd, 'Abbreviation': 'VER', 'TeamName': 'Red Bull', 'Position': 1, 'QualifyingPosition': 1, 'GridPosition': 1, 'EventName': f'Race {rnd}'},
            {'Year': 2024, 'RoundNumber': rnd, 'Abbreviation': 'HAM', 'TeamName': 'Mercedes', 'Position': 2, 'QualifyingPosition': 2, 'GridPosition': 2, 'EventName': f'Race {rnd}'},
        ])
    return pd.DataFrame(data)

def test_encoding_stability_unseen_data(historical_df):
    """
    Ensure the FeatureProcessor handles unknown categorical data by encoding them as -1,
    and verify the ModelPipeline can still produce predictions from such data.
    """
    processor = FeatureProcessor(time_steps=2)
    processor.fit(historical_df)
    
    # Create prediction data with UNSEEN driver, team, and event
    prediction_df = pd.DataFrame({
        'Abbreviation': ['COL'],      # Unseen driver (Colapinto)
        'TeamName': ['Williams'],      # Unseen team
        'QualifyingPosition': [15],
        'GridPosition': [15],
        'EventName': ['Azerbaijan GP'] # Unseen event
    })
    
    # Empty history for unseen driver
    history_df = pd.DataFrame(columns=historical_df.columns)
    
    # 1. Transform for prediction
    X_pred = processor.transform_for_prediction(history_df, prediction_df)
    
    # 2. Assert unseen categorical entries are encoded as -1 (the last 3 features are IDs)
    # The output is 3D: (samples, timesteps, features)
    assert X_pred.shape == (1, 2, len(processor.feature_cols))
    
    # For padded sequences, all timesteps should have the unseen IDs (-1)
    assert np.all(X_pred[0, :, -3] == -1) # DriverID
    assert np.all(X_pred[0, :, -2] == -1) # TeamID
    assert np.all(X_pred[0, :, -1] == -1) # EventID
    
    # 3. Assert baseline statistics use global mean for unseen entries
    global_mean = historical_df['Position'].mean()
    # Indices: DriverAvg=2, TeamAvg=3, EventAvg=4
    assert np.all(X_pred[0, :, 2] == global_mean)

    # 4. Verify the rest of the pipeline functions
    # Fit processor and prepare training data
    X_train, y_train = processor.transform(historical_df)
    
    # Initialize and train ModelPipeline
    pipeline = ModelPipeline(processor=processor)
    pipeline.train(X_train, y_train, X_train, y_train) 
    
    # Predict using the data
    preds = pipeline.predict(X_pred)
    
    # Assert we got a valid prediction
    assert len(preds) == 1
    assert isinstance(preds[0], (float, np.float32, np.float64))
    
    # Clean up created files if any
    if os.path.exists("models/f1_pipeline.joblib"):
        os.remove("models/f1_pipeline.joblib")
    if os.path.exists("models/f1_pipeline_torch.pth"):
        os.remove("models/f1_pipeline_torch.pth")
