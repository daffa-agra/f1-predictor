import pandas as pd
import pytest
from f1_predictor.preprocessor import preprocess_data

def test_preprocess_data():
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
    
    X, y, le_driver, le_team, le_event = preprocess_data(df)
    
    # Assertions
    assert len(X) == 4
    assert len(y) == 4
    assert 'QualifyingPosition' in X.columns
    assert 'DriverAvgFinish' in X.columns
    assert y.iloc[0] == 1
    assert y.iloc[3] == 3
