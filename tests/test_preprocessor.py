import pandas as pd
import pytest
import numpy as np
from f1_predictor.preprocessor import FeatureProcessor

def test_feature_processor_basic():
    # Create sample data with at least enough history for a default processor (time_steps=5)
    data = []
    # Using 12 rounds to get more variance
    for rnd in range(1, 13):
        # Varying positions slightly to avoid perfect integers after scaling if possible,
        # but standard scaler will often produce -1, 0, 1 for simple cases.
        pos_ver = 1 if rnd % 3 != 0 else 2
        pos_ham = 2 if rnd % 3 != 0 else 3
        data.extend([
            {
                'Year': 2024, 'RoundNumber': rnd, 'Abbreviation': 'VER', 'TeamName': 'Red Bull', 
                'Position': pos_ver, 'QualifyingPosition': pos_ver, 'GridPosition': pos_ver, 'EventName': f'Race {rnd}',
                'Status': 'Finished', 'QDelta': 0.0
            },
            {
                'Year': 2024, 'RoundNumber': rnd, 'Abbreviation': 'HAM', 'TeamName': 'Mercedes', 
                'Position': pos_ham, 'QualifyingPosition': pos_ham, 'GridPosition': pos_ham, 'EventName': f'Race {rnd}',
                'Status': 'Finished', 'QDelta': 0.15
            },
        ])
    df = pd.DataFrame(data)
    
    time_steps = 3
    processor = FeatureProcessor(time_steps=time_steps)
    processor.fit(df)
    X, y = processor.transform(df)
    
    # 2 drivers * (12 races - 3 timesteps) = 18 sequences
    assert X.shape == (18, time_steps, len(processor.feature_cols))
    assert y.shape == (18,)
    
    # Verify scaling: Numerical features should have mean approx 0 and std approx 1
    # Numerical indices are 0 to 11
    for i in range(12):
        feat_slice = X[:, :, i]
        mean = feat_slice.mean()
        std = feat_slice.std()
        assert abs(mean) < 1.0
        # If all values were same, std is 0, but here they vary
        # TrackCluster (8), AirTemp (10), Rainfall (11) are constant in this test data
        if i not in [4, 6, 8, 10, 11]: 
             assert std > 0
        
    # Verify categorical IDs are integers
    # Categorical indices start at 12
    for i in range(12, 15):
        feat_slice = X[:, :, i]
        assert np.all(np.equal(np.mod(feat_slice, 1), 0))

def test_mechanical_dnf_flag():
    df = pd.DataFrame([
        {'Year': 2024, 'RoundNumber': 1, 'Abbreviation': 'VER', 'TeamName': 'RB', 'Position': 1, 'QualifyingPosition': 1, 'GridPosition': 1, 'EventName': 'E1', 'Status': 'Engine'},
        {'Year': 2024, 'RoundNumber': 2, 'Abbreviation': 'VER', 'TeamName': 'RB', 'Position': 20, 'QualifyingPosition': 1, 'GridPosition': 1, 'EventName': 'E2', 'Status': 'Accident'},
        {'Year': 2024, 'RoundNumber': 3, 'Abbreviation': 'VER', 'TeamName': 'RB', 'Position': 2, 'QualifyingPosition': 1, 'GridPosition': 1, 'EventName': 'E3', 'Status': 'Finished'},
        {'Year': 2024, 'RoundNumber': 4, 'Abbreviation': 'VER', 'TeamName': 'RB', 'Position': 3, 'QualifyingPosition': 1, 'GridPosition': 1, 'EventName': 'E4', 'Status': '+1 Lap'},
    ])
    processor = FeatureProcessor()
    processed = processor._preprocess_raw_df(df)
    
    assert processed.loc[0, 'is_mechanical_dnf'] == 1 # Engine
    assert processed.loc[1, 'is_mechanical_dnf'] == 0 # Accident
    assert processed.loc[2, 'is_mechanical_dnf'] == 0 # Finished
    assert processed.loc[3, 'is_mechanical_dnf'] == 0 # +1 Lap

def test_qdelta_imputation():
    df = pd.DataFrame([
        {'Abbreviation': 'A', 'QDelta': 0.1, 'Year': 2024, 'RoundNumber': 1, 'EventName': 'E1'},
        {'Abbreviation': 'B', 'QDelta': 0.5, 'Year': 2024, 'RoundNumber': 1, 'EventName': 'E1'},
        {'Abbreviation': 'C', 'QDelta': np.nan, 'Year': 2024, 'RoundNumber': 1, 'EventName': 'E1'},
    ])
    processor = FeatureProcessor()
    processed = processor._preprocess_raw_df(df)
    
    assert processed.loc[2, 'QDelta'] > 0.5 # Should be filled with something higher than max
