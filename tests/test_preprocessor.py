import pandas as pd
import pytest
from f1_predictor.preprocessor import FeatureProcessor

def test_feature_processor_basic():
    # Create sample data
    df = pd.DataFrame({
        'Year': [2024, 2024, 2024, 2024],
        'RoundNumber': [1, 1, 2, 2],
        'Abbreviation': ['VER', 'HAM', 'VER', 'HAM'],
        'TeamName': ['Red Bull', 'Mercedes', 'Red Bull', 'Mercedes'],
        'Position': [1, 2, 1, 3],
        'QualifyingPosition': [1, 2, 2, 1],
        'GridPosition': [1, 2, 2, 1],
        'EventName': ['Bahrain GP', 'Bahrain GP', 'Saudi GP', 'Saudi GP']
    })
    
    processor = FeatureProcessor()
    processor.fit(df)
    X, y = processor.transform(df)
    
    # Assertions
    assert len(X) == 4
    assert len(y) == 4
    assert 'QualifyingPosition' in X.columns
    assert 'DriverAvgFinish' in X.columns
    assert y.iloc[0] == 1
    assert y.iloc[3] == 3
