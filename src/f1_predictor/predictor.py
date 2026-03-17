import pandas as pd
import numpy as np
import os
import argparse
import json
from datetime import datetime

def export_json(results_df, event_name):
    """Export top 10 predictions to JSON for the website."""
    top_10 = results_df.head(10)
    data = {
        "event": event_name,
        "date": datetime.now().strftime("%B %d, %Y"),
        "top_10": []
    }
    for _, row in top_10.iterrows():
        data["top_10"].append({
            "name": row.get('BroadcastName', f"Driver {row['DriverNumber']}"),
            "prediction": float(row['PredictedPosition'])
        })
    
    os.makedirs("website", exist_ok=True)
    with open("website/predictions.json", "w") as f:
        json.dump(data, f, indent=4)
    print("Exported results to website/predictions.json")
from f1_predictor.data_fetcher import fetch_season_data, fetch_historical_data, fetch_race_results, fetch_qualifying_results
from f1_predictor.preprocessor import FeatureProcessor
from f1_predictor.model import ModelPipeline
import fastf1
from sklearn.model_selection import train_test_split

def predict_upcoming_race(year, round_num=None):
    """Predict the winner for the next (or specific) race in the season."""
    if round_num is None:
        # Get the next upcoming race
        schedule = fastf1.get_event_schedule(year)
        now = pd.Timestamp.now().tz_localize(None)
        # Session5DateUtc is usually the race date
        upcoming = schedule[schedule['Session5DateUtc'].dt.tz_localize(None) > now]
        if upcoming.empty:
            print(f"No upcoming races found for the {year} season.")
            return
        race = upcoming.iloc[0]
        round_num = race['RoundNumber']
        event_name = race['EventName']
    else:
        schedule = fastf1.get_event_schedule(year)
        race = schedule[schedule['RoundNumber'] == round_num]
        if race.empty:
            print(f"Round {round_num} not found in {year} schedule.")
            return
        race = race.iloc[0]
        event_name = race['EventName']

    print(f"Predicting results for {year} Round {round_num}: {event_name}")
    
    # Load model pipeline
    try:
        pipeline = ModelPipeline.load()
        processor = pipeline.processor
        model = pipeline.model
    except Exception as e:
        print(f"Error loading model: {e}")
        print("Please train the model first using --train.")
        return

    # Fetch qualifying data for the race
    qual_df = fetch_qualifying_results(year, round_num)
    if qual_df.empty:
        print(f"Qualifying data for {event_name} not available yet.")
        return

    # Enrich qual_df with BroadcastName and Abbreviation/Team if missing
    try:
        session = fastf1.get_session(year, round_num, 'Q')
        session.load(laps=False, telemetry=False, weather=False, messages=False)
        results = session.results[['DriverNumber', 'BroadcastName', 'Abbreviation', 'TeamName']]
        qual_df = pd.merge(qual_df, results, on='DriverNumber', how='left')
    except Exception as e:
        print(f"Warning: Could not fetch detailed driver info: {e}")
    
    # Ensure EventName is present
    qual_df['EventName'] = event_name

    # Transform for prediction using pre-calculated baselines
    X_pred = processor.transform_for_prediction(qual_df, pipeline.baselines)
    
    # Predict
    predicted_positions = model.predict(X_pred)
    
    # Map back to drivers
    results_out = qual_df.copy()
    results_out['PredictedPosition'] = predicted_positions
    results_out = results_out.sort_values('PredictedPosition')
    
    # Export for website
    export_json(results_out, event_name)
    
    print(f"\nPredicted Top 10 for {event_name}:")
    top_10 = results_out.head(10)
    for i, (_, row) in enumerate(top_10.iterrows(), 1):
        name = row.get('BroadcastName', f"Driver {row['DriverNumber']}")
        print(f"{i:2}. {name:20} (Predicted Position: {row['PredictedPosition']:.2f})")

def main():
    parser = argparse.ArgumentParser(description="F1 Race Winner Predictor")
    parser.add_argument("--train", action="store_true", help="Train the ML model on historical data")
    parser.add_argument("--predict", type=int, help="Round number to predict (defaults to next race)")
    parser.add_argument("--year", type=int, default=datetime.now().year, help="Season to predict (default current year)")
    
    args = parser.parse_args()
    
    if args.train:
        # Use a dynamic range for training
        end_train_year = datetime.now().year - 1
        start_train_year = end_train_year - 5
        print(f"Fetching historical data for training ({start_train_year}-{end_train_year})...")
        
        df = fetch_historical_data(start_train_year, end_train_year)
        if df.empty:
            print("No training data found.")
            return

        processor = FeatureProcessor()
        processor.fit(df)
        X, y = processor.transform(df)
        
        # Split for internal validation
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        pipeline = ModelPipeline(processor=processor)
        pipeline.train(X_train, y_train, X_test, y_test)
        pipeline.save()
    
    if args.predict is not None or not args.train:
        predict_upcoming_race(args.year, args.predict)

if __name__ == "__main__":
    main()
