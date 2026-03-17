import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from f1_predictor.data_fetcher import fetch_race_results

@patch('fastf1.get_session')
def test_fetch_race_results_success(mock_get_session):
    # Mock the fastf1 session and results
    mock_session = MagicMock()
    mock_results = pd.DataFrame({
        'DriverNumber': ['1', '44'],
        'BroadcastName': ['M. VERSTAPPEN', 'L. HAMILTON'],
        'Abbreviation': ['VER', 'HAM'],
        'TeamName': ['Red Bull Racing', 'Mercedes'],
        'Position': [1.0, 2.0],
        'GridPosition': [1.0, 2.0],
        'Points': [25.0, 18.0],
        'Status': ['Finished', 'Finished']
    })
    mock_session.results = mock_results
    mock_session.event = {'EventName': 'Bahrain Grand Prix'}
    mock_get_session.return_value = mock_session
    
    # Call the function
    df = fetch_race_results(2025, 1)
    
    # Assertions
    assert not df.empty
    assert len(df) == 2
    assert df.iloc[0]['BroadcastName'] == 'M. VERSTAPPEN'
    assert df.iloc[0]['EventName'] == 'Bahrain Grand Prix'

@patch('fastf1.get_session')
def test_fetch_race_results_failure(mock_get_session):
    # Mock a failure
    mock_get_session.side_effect = Exception("API Error")
    
    df = fetch_race_results(2025, 1)
    
    assert df.empty
