# CHANGES.md - Refactoring Summary

## Overview
This document summarizes the refactoring and expansion tasks performed on the Taiwan Stock Strategy Mining System.

## Task 1: Trigger Expansion
- **File**: `agents/local_hypothesis_generator.py`
- **Changes**: Added 18 new trigger templates (A02, A05, B05, E01, E02, E03, G01, G03, G04, H01, H04, H05, J01, J04, K04, K05, M04, M05) with dense parameter grids.

## Task 2: Unified Validation Thresholds
- **File**: `config/config.py`
- **Changes**: Introduced centralized constants for validation logic (e.g., `MIN_WIN_RATE`, `MIN_SHARPE`).
- **File**: `engine/validator.py`
- **Changes**: Updated `validate_backtests` to reference the central constants.
- **File**: `dbg.py`
- **Changes**: Replaced hardcoded numbers with imports from `config.py`.

## Task 3: L01 Logic Correction
- **File**: `engine/backtest.py`
- **Changes**: Refactored the `L01` trigger to require simultaneous institutional buy streak, price streak, and KD bull condition.

## Task 4: Universe Cleanup
- **File**: `data/universe.py`
- **Changes**: Removed duplicate stock codes and added an assertion to prevent future duplicates.

## Task 5: Orchestrator Robustness
- **File**: `engine/orchestrator.py`
- **Changes**: Removed unsafe directory-wide JSON fallback and added explicit error handling for missing strategy batches.

## Task 6: Deprecation Warning
- **File**: `agents/hypothesis_generator.py`
- **Changes**: Added a `DeprecationWarning` to the entry point.
- **File**: `engine/orchestrator.py`
- **Changes**: Added a deprecation notice comment at the top.
