@echo off

cd /d "%~dp0"

python etl_pipeline.py > pipeline_output.txt 2>&1

type pipeline_output.txt