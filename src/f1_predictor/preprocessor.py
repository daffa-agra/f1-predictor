import pandas as pd
import numpy as np
from sklearn.preprocessing import OrdinalEncoder

class FeatureProcessor:
    """Stateful feature engineering pipeline for F1 race prediction."""
    
    def __init__(self, time_steps=5):
        self.le_driver = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
        self.le_team = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
        self.le_event = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
        self.baselines = {}
        self.is_fitted = False
        self.time_steps = time_steps
        self.feature_cols = [
            'QualifyingPosition', 'GridPosition', 'DriverAvgFinish', 
            'TeamAvgFinish', 'EventAvgFinish', 'DriverID', 'TeamID', 'EventID'
        ]

    def fit(self, df):
        """Fit encoders and calculate historical baseline statistics."""
        # Ensure data is sorted for temporal calculations
        df = df.sort_values(['Year', 'RoundNumber'])
        
        # Fit OrdinalEncoders (requires 2D input)
        self.le_driver.fit(df[['Abbreviation']].drop_duplicates().values)
        self.le_team.fit(df[['TeamName']].drop_duplicates().values)
        self.le_event.fit(df[['EventName']].drop_duplicates().values)
        
        # Calculate global baselines (using only historical data) for imputation
        self.baselines['global_mean'] = df['Position'].mean()
        self.baselines['driver_means'] = df.groupby('Abbreviation')['Position'].mean().to_dict()
        self.baselines['team_means'] = df.groupby('TeamName')['Position'].mean().to_dict()
        
        self.is_fitted = True
        return self

    def _calculate_rolling_features(self, df):
        """Calculate rolling averages with a shift to avoid data leakage."""
        df = df.copy()
        df = df.sort_values(['Year', 'RoundNumber'])
        
        # 1. Driver rolling performance (avg finish position in last 5 races)
        # We shift by 1 to only use data from previous races for the current race prediction
        df['DriverAvgFinish'] = df.groupby('Abbreviation')['Position'].transform(
            lambda x: x.rolling(window=5, min_periods=1).mean().shift(1)
        )
        
        # 2. Team rolling performance
        df['TeamAvgFinish'] = df.groupby('TeamName')['Position'].transform(
            lambda x: x.rolling(window=5, min_periods=1).mean().shift(1)
        )
        
        # 3. Track History (Average finish at this specific event)
        df['EventAvgFinish'] = df.groupby(['Abbreviation', 'EventName'])['Position'].transform(
            lambda x: x.expanding().mean().shift(1)
        )
        
        # Impute missing values using global mean (NO look-ahead bias if using training mean)
        global_mean = self.baselines.get('global_mean', df['Position'].mean())
        df['DriverAvgFinish'] = df['DriverAvgFinish'].fillna(global_mean)
        df['TeamAvgFinish'] = df['TeamAvgFinish'].fillna(global_mean)
        df['EventAvgFinish'] = df['EventAvgFinish'].fillna(global_mean)
        
        return df

    def transform(self, df):
        """Clean and engineer features for training."""
        if not self.is_fitted:
            raise ValueError("FeatureProcessor must be fitted before transform.")
            
        # Drop rows missing critical targets during training
        df = df.dropna(subset=['QualifyingPosition', 'Position'])
        
        # Calculate features
        df = self._calculate_rolling_features(df)
        
        # Encode categorical IDs (requires 2D input)
        df['DriverID'] = self.le_driver.transform(df[['Abbreviation']].values).ravel()
        df['TeamID'] = self.le_team.transform(df[['TeamName']].values).ravel()
        df['EventID'] = self.le_event.transform(df[['EventName']].values).ravel()
        
        X_seq = []
        y_seq = []
        
        # Group by driver to create sequences
        for driver_id, driver_df in df.groupby('DriverID'):
            driver_df = driver_df.sort_values(['Year', 'RoundNumber'])
            
            # Extract features array for this driver
            features = driver_df[self.feature_cols].values
            targets = driver_df['Position'].values
            
            # Need at least time_steps rows to form one sequence + target
            if len(features) < self.time_steps + 1:
                continue
                
            for i in range(len(features) - self.time_steps):
                X_seq.append(features[i : i + self.time_steps])
                # Target is the position at the next time step
                y_seq.append(targets[i + self.time_steps])
                
        return np.array(X_seq), np.array(y_seq)

    def transform_for_prediction(self, history_df, current_race_df, external_baselines=None):
        """
        Prepare real-time features for inference using stored statistics.
        history_df should contain the past N races for the drivers in current_race_df.
        """
        if not self.is_fitted:
            raise ValueError("FeatureProcessor must be fitted before transform_for_prediction.")
            
        # Use provided baselines or internal ones
        baselines = external_baselines if external_baselines is not None else self.baselines
        global_mean = baselines.get('global_mean', 10.0)
        
        # We need a sequence of length `self.time_steps` for each driver in `current_race_df`.
        # First, process `history_df` using the same logic as `_calculate_rolling_features` and ID encodings.
        # Ensure it has the necessary rolling features
        if history_df is not None and not history_df.empty:
             history_df = self._calculate_rolling_features(history_df)
             history_df['DriverID'] = self.le_driver.transform(history_df[['Abbreviation']].values).ravel()
             history_df['TeamID'] = self.le_team.transform(history_df[['TeamName']].values).ravel()
             history_df['EventID'] = self.le_event.transform(history_df[['EventName']].values).ravel()
        else:
            history_df = pd.DataFrame(columns=current_race_df.columns)

        event_name = current_race_df['EventName'].iloc[0] if 'EventName' in current_race_df.columns else "Unknown"
        event_id = self.le_event.transform([[event_name]])[0, 0]

        X_pred_seq = []
        
        for _, driver in current_race_df.iterrows():
            abbr = driver.get('Abbreviation', 'UNKNOWN')
            team = driver.get('TeamName', 'UNKNOWN')
            
            driver_id = self.le_driver.transform([[abbr]])[0, 0]
            team_id = self.le_team.transform([[team]])[0, 0]
            
            # Find history for this driver
            if 'DriverID' in history_df.columns:
                driver_history = history_df[history_df['DriverID'] == driver_id].sort_values(['Year', 'RoundNumber'])
            else:
                driver_history = pd.DataFrame(columns=self.feature_cols)
            
            # Extract features
            if not driver_history.empty:
                features = driver_history[self.feature_cols].values
            else:
                features = np.empty((0, len(self.feature_cols)))

            # If history is longer than needed, take the latest `self.time_steps`
            if len(features) >= self.time_steps:
                seq = features[-self.time_steps:]
            else:
                # Pad with baselines if history is too short
                driver_avg = baselines.get('driver_means', {}).get(abbr, global_mean)
                team_avg = baselines.get('team_means', {}).get(team, global_mean)
                event_avg = global_mean # Default

                pad_row = [
                    driver.get('QualifyingPosition', 10.0), # Assuming mid-pack if missing
                    driver.get('GridPosition', driver.get('QualifyingPosition', 10.0)),
                    driver_avg,
                    team_avg,
                    event_avg,
                    driver_id,
                    team_id,
                    event_id
                ]
                
                pad_length = self.time_steps - len(features)
                padding = np.array([pad_row] * pad_length)
                
                if len(features) > 0:
                    seq = np.vstack((padding, features))
                else:
                    seq = padding
                    
            X_pred_seq.append(seq)
            
        return np.array(X_pred_seq)
