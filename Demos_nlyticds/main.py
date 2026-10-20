import polars as pl
import argparse

parser = argparse.ArgumentParser(
    description="A simple script to demonstrate argparse."
)

parser.add_argument("filename", help="Path to the input file")

URI = parser.parse_args().filename

df: pl.DataFrame = pl.read_parquet(URI)
