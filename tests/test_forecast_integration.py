import pytest
import json
import os
import pandas as pd
from unittest.mock import patch, MagicMock
from forecast_2026 import create_forecast

@pytest.fixture
def mock_drivers_json():
    # Return a sample drivers dictionary
    return {
        "VERSTAPPEN": {"no": "3", "nat": "NED", "team": "Red Bull Racing"},
        "HAMILTON": {"no": "44", "nat": "GBR", "team": "Ferrari"},
        "NORRIS": {"no": "1", "nat": "GBR", "team": "McLaren"}
    }

@pytest.fixture
def mock_schedule():
    # Return a dummy schedule for 2026
    data = {
        'EventName': ['Bahrain Grand Prix', 'Saudi Arabian Grand Prix'],
        'EventFormat': ['conventional', 'conventional'],
        'Session5Date': [
            pd.Timestamp('2026-03-20', tz='UTC'),
            pd.Timestamp('2026-03-27', tz='UTC')
        ],
        'RoundNumber': [1, 2]
    }
    return pd.DataFrame(data)

@pytest.fixture
def mock_pipeline():
    # Mock a pipeline object that returns predictable predictions
    pipeline = MagicMock()
    # Mock FeatureProcessor
    processor = MagicMock()
    # transform_for_prediction returns a DF with the right number of rows
    def mock_transform(df, baselines=None):
        return pd.DataFrame({'dummy': [0] * len(df)})
    processor.transform_for_prediction.side_effect = mock_transform
    pipeline.processor = processor
    
    # Mock XGBRegressor
    model = MagicMock()
    # model.predict returns a list of positions
    def mock_predict(X):
        # Return a list of positions from 1.0 upwards
        return [float(i+1) for i in range(len(X))]
    model.predict.side_effect = mock_predict
    pipeline.model = model
    pipeline.baselines = {}
    
    return pipeline

@patch('forecast_2026.os.path.exists')
@patch('forecast_2026.ModelPipeline.load')
@patch('forecast_2026.fetch_2026_stats')
@patch('forecast_2026.fastf1.get_event_schedule')
@patch('forecast_2026.pd.Timestamp.now')
def test_forecast_empty_stats(mock_now, mock_get_schedule, mock_fetch_stats, mock_load_pipeline, mock_exists, mock_schedule, mock_pipeline):
    """Test forecast when no 2026 races have occurred yet."""
    mock_exists.return_value = True
    mock_load_pipeline.return_value = mock_pipeline
    mock_fetch_stats.return_value = pd.DataFrame() # Empty 2026 stats
    mock_get_schedule.return_value = mock_schedule
    # Set 'now' to before the first race
    mock_now.return_value = pd.Timestamp('2026-03-10', tz='UTC')
    
    # Run the forecast
    create_forecast()
    
    # Verify the output file
    assert os.path.exists("website/forecast.json")
    with open("website/forecast.json", "r") as f:
        data = json.load(f)
        
    assert data['event'] == 'Bahrain Grand Prix'
    assert data['is_preliminary'] is True
    assert len(data['top_10']) > 0
    # Since we have 3 drivers in our mock_drivers_json (if we mock open)
    # Actually create_forecast loads from config/drivers_2026.json
    # I should check how many drivers are there and ensure they are present.
    
@patch('forecast_2026.os.path.exists')
@patch('forecast_2026.ModelPipeline.load')
@patch('forecast_2026.fetch_2026_stats')
@patch('forecast_2026.fastf1.get_event_schedule')
@patch('forecast_2026.pd.Timestamp.now')
def test_forecast_with_stats(mock_now, mock_get_schedule, mock_fetch_stats, mock_load_pipeline, mock_exists, mock_schedule, mock_pipeline):
    """Test forecast when some 2026 races have occurred."""
    mock_exists.return_value = True
    mock_load_pipeline.return_value = mock_pipeline
    
    # Mock some 2026 results
    mock_results = pd.DataFrame({
        'BroadcastName': ['M. Verstappen', 'L. Hamilton'],
        'Abbreviation': ['VER', 'HAM'],
        'GridPosition': [1.0, 3.0],
        'Position': [1, 2],
        'Year': [2026, 2026],
        'RoundNumber': [1, 1]
    })
    mock_fetch_stats.return_value = mock_results
    mock_get_schedule.return_value = mock_schedule
    # Set 'now' to after the first race but before the second
    mock_now.return_value = pd.Timestamp('2026-03-25', tz='UTC')
    
    # Run the forecast
    create_forecast()
    
    # Verify the output file
    assert os.path.exists("website/forecast.json")
    with open("website/forecast.json", "r") as f:
        data = json.load(f)
        
    assert data['event'] == 'Saudi Arabian Grand Prix'
    assert data['is_preliminary'] is True
    assert len(data['top_10']) > 0

def test_forecast_format_verification():
    """Verify that the generated JSON matches the expected structure."""
    if not os.path.exists("website/forecast.json"):
        pytest.skip("forecast.json not found")
        
    with open("website/forecast.json", "r") as f:
        data = json.load(f)
        
    required_keys = ['event', 'date', 'is_preliminary', 'top_10']
    for key in required_keys:
        assert key in data
        
    assert isinstance(data['top_10'], list)
    if len(data['top_10']) > 0:
        driver = data['top_10'][0]
        assert 'name' in driver
        assert 'prediction' in driver
        assert 'number' in driver
        assert 'nationality' in driver
        assert 'team' in driver
