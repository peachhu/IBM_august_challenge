@echo off
cd /d "C:\Users\MuNe\IBM_challenge\august_challenge\IBM_august_challenge"
"C:\Users\MuNe\AppData\Local\Programs\Python\Python314\python.exe" etl_pipeline.py > pipeline_output.txt 2>&1
type pipeline_output.txt
