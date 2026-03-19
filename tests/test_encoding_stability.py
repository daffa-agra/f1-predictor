import pandas as pd
import numpy as np
import pytest
from f1_predictor.preprocessor import FeatureProcessor
from f1_predictor.model import ModelPipeline

@pytest.fixture
def historical_df():
    """Mock historical data for fitting the processor."""
    return pd.DataFrame({
        'Year': [2024, 2024, 2024, 2024],
        'RoundNumber': [1, 1, 2, 2],
        'Abbreviation': ['VER', 'HAM', 'VER', 'HAM'],
        'TeamName': ['Red Bull', 'Mercedes', 'Red Bull', 'Mercedes'],
        'Position': [1, 2, 1, 3],
        'QualifyingPosition': [1, 2, 2, 1],
        'GridPosition': [1, 2, 2, 1],
        'EventName': ['Bahrain GP', 'Bahrain GP', 'Saudi GP', 'Saudi GP']
    })

def test_encoding_stability_unseen_data(historical_df):
    """
    Ensure the FeatureProcessor handles unknown categorical data by encoding them as -1,
    and verify the ModelPipeline can still produce predictions from such data.
    """
    processor = FeatureProcessor()
    processor.fit(historical_df)
    
    # Create prediction data with UNSEEN driver, team, and event
    prediction_df = pd.DataFrame({
        'Abbreviation': ['COL'],      # Unseen driver (Colapinto)
        'TeamName': ['Williams'],      # Unseen team
        'QualifyingPosition': [15],
        'GridPosition': [15],
        'EventName': ['Azerbaijan GP'] # Unseen event
    })
    
    # 1. Transform for prediction
    X_pred = processor.transform_for_prediction(prediction_df)
    
    # 2. Assert unseen categorical entries are encoded as -1
    # OrdinalEncoder handle_unknown='use_encoded_value' with unknown_value=-1
    assert X_pred.iloc[0]['DriverID'] == -1
    assert X_pred.iloc[0]['TeamID'] == -1
    assert X_pred.iloc[0]['EventID'] == -1
    
    # 3. Assert baseline statistics use global mean for unseen entries
    global_mean = historical_df['Position'].mean() # (1+2+1+3)/4 = 1.75
    assert X_pred.iloc[0]['DriverAvgFinish'] == global_mean
    assert X_pred.iloc[0]['TeamAvgFinish'] == global_mean
    assert X_pred.iloc[0]['EventAvgFinish'] == global_mean

    # 4. Verify the rest of the pipeline functions even with these -1 encodings
    # Fit processor and prepare training data
    X_train, y_train = processor.transform(historical_df)
    
    # Initialize and train ModelPipeline
    pipeline = ModelPipeline(processor=processor)
    # Using same data for testing as training just to verify functionality
    pipeline.train(X_train, y_train, X_train, y_train) 
    
    # Predict using the data with -1 encodings
    preds = pipeline.predict(X_pred)
    
    # Assert we got a valid prediction
    assert len(preds) == 1
    assert isinstance(preds[0], (float, np.float32))
    # It should be a reasonable value (around the training range)
    assert 1.0 <= preds[0] <= 20.0
