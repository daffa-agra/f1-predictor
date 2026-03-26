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
        session.load(laps=False, telemetry=False, weather=True, messages=False)
        results = session.results
        # Select relevant columns
        cols = ['DriverNumber', 'BroadcastName', 'Abbreviation', 'TeamName', 'Position', 'GridPosition', 'Points', 'Status']
        df = results[cols].copy()
        df['Year'] = year
        df['RoundNumber'] = round_num
        df['EventName'] = session.event['EventName']
        
        # Add weather data
        weather = session.weather_data
        if not weather.empty:
            df['AirTemp'] = weather['AirTemp'].mean()
            df['Rainfall'] = 1 if weather['Rainfall'].any() else 0
        else:
            df['AirTemp'] = 25.0 # Default
            df['Rainfall'] = 0
            
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
        
        # Calculate QDelta
        # FastF1 returns Q1, Q2, Q3 as pd.Timedelta
        q_cols = ['Q1', 'Q2', 'Q3']
        for col in q_cols:
            df[col] = pd.to_timedelta(df[col])
            
        # Get best time for each driver in seconds
        driver_best = df[q_cols].min(axis=1).dt.total_seconds()
        # Session best time is the minimum across all drivers
        session_best = driver_best.min()
        
        if pd.notna(session_best) and session_best > 0:
            df['QDelta'] = (driver_best - session_best) / session_best
        else:
            df['QDelta'] = pd.NA
            
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
            merged = pd.merge(race_df, qual_df[['DriverNumber', 'QualifyingPosition', 'QDelta']], on='DriverNumber', how='left')
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

def fetch_2026_stats():
    """Fetch all race results for the year 2026 that have already occurred."""
    schedule = fastf1.get_event_schedule(2026)
    # Filter for real races (exclude testing)
    races = schedule[schedule['EventFormat'] != 'testing']
    
    # Use current time to find completed races
    # FastF1 schedule dates are usually aware UTC.
    # To be safe, we use naive UTC comparison.
    now = pd.Timestamp.now(tz='UTC').tz_localize(None)
    
    all_results = []
    for _, race in races.iterrows():
        # Session5Date is typically the race session date
        race_date = race['Session5Date']
        if pd.notna(race_date):
            # Ensure race_date is naive UTC for comparison
            if race_date.tzinfo is not None:
                race_date_cmp = race_date.tz_convert('UTC').tz_localize(None)
            else:
                race_date_cmp = race_date
                
            if race_date_cmp < now:
                round_num = race['RoundNumber']
                print(f"Fetching 2026 Round {round_num}: {race['EventName']}")
                race_df = fetch_race_results(2026, round_num)
                qual_df = fetch_qualifying_results(2026, round_num)
                
                if not race_df.empty and not qual_df.empty:
                    merged = pd.merge(race_df, qual_df[['DriverNumber', 'QualifyingPosition', 'QDelta']], on='DriverNumber', how='left')
                    all_results.append(merged)
                elif not race_df.empty:
                    all_results.append(race_df)
    
    if all_results:
        return pd.concat(all_results, ignore_index=True)
    
    # Return empty DataFrame with the same columns as fetch_race_results
    cols = ['DriverNumber', 'BroadcastName', 'Abbreviation', 'TeamName', 'Position', 'GridPosition', 'Points', 'Status', 'Year', 'RoundNumber', 'EventName']
    return pd.DataFrame(columns=cols)

if __name__ == "__main__":
    # Test fetch for 2025 (latest complete season)
    df = fetch_historical_data(2025, 2025)
    print("--- 2025 Historical Data ---")
    print(df.head())
    
    # Test fetch for 2026
    print("\n--- 2026 Stats ---")
    df_2026 = fetch_2026_stats()
    print(df_2026.head())
