# Design Document: F1 Data Sync Patch

## Problem Statement
The F1 Prediction pipeline has reached its API call limit (FastF1/Ergast). Consequently, GitHub Actions CI/CD runs are failing to fetch the complete dataset required for model training. The goal is to leverage a complete local copy of `data/historical_data.csv` as a persistent baseline in the remote repository, "patching" the gap caused by the API limits.

## Requirements
### Functional
- Use the locally-provided `data/historical_data.csv` as the baseline for all CI/CD runs.
- Commit the CSV to the remote repository (GitHub) to ensure it is always available.
- Ensure CI/CD still supports incremental fetching for future races.

### Non-Functional
- **Reliability**: Model training must have access to at least 2020-2024 data.
- **Maintainability**: Baseline should be easy to update manually if needed.
- **Efficiency**: Minimize API calls by using the tracked CSV as the starting point.

## Selected Approach
### Approach 1: Persistent Baseline in Git
Unignore and commit `data/historical_data.csv` to the repository. This provides a reliable data source for the CI environment, effectively mitigating API limit failures.

## Architecture
### Components
- **Local Git Repository**: Source of truth for code and the `historical_data.csv` baseline.
- **GitHub Actions CI/CD**:
    - Pulls the repository (including the CSV).
    - Uses `fine_tune.py` which loads the CSV as its starting historical dataset.
    - Incremental fetching logic only pulls missing races (API-efficient).
- **Data Flow**: Local Developer -> Manual CSV Update -> GitHub -> CI/CD -> Model Training.

## Agent Team
- **Coder**: Modifies `.gitignore` and commits the CSV.
- **DevOps Engineer**: Verifies GitHub Action compatibility.
- **Tester**: Validates CSV tracking and CI execution.

## Risk Assessment & Mitigation
- **CSV Size**: Managing file growth (~15-20K lines/year) is handled by Git's efficient storage for small-to-medium files (~2MB over 10 years).
- **API Limits**: The tracked CSV serves as a fallback, reducing the number of required API calls to near zero for existing data.

## Success Criteria
- `.gitignore` allows `data/historical_data.csv`.
- `data/historical_data.csv` is committed and pushed to GitHub.
- GitHub Action successfully loads the CSV and completes model training.
- Model is trained on the full 2020-2024 baseline.
