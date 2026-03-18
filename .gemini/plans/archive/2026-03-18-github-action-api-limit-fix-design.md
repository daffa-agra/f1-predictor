# Design Document: GitHub Action API Limit Fix (Incremental Fetching & Caching)

## 1. Problem Statement
The current GitHub Action workflow for F1 predictions (`f1-prediction.yml`) triggers redundant API calls to the FastF1 data backend in every run. Because the `data/cache` directory is not preserved across CI runs, the `scripts/fine_tune.py` script attempts to fetch historical data from 2020 to the present day each time it executes. This behavior frequently hits the Ergast API's rate limits, causing the workflow to fail.

## 2. Requirements
- **Functional Requirements:**
  - Persist the `data/cache` directory between GitHub Actions runs using the `actions/cache` action.
  - Automatically update the cache when new data is successfully fetched for the current 2026 season.
- **Non-Functional Requirements:**
  - Minimize execution time of the `Fine-tune & Train` step by loading data from the local cache.
  - Ensure the cache is restored before the `fine_tune.py` script runs and saved after successful execution.
- **Constraints:**
  - Total cache size must stay within GitHub's 10GB limit (currently only 5.2MB, so not an issue).
  - Cache must be scoped correctly (keyed by a hash of `requirements.txt` or a static version).

## 3. Selected Approach: GitHub Actions Caching & Incremental Fetching
**Summary**: This approach implements persistent storage of the FastF1 `data/cache` directory using GitHub's `actions/cache` action combined with an incremental fetching logic.
**Architecture**: 
- The workflow `f1-prediction.yml` will be updated with a new step that restores the `data/cache` folder at the beginning of each job.
- The `data_fetcher.py` and `fine_tune.py` scripts will be updated to fetch data incrementally, starting from the latest available data in the cache.
- FastF1's built-in `Cache.enable_cache("data/cache")` will then automatically read existing data from disk instead of making remote API calls.
- Hyperparameter tuning will only execute after the dataset is fully consolidated.

## 4. Architecture: Incremental Fetching & Caching
**Data Flow:**
1. **Cache Restore**: GitHub Action (`actions/cache`) restores `data/cache` from the previous run.
2. **Incremental Load**: `scripts/fine_tune.py` will:
   - Identify the "Latest Year" available in the local `data/historical_data_*.csv`.
   - If the API limit allows, fetch missing historical years.
   - Fetch only the most recent sessions from the 2026 season.
3. **Data Refresh**: Merge newly fetched data with existing historical data and save the updated CSV.
4. **Caching**: FastF1's built-in `Cache.enable_cache("data/cache")` will avoid redundant calls for individual race sessions.
5. **Fine-tuning**: Only after all data is refreshed and processed will the `RandomizedSearchCV` hyperparameter tuning execute.
6. **Cache Save**: GitHub Actions saves the updated `data/cache` directory for future runs.

## 5. Agent Team
- **`devops_engineer`**: Update `.github/workflows/f1-prediction.yml` to include the `actions/cache` step.
- **`data_engineer`**: Refactor `src/f1_predictor/data_fetcher.py` and `scripts/fine_tune.py` for incremental fetching.
- **`tester`**: Verify the incremental loading and caching logic through local simulation.

## 6. Risk Assessment & Mitigation
- **Cache Invalidation**: Use `requirements.txt` as a cache key; if dependencies change, re-fetch.
- **Corrupted CSV**: Implement data integrity checks before fine-tuning.
- **API Limit in Initial Run**: Incremental fetching will skip already-cached years.

## 7. Success Criteria
- **Workflow Completion**: GitHub Action completes without API failures.
- **Cache Hits**: FastF1 reports loading from cache for 2020-2025 data.
- **Incrementalism**: Historical CSV updates with only missing years and 2026 data.
- **Fine-tuning**: Hyperparameter tuning runs after consolidation.
