import pandas as pd
import pytest
import numpy as np
from f1_predictor.preprocessor import FeatureProcessor

def test_feature_processor_basic():
    # Create sample data with at least enough history for a default processor (time_steps=5)
    data = []
    for rnd in range(1, 8):
        data.extend([
            {'Year': 2024, 'RoundNumber': rnd, 'Abbreviation': 'VER', 'TeamName': 'Red Bull', 'Position': 1, 'QualifyingPosition': 1, 'GridPosition': 1, 'EventName': f'Race {rnd}'},
            {'Year': 2024, 'RoundNumber': rnd, 'Abbreviation': 'HAM', 'TeamName': 'Mercedes', 'Position': 2, 'QualifyingPosition': 2, 'GridPosition': 2, 'EventName': f'Race {rnd}'},
        ])
    df = pd.DataFrame(data)
    
    processor = FeatureProcessor(time_steps=5)
    processor.fit(df)
    X, y = processor.transform(df)
    
    # Assertions
    # 2 drivers * (7 races - 5 timesteps) = 4 sequences
    assert X.shape == (4, 5, len(processor.feature_cols))
    assert y.shape == (4,)
    assert y[0] in [1, 2] # VER or HAM 6th race
