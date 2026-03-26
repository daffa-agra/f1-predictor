import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from f1_predictor.data_fetcher import fetch_race_results, fetch_qualifying_results, fetch_season_data

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
    assert 'Status' in df.columns

@patch('fastf1.get_session')
def test_fetch_qualifying_results_success(mock_get_session):
    # Mock qualifying results with Timedeltas
    mock_session = MagicMock()
    mock_results = pd.DataFrame({
        'DriverNumber': ['1', '44'],
        'Position': [1.0, 2.0],
        'Q1': [pd.Timedelta(seconds=90.0), pd.Timedelta(seconds=91.0)],
        'Q2': [pd.Timedelta(seconds=89.0), pd.Timedelta(seconds=90.0)],
        'Q3': [pd.Timedelta(seconds=88.0), pd.Timedelta(seconds=89.0)]
    })
    mock_session.results = mock_results
    mock_get_session.return_value = mock_session
    
    df = fetch_qualifying_results(2025, 1)
    
    assert not df.empty
    assert 'QDelta' in df.columns
    # Driver 1 best: 88.0, Session best: 88.0 -> QDelta: 0.0
    # Driver 44 best: 89.0 -> QDelta: (89-88)/88 = 1/88 approx 0.01136
    assert df.loc[df['DriverNumber'] == '1', 'QDelta'].iloc[0] == 0.0
    assert abs(df.loc[df['DriverNumber'] == '44', 'QDelta'].iloc[0] - (1/88)) < 1e-6

@patch('f1_predictor.data_fetcher.fetch_qualifying_results')
@patch('f1_predictor.data_fetcher.fetch_race_results')
@patch('fastf1.get_event_schedule')
def test_fetch_season_data(mock_schedule, mock_fetch_race, mock_fetch_qual):
    # Mock schedule
    mock_schedule.return_value = pd.DataFrame({
        'RoundNumber': [1],
        'EventName': ['Bahrain Grand Prix'],
        'EventFormat': ['conventional']
    })
    
    # Mock race results
    mock_fetch_race.return_value = pd.DataFrame({
        'DriverNumber': ['1', '44'],
        'Position': [1.0, 2.0],
        'Status': ['Finished', 'Finished']
    })
    
    # Mock qual results
    mock_fetch_qual.return_value = pd.DataFrame({
        'DriverNumber': ['1', '44'],
        'QualifyingPosition': [1.0, 2.0],
        'QDelta': [0.0, 0.01]
    })
    
    df = fetch_season_data(2025)
    
    assert not df.empty
    assert 'QDelta' in df.columns
    assert 'QualifyingPosition' in df.columns
    assert 'Status' in df.columns

@patch('fastf1.get_session')
def test_fetch_race_results_failure(mock_get_session):
    # Mock a failure
    mock_get_session.side_effect = Exception("API Error")
    
    df = fetch_race_results(2025, 1)
    
    assert df.empty
