import pandas as pd
import pytest
from f1_predictor.preprocessor import FeatureProcessor

@pytest.fixture
def sample_df():
    return pd.DataFrame({
        'Year': [2024, 2024, 2024, 2024, 2024, 2024],
        'RoundNumber': [1, 1, 2, 2, 3, 3],
        'Abbreviation': ['VER', 'HAM', 'VER', 'HAM', 'VER', 'HAM'],
        'TeamName': ['Red Bull', 'Mercedes', 'Red Bull', 'Mercedes', 'Red Bull', 'Mercedes'],
        'Position': [1, 2, 1, 3, 2, 1],
        'QualifyingPosition': [1, 2, 2, 1, 1, 2],
        'GridPosition': [1, 2, 2, 1, 1, 2],
        'EventName': ['Bahrain GP', 'Bahrain GP', 'Saudi GP', 'Saudi GP', 'Austrian GP', 'Austrian GP']
    })

def test_feature_processor_fit_transform(sample_df):
    processor = FeatureProcessor()
    processor.fit(sample_df)
    X, y = processor.transform(sample_df)
    
    assert len(X) == 6
    assert 'DriverAvgFinish' in X.columns
    # VER's first race should use global mean (baseline) for shift(1)
    assert X.iloc[0]['DriverAvgFinish'] == sample_df['Position'].mean()
    # VER's second race (Round 2) should use Round 1 result (1)
    assert X.iloc[2]['DriverAvgFinish'] == 1.0
    # VER's third race (Round 3) should use avg of Round 1 (1) and Round 2 (1)
    assert X.iloc[4]['DriverAvgFinish'] == 1.0

def test_feature_processor_no_leakage(sample_df):
    processor = FeatureProcessor()
    processor.fit(sample_df)
    X, y = processor.transform(sample_df)
    
    # Check that for VER Round 3, the DriverAvgFinish does NOT include his Round 3 result (2)
    # Correct avg of R1(1) and R2(1) is 1.0. If leakage, it would be (1+1+2)/3 = 1.33
    assert X.iloc[4]['DriverAvgFinish'] == 1.0

def test_transform_for_prediction(sample_df):
    processor = FeatureProcessor()
    processor.fit(sample_df)
    
    race_df = pd.DataFrame({
        'Abbreviation': ['VER', 'HAM'],
        'TeamName': ['Red Bull', 'Mercedes'],
        'QualifyingPosition': [1, 2],
        'EventName': ['Miami GP', 'Miami GP']
    })
    
    # Test with internal baselines
    X_pred = processor.transform_for_prediction(race_df)
    
    assert len(X_pred) == 2
    # VER's predicted avg finish should be avg of his historical results (1, 1, 2) -> 1.33
    assert pytest.approx(X_pred.iloc[0]['DriverAvgFinish'], 0.01) == 1.33
    
    # Test with external baselines passing
    X_pred_ext = processor.transform_for_prediction(race_df, external_baselines=processor.baselines)
    assert len(X_pred_ext) == 2
    assert X_pred_ext.iloc[0]['DriverAvgFinish'] == X_pred.iloc[0]['DriverAvgFinish']
