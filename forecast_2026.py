import pandas as pd
import json
import os
from f1_predictor.model import ModelPipeline
from f1_predictor.preprocessor import FeatureProcessor
from f1_predictor.data_fetcher import fetch_2026_stats
import fastf1
from datetime import datetime

def create_forecast():
    print("Starting 2026 Forecast Generation...")
    
    # 1. Load the trained model
    pipeline_path = "models/f1_pipeline.joblib"
    if not os.path.exists(pipeline_path):
        print(f"Error: Model pipeline not found at {pipeline_path}")
        return
    pipeline = ModelPipeline.load(pipeline_path)
    print("Model loaded successfully.")

    # 2. Load 2026 driver metadata
    drivers_path = "config/drivers_2026.json"
    with open(drivers_path, "r") as f:
        drivers_2026 = json.load(f)
    print(f"Loaded {len(drivers_2026)} drivers from metadata.")

    # 3. Fetch 2026 historical results
    df_2026 = fetch_2026_stats()
    print(f"Fetched {len(df_2026)} historical records for 2026.")

    # 4. Identify the next upcoming race in 2026
    schedule = fastf1.get_event_schedule(2026)
    # Filter for real races
    races = schedule[schedule['EventFormat'] != 'testing'].copy()
    # Ensure Session5Date is datetime and UTC-aware
    races['Session5Date'] = pd.to_datetime(races['Session5Date'], utc=True)
    now = pd.Timestamp.now(tz='UTC')
    
    upcoming = races[races['Session5Date'] > now]
    if upcoming.empty:
        # If no more races in 2026, just take the last one or a placeholder
        upcoming_race = races.iloc[-1]
    else:
        upcoming_race = upcoming.iloc[0]
    
    event_name = upcoming_race['EventName']
    # Format date: "March 19, 2026"
    event_date = upcoming_race['Session5Date'].strftime("%B %d, %Y")
    print(f"Target Event: {event_name} on {event_date}")

    # 5. Create forecast_df
    forecast_rows = []
    for name_key, meta in drivers_2026.items():
        # Calculate Grid Proxy
        # Match driver in df_2026 using name_key (e.g. "VERSTAPPEN")
        if not df_2026.empty:
            driver_stats = df_2026[df_2026['BroadcastName'].str.contains(name_key, case=False)]
            if not driver_stats.empty:
                grid_proxy = driver_stats['GridPosition'].mean()
                # Use real abbreviation if found
                abbr = driver_stats['Abbreviation'].iloc[0]
            else:
                grid_proxy = 20.0
                abbr = name_key[:3].upper() # Fallback to first 3 letters
        else:
            grid_proxy = 20.0
            abbr = name_key[:3].upper()

        forecast_rows.append({
            'Abbreviation': abbr,
            'TeamName': meta['team'],
            'QualifyingPosition': grid_proxy,
            'GridPosition': grid_proxy,
            'EventName': event_name,
            'BroadcastName': f"M. {name_key.capitalize()}", # For display
            'DriverNumber': meta['no'],
            'Nationality': meta['nat']
        })
    
    forecast_df = pd.DataFrame(forecast_rows)
    print("Forecast DataFrame prepared with Grid Proxies.")

    # 6. Transform for prediction
    X_pred = pipeline.processor.transform_for_prediction(forecast_df, pipeline.baselines)
    
    # 7. Run model to get PredictedPosition
    predictions = pipeline.model.predict(X_pred)
    forecast_df['PredictedPosition'] = predictions
    
    # 8. Export top 10 results
    forecast_df = forecast_df.sort_values('PredictedPosition')
    top_10_df = forecast_df.head(10)
    
    output_data = {
        "event": event_name,
        "date": event_date,
        "is_preliminary": True,
        "top_10": []
    }
    
    for _, row in top_10_df.iterrows():
        output_data["top_10"].append({
            "name": row['BroadcastName'].upper(),
            "prediction": float(row['PredictedPosition']),
            "number": row['DriverNumber'],
            "nationality": row['Nationality'],
            "team": row['TeamName']
        })
    
    # Ensure website directory exists
    os.makedirs("website", exist_ok=True)
    with open("website/forecast.json", "w") as f:
        json.dump(output_data, f, indent=4)
    
    print(f"Forecast exported to website/forecast.json")
    print("\nTop 10 Forecast:")
    for i, item in enumerate(output_data["top_10"], 1):
        print(f"{i:2}. {item['name']:20} ({item['team']}) - Predicted: {item['prediction']:.2f}")

if __name__ == "__main__":
    create_forecast()
