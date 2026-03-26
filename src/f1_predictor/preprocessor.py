import pandas as pd
import numpy as np
from sklearn.preprocessing import OrdinalEncoder, StandardScaler

class FeatureProcessor:
    """Stateful feature engineering pipeline for F1 race prediction."""
    
    def __init__(self, time_steps=5):
        self.le_driver = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
        self.le_team = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
        self.le_event = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
        self.scaler = StandardScaler()
        self.baselines = {}
        self.is_fitted = False
        self.time_steps = time_steps
        
        # Define feature groups
        self.numerical_cols = [
            'QualifyingPosition', 'GridPosition', 'DriverAvgFinish', 
            'TeamAvgFinish', 'EventAvgFinish', 'QDelta', 'is_mechanical_dnf',
            'TeammateQDelta', 'TrackCluster', 'TeamSlope', 'AirTemp', 'Rainfall'
        ]
        self.categorical_cols = ['DriverID', 'TeamID', 'EventID']
        self.feature_cols = self.numerical_cols + self.categorical_cols

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
        
        # Fit scaler on numerical features from a processed version of the training data
        processed_df = self._preprocess_raw_df(df)
        processed_df = self._calculate_rolling_features(processed_df, shift=True)
        # Drop rows missing critical targets during training to match transform logic
        processed_df = processed_df.dropna(subset=['QualifyingPosition', 'Position'])
        self.scaler.fit(processed_df[self.numerical_cols])
        
        self.is_fitted = True
        return self

    def _preprocess_raw_df(self, df):
        """Initial cleaning and base feature creation."""
        df = df.copy()
        
        # 1. Mechanical DNF Flag
        # Standard finishes: 'Finished' or '+N Laps'
        # Driver errors: 'Accident', 'Collision', 'Spun off'
        def check_mechanical(status):
            s = str(status)
            if s in ['Finished', 'Accident', 'Collision', 'Spun off']:
                return 0
            if s.startswith('+') and ('Lap' in s or 'Laps' in s):
                return 0
            return 1
            
        if 'Status' in df.columns:
            df['is_mechanical_dnf'] = df['Status'].apply(check_mechanical)
        else:
            df['is_mechanical_dnf'] = 0
            
        # 2. QDelta Handling
        if 'QDelta' in df.columns:
            # Fill missing QDelta with a penalty (e.g., 105% of max or fixed high value)
            # If all are NaN, use a default high value
            max_delta = df['QDelta'].max()
            fill_val = max_delta * 1.1 if not np.isnan(max_delta) else 5.0
            df['QDelta'] = df['QDelta'].fillna(fill_val)
        else:
            df['QDelta'] = 0.0

        # 3. Weather
        if 'AirTemp' not in df.columns:
            df['AirTemp'] = 25.0
        if 'Rainfall' not in df.columns:
            df['Rainfall'] = 0

        # 4. Track Clusters
        track_map = {
            'Monza': 0, 'Spa-Francorchamps': 0, 'Jeddah Street Circuit': 0, 'Las Vegas Strip Circuit': 0, 'Red Bull Ring': 0,
            'Circuit de Barcelona-Catalunya': 1, 'Silverstone Circuit': 1, 'Suzuka International Racing Course': 1, 'Circuit of the Americas': 1, 'Lusail International Circuit': 1,
            'Monaco': 2, 'Marina Bay Street Circuit': 2, 'Baku City Circuit': 2, 'Albert Park Circuit': 2, 'Miami International Autodrome': 2, 'Circuit Gilles-Villeneuve': 2,
        }
        df['TrackCluster'] = df['EventName'].map(track_map).fillna(3)
            
        return df

    def _calculate_rolling_features(self, df, shift=True):
        """Calculate rolling averages with a shift to avoid data leakage."""
        df = df.copy()
        df = df.sort_values(['Year', 'RoundNumber'])
        
        # Core rolling positions
        if shift:
            df['DriverAvgFinish'] = df.groupby('Abbreviation')['Position'].transform(
                lambda x: x.rolling(window=self.time_steps, min_periods=1).mean().shift(1)
            )
            df['TeamAvgFinish'] = df.groupby('TeamName')['Position'].transform(
                lambda x: x.rolling(window=self.time_steps, min_periods=1).mean().shift(1)
            )
            # Team Slope: change in team performance over last 3 races
            df['TeamSlope'] = df.groupby('TeamName')['TeamAvgFinish'].transform(
                lambda x: x.diff().rolling(window=3, min_periods=1).mean()
            )
            df['EventAvgFinish'] = df.groupby(['Abbreviation', 'EventName'])['Position'].transform(
                lambda x: x.expanding().mean().shift(1)
            )
        else:
            df['DriverAvgFinish'] = df.groupby('Abbreviation')['Position'].transform(
                lambda x: x.rolling(window=self.time_steps, min_periods=1).mean()
            )
            df['TeamAvgFinish'] = df.groupby('TeamName')['Position'].transform(
                lambda x: x.rolling(window=self.time_steps, min_periods=1).mean()
            )
            df['TeamSlope'] = df.groupby('TeamName')['TeamAvgFinish'].transform(
                lambda x: x.diff().rolling(window=3, min_periods=1).mean()
            )
            df['EventAvgFinish'] = df.groupby(['Abbreviation', 'EventName'])['Position'].transform(
                lambda x: x.expanding().mean()
            )
        
        # Teammate QDelta
        df['TeammateQDelta'] = df.groupby(['Year', 'RoundNumber', 'TeamName'])['QDelta'].transform(
            lambda x: (x.sum() - x) / (x.count() - 1) if x.count() > 1 else x
        )

        # Impute missing values using global mean
        global_mean = self.baselines.get('global_mean', df['Position'].mean() if not df.empty else 10.0)
        df['DriverAvgFinish'] = df['DriverAvgFinish'].fillna(global_mean)
        df['TeamAvgFinish'] = df['TeamAvgFinish'].fillna(global_mean)
        df['EventAvgFinish'] = df['EventAvgFinish'].fillna(global_mean)
        df['TeamSlope'] = df['TeamSlope'].fillna(0.0)
        df['TeammateQDelta'] = df['TeammateQDelta'].fillna(df['QDelta'])
        
        return df

    def transform(self, df):
        """Clean and engineer features for training."""
        if not self.is_fitted:
            raise ValueError("FeatureProcessor must be fitted before transform.")
            
        # Drop rows missing critical targets during training
        df = df.dropna(subset=['QualifyingPosition', 'Position'])
        
        # Apply base preprocessing (DNF, QDelta)
        df = self._preprocess_raw_df(df)
        
        # Calculate features with shift=True to prevent leakage
        df = self._calculate_rolling_features(df, shift=True)
        
        # Encode categorical IDs (requires 2D input)
        df['DriverID'] = self.le_driver.transform(df[['Abbreviation']].values).ravel()
        df['TeamID'] = self.le_team.transform(df[['TeamName']].values).ravel()
        df['EventID'] = self.le_event.transform(df[['EventName']].values).ravel()
        
        # Apply scaling to numerical features
        df[self.numerical_cols] = self.scaler.transform(df[self.numerical_cols])
        
        # Final safety fill for any unexpected NaNs in feature columns
        # Note: Scaled data mean is 0.0
        df[self.feature_cols] = df[self.feature_cols].fillna(0.0)

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
        
        # 1. Process history_df (shift=False to get absolute latest stats)
        if history_df is not None and not history_df.empty:
             history_df = self._preprocess_raw_df(history_df)
             history_df = self._calculate_rolling_features(history_df, shift=False)
             history_df['DriverID'] = self.le_driver.transform(history_df[['Abbreviation']].values).ravel()
             history_df['TeamID'] = self.le_team.transform(history_df[['TeamName']].values).ravel()
             history_df['EventID'] = self.le_event.transform(history_df[['EventName']].values).ravel()
             
             # Apply scaling to history
             history_df[self.numerical_cols] = self.scaler.transform(history_df[self.numerical_cols])
             history_df[self.feature_cols] = history_df[self.feature_cols].fillna(0.0)
        else:
            history_df = pd.DataFrame(columns=self.feature_cols + ['Abbreviation', 'Year', 'RoundNumber'])

        # 2. Process current_race_df for base features
        current_race_df = self._preprocess_raw_df(current_race_df)
        
        event_name = current_race_df['EventName'].iloc[0] if 'EventName' in current_race_df.columns else "Unknown"
        event_id_arr = self.le_event.transform([[event_name]])
        event_id = event_id_arr[0, 0] if event_id_arr.size > 0 else -1

        X_pred_seq = []
        
        for _, driver in current_race_df.iterrows():
            abbr = driver.get('Abbreviation', 'UNKNOWN')
            team = driver.get('TeamName', 'UNKNOWN')
            
            driver_id_arr = self.le_driver.transform([[abbr]])
            driver_id = driver_id_arr[0, 0] if driver_id_arr.size > 0 else -1
            
            team_id_arr = self.le_team.transform([[team]])
            team_id = team_id_arr[0, 0] if team_id_arr.size > 0 else -1
            
            # Find history for this driver
            if 'Abbreviation' in history_df.columns:
                driver_history = history_df[history_df['Abbreviation'] == abbr].sort_values(['Year', 'RoundNumber'])
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
                event_avg = global_mean

                # Construct unscaled pad row
                raw_pad_row = {
                    'QualifyingPosition': driver.get('QualifyingPosition', 10.0),
                    'GridPosition': driver.get('GridPosition', driver.get('QualifyingPosition', 10.0)),
                    'DriverAvgFinish': driver_avg,
                    'TeamAvgFinish': team_avg,
                    'EventAvgFinish': event_avg,
                    'QDelta': driver.get('QDelta', 0.0),
                    'is_mechanical_dnf': 0,
                    'TeammateQDelta': driver.get('QDelta', 0.0), # Assume teammate is similar if unknown
                    'TrackCluster': driver.get('TrackCluster', 3.0),
                    'TeamSlope': 0.0,
                    'AirTemp': driver.get('AirTemp', 25.0),
                    'Rainfall': driver.get('Rainfall', 0)
                }
                
                # Scale the numerical part of the pad row
                pad_df = pd.DataFrame([raw_pad_row])
                pad_df[self.numerical_cols] = self.scaler.transform(pad_df[self.numerical_cols])
                
                scaled_numerical_pad = pad_df[self.numerical_cols].values[0]
                full_pad_row = np.concatenate([
                    scaled_numerical_pad,
                    [driver_id, team_id, event_id]
                ])
                
                pad_length = self.time_steps - len(features)
                padding = np.array([full_pad_row] * pad_length)
                
                if len(features) > 0:
                    seq = np.vstack((padding, features))
                else:
                    seq = padding
            
            # Final safety fill
            seq = np.nan_to_num(seq, nan=0.0)
            X_pred_seq.append(seq)
            
        return np.array(X_pred_seq)
