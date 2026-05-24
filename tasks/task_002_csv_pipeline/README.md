# Task 002 — CSV Pipeline

## Overview
A data-processing pipeline that reads sales data from CSV, cleans and transforms it, and writes the results as JSON. The pipeline computes running (cumulative) totals for the `amount` column.

## The Bug
`transformers.py :: calculate_running_totals` assigns `running_total` **before** adding the current row's amount to the accumulator. This means:
- Row 1 gets `running_total = 0` instead of `50.0`
- Row 2 gets `running_total = 50.0` instead of `87.5`
- Every row is off by the first row's amount.

## Expected Behaviour
The `running_total` for each row should be the cumulative sum of all amounts **up to and including** that row.

## Running
```bash
pip install -r requirements.txt
python pipeline.py
```

## Verification
```bash
bash verify.sh
```
