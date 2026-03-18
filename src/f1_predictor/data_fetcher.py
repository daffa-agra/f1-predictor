import fastf1
import pandas as pd
import os
import time
import functools
from pathlib import Path

# Set up caching
CACHE_DIR = "data/cache"
os.makedirs(CACHE_DIR, exist_ok=True)
fastf1.Cache.enable_cache(CACHE_DIR)

def save_historical_data(df, path):
    """Save historical data to CSV without duplicates."""
    if df.empty:
        return
    
    path = Path(path)
    os.makedirs(path.parent, exist_ok=True)
    
    # Drop duplicates based on Year, RoundNumber, and DriverNumber
    # This ensures we don't have multiple entries for the same driver in the same race
    df_clean = df.drop_duplicates(subset=['Year', 'RoundNumber', 'DriverNumber'])
    
    # Sort for consistency: Year, RoundNumber, then Position
    # Handle cases where Position might be NaN (e.g., if data is incomplete)
    df_clean = df_clean.sort_values(['Year', 'RoundNumber', 'Position'], ascending=[True, True, True])
    
    df_clean.to_csv(path, index=False)
    print(f"Saved {len(df_clean)} records to {path}")

def retry_api_call(max_retries=3, delay=2, backoff=2):
    """Decorator to retry API calls with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries == max_retries:
                        print(f"Failed {func.__name__} after {max_retries} attempts: {e}")
                        raise e
                    print(f"Error in {func.__name__}: {e}. Retrying in {current_delay}s... ({retries}/{max_retries})")
                    time.sleep(current_delay)
                    current_delay *= backoff
            return func(*args, **kwargs)
        return wrapper
    return decorator

@retry_api_call()
def fetch_race_results(year, round_num):
    """Fetch race results for a specific year and round."""
    try:
        session = fastf1.get_session(year, round_num, 'R')
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        results = session.results
        # Select relevant columns
        cols = ['DriverNumber', 'BroadcastName', 'Abbreviation', 'TeamName', 'Position', 'GridPosition', 'Points', 'Status']
        df = results[cols].copy()
        df['Year'] = year
        df['RoundNumber'] = round_num
        df['EventName'] = session.event['EventName']
        return df
    except Exception as e:
        print(f"Error fetching race results for {year} Round {round_num}: {e}")
        return pd.DataFrame()

@retry_api_call()
def fetch_qualifying_results(year, round_num):
    """Fetch qualifying results for a specific year and round."""
    try:
        session = fastf1.get_session(year, round_num, 'Q')
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        results = session.results
        cols = ['DriverNumber', 'Position', 'Q1', 'Q2', 'Q3']
        df = results[cols].copy()
        df = df.rename(columns={'Position': 'QualifyingPosition'})
        df['Year'] = year
        df['RoundNumber'] = round_num
        return df
    except Exception as e:
        print(f"Error fetching qualifying results for {year} Round {round_num}: {e}")
        return pd.DataFrame()

@retry_api_call()
def fetch_season_data(year):
    """Fetch all race and qualifying data for a given season."""
    schedule = fastf1.get_event_schedule(year)
    # Filter for real races (exclude testing)
    races = schedule[schedule['EventFormat'] != 'testing']
    
    all_results = []
    for _, race in races.iterrows():
        round_num = race['RoundNumber']
        print(f"Fetching data for {year} Round {round_num}: {race['EventName']}")
        
        race_df = fetch_race_results(year, round_num)
        qual_df = fetch_qualifying_results(year, round_num)
        
        if not race_df.empty and not qual_df.empty:
            # Merge race and qualifying data
            merged = pd.merge(race_df, qual_df[['DriverNumber', 'QualifyingPosition']], on='DriverNumber', how='left')
            all_results.append(merged)
            
    if all_results:
        return pd.concat(all_results, ignore_index=True)
    return pd.DataFrame()

def fetch_historical_data(start_year=2018, end_year=2025):
    """Fetch historical data for multiple seasons and save to CSV, fetching only missing years."""
    generic_path = Path("data/historical_data.csv")
    legacy_path = Path(f"data/historical_data_{start_year}_{end_year}.csv")
    
    existing_df = pd.DataFrame()
    
    # Try to load existing data
    if generic_path.exists():
        print(f"Loading historical data from {generic_path}")
        existing_df = pd.read_csv(generic_path)
    elif legacy_path.exists():
        print(f"Loading historical data from legacy {legacy_path}")
        existing_df = pd.read_csv(legacy_path)
    
    # Identify which years we already have
    if not existing_df.empty and 'Year' in existing_df.columns:
        existing_years = set(existing_df['Year'].unique())
    else:
        existing_years = set()
    
    # Determine which years are missing from the requested range
    requested_years = set(range(start_year, end_year + 1))
    missing_years = sorted(list(requested_years - existing_years))
    
    if not missing_years:
        print(f"All requested years ({start_year}-{end_year}) are already present in cache.")
    else:
        print(f"Fetching data for missing years: {missing_years}")
        new_dfs = []
        for year in missing_years:
            print(f"--- Fetching Season {year} ---")
            df = fetch_season_data(year)
            if not df.empty:
                new_dfs.append(df)
            else:
                print(f"Warning: No data fetched for {year}")
        
        if new_dfs:
            # Combine existing and new data
            all_dfs = [existing_df] if not existing_df.empty else []
            all_dfs.extend(new_dfs)
            existing_df = pd.concat(all_dfs, ignore_index=True)
            
            # Save the accumulated data to the generic path
            save_historical_data(existing_df, generic_path)
            
            # If we were using the legacy path and it's different, maybe update it?
            # Actually, the requirement says "Use a consistent naming convention or a primary data/historical_data.csv"
            # So we'll stick to data/historical_data.csv.
    
    # Filter and return the requested range
    if not existing_df.empty:
        return existing_df[(existing_df['Year'] >= start_year) & (existing_df['Year'] <= end_year)].copy()
    
    return pd.DataFrame()

if __name__ == "__main__":
    # Test fetch for 2025 (latest complete season)
    df = fetch_historical_data(2025, 2025)
    print(df.head())
