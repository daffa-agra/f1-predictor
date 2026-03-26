import pandas as pd
import pytest
import numpy as np
from f1_predictor.preprocessor import FeatureProcessor

@pytest.fixture
def sample_df():
    data = []
    # Create 6 races for VER and HAM
    for rnd in range(1, 7):
        data.extend([
            {'Year': 2024, 'RoundNumber': rnd, 'Abbreviation': 'VER', 'TeamName': 'Red Bull', 'Position': 1 if rnd % 2 != 0 else 2, 'QualifyingPosition': 1, 'GridPosition': 1, 'EventName': f'Race {rnd}'},
            {'Year': 2024, 'RoundNumber': rnd, 'Abbreviation': 'HAM', 'TeamName': 'Mercedes', 'Position': 2 if rnd % 2 != 0 else 1, 'QualifyingPosition': 2, 'GridPosition': 2, 'EventName': f'Race {rnd}'},
        ])
    return pd.DataFrame(data)

def test_feature_processor_fit_transform(sample_df):
    processor = FeatureProcessor(time_steps=2)
    processor.fit(sample_df)
    X, y = processor.transform(sample_df)
    
    # 2 drivers * (6 races - 2 timesteps) = 8 sequences
    assert X.shape == (8, 2, len(processor.feature_cols))
    assert y.shape == (8,)

def test_transform_for_prediction(sample_df):
    processor = FeatureProcessor(time_steps=2)
    processor.fit(sample_df)
    
    race_df = pd.DataFrame({
        'Abbreviation': ['VER', 'HAM'],
        'TeamName': ['Red Bull', 'Mercedes'],
        'QualifyingPosition': [1, 2],
        'EventName': ['Race 7', 'Race 7']
    })
    
    # Pass sample_df as history
    X_pred = processor.transform_for_prediction(sample_df, race_df)
    
    assert X_pred.shape == (2, 2, len(processor.feature_cols))
    
    # Check that it uses the latest history records correctly.
    # VER last race results (R1-R6): 1, 2, 1, 2, 1, 2.
    # With shift=False and window=5, R6 row should have mean(R2-R6) = mean(2, 1, 2, 1, 2) = 1.6
    # Index of DriverAvgFinish is 2
    assert np.isclose(X_pred[0, 1, 2], 1.6)
