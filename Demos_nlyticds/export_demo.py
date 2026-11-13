"""Export every dataset Boon can read from a Deadlock replay to Parquet and zip it.

Usage:
    python export_demo.py <path-to-demo.dem>
    python export_demo.py <demo.dem> --with-catalog --with-stats
    python export_demo.py <demo.dem> --out exports --no-zip

Raw Boon datasets, roster/header metadata, the PostMatchDetails summary, and
derived per-tick analytics are exported by default. Catalog-backed data
(``player_states``, ``imbues``) is enabled with ``--with-catalog``; calculated
ability/hero stats are enabled with ``--with-stats``.
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

import polars as pl

from boon import Demo

DATASETS = Demo.available_datasets()

HEADER_FIELDS = (
    "build",
    "map_name",
    "match_id",
    "game_mode",
    "tick_rate",
    "total_ticks",
    "total_seconds",
    "total_clock_time",
    "winning_team_num",
    "game_over_tick",
    "pregame_seconds",
    "game_start_tick",
    "regulation_ticks",
    "regulation_seconds",
    "regulation_clock_time",
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return value


class Exporter:
    def __init__(self, demo: Demo, out_dir: Path) -> None:
        self.demo = demo
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.entries: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}

    def write_frame(
        self,
        name: str,
        df: pl.DataFrame,
        *,
        kind: str = "dataset",
        source: str | None = None,
    ) -> Path:
        started = time.perf_counter()
        path = self.out_dir / f"{name}.parquet"
        df.write_parquet(path, compression="zstd", statistics=True)
        elapsed = time.perf_counter() - started
        self.entries.append(
            {
                "name": name,
                "kind": kind,
                "source": source or name,
                "file": path.name,
                "rows": df.height,
                "columns": df.width,
                "dtypes": {col: str(dtype) for col, dtype in df.schema.items()},
                "seconds": round(elapsed, 3),
                "status": "ok",
            }
        )
        print(f"  [ok] {name:<28} {df.height:>10,} x {df.width:<3} "
              f"{path.stat().st_size / 2**20:8.2f} MB  {elapsed:5.1f}s")
        del df
        gc.collect()
        return path

    def _record_error(self, name: str, kind: str, exc: Exception, elapsed: float) -> None:
        message = f"{type(exc).__name__}: {exc}"
        self.entries.append(
            {
                "name": name,
                "kind": kind,
                "source": name,
                "file": None,
                "rows": 0,
                "columns": 0,
                "dtypes": {},
                "seconds": round(elapsed, 3),
                "status": "error",
                "error": message,
            }
        )
        print(f"  [!!] {name:<28} {message}")

    def run(self, name: str, call: Callable[[], Any], *, kind: str = "dataset") -> None:
        started = time.perf_counter()
        try:
            result = call()
            if isinstance(result, pl.DataFrame):
                self.write_frame(name, result, kind=kind)
            else:
                raise TypeError(f"expected a Polars DataFrame, got {type(result)!r}")
        except Exception as exc:  # keep exporting the remaining datasets
            self._record_error(name, kind, exc, time.perf_counter() - started)

    def run_frames(
        self,
        name: str,
        call: Callable[[], dict[str, pl.DataFrame]],
        *,
        kind: str = "dataset",
    ) -> None:
        started = time.perf_counter()
        try:
            for suffix, frame in call().items():
                self.write_frame(f"{name}_{suffix}", frame, kind=kind, source=f"{name}.{suffix}")
        except Exception as exc:  # keep exporting the remaining datasets
            self._record_error(name, kind, exc, time.perf_counter() - started)

    def run_chunked_frames(
        self,
        name: str,
        ticks: list[int],
        call: Callable[[list[int]], dict[str, pl.DataFrame]],
        *,
        chunk_size: int = 2000,
        kind: str = "dataset",
    ) -> None:
        started = time.perf_counter()
        try:
            chunks = [ticks[i:i + chunk_size] for i in range(0, len(ticks), chunk_size)]
            for index, chunk in enumerate(chunks):
                for suffix, frame in call(chunk).items():
                    part = f"{name}_{suffix}"
                    if len(chunks) > 1:
                        part = f"{part}.part{index:04d}"
                    self.write_frame(part, frame, kind=kind, source=f"{name}.{suffix}")
        except Exception as exc:  # keep exporting the remaining datasets
            self._record_error(name, kind, exc, time.perf_counter() - started)

    def collect_metadata(self) -> None:
        data: dict[str, Any] = {
            "demo_path": str(self.demo.path),
            "file_size_bytes": self.demo.path.stat().st_size,
            "file_mtime_ns": self.demo.path.stat().st_mtime_ns,
        }
        for field in HEADER_FIELDS:
            try:
                data[field] = _jsonable(getattr(self.demo, field))
            except Exception as exc:
                data[field] = None
                data[f"{field}_error"] = f"{type(exc).__name__}: {exc}"
        self.metadata = data


def export_summary(exporter: Exporter) -> None:
    print("Post-match summary")
    exporter.run_frames("summary", exporter.demo.summary, kind="summary")


def export_catalog(
    exporter: Exporter,
    data_version: str,
    include_stats: bool,
    every: int,
) -> None:
    print(f"Catalog-backed data (data_version={data_version}, every={every} ticks)")
    exporter.run(
        "player_states",
        lambda: exporter.demo.player_states(data_version=data_version),
        kind="catalog",
    )

    ticks = exporter.demo.player_ticks["tick"].unique().sort().to_list()
    if every > 1:
        ticks = ticks[::every]
    exporter.metadata["catalog_tick_every"] = every
    exporter.metadata["catalog_tick_count"] = len(ticks)

    def imbues(chunk: list[int]) -> dict[str, pl.DataFrame]:
        result = exporter.demo.imbues(ticks=chunk, data_version=data_version)
        exporter.metadata["imbues_metadata"] = _jsonable(result.metadata)
        return {"bindings": result.bindings, "effects": result.effects}

    exporter.run_chunked_frames("imbues", ticks, imbues, kind="catalog")

    if not include_stats:
        return

    def ability_stats(chunk: list[int]) -> dict[str, pl.DataFrame]:
        result = exporter.demo.calculate_ability_stats(
            ticks=chunk, data_version=data_version, strict=False
        )
        exporter.metadata["ability_stats_metadata"] = _jsonable(result.metadata)
        return {"contributions": result.contributions, "values": result.values}

    exporter.run_chunked_frames("ability_stats", ticks, ability_stats, kind="stats")

    def hero_stats(chunk: list[int]) -> dict[str, pl.DataFrame]:
        result = exporter.demo.calculate_hero_stats(
            ticks=chunk, data_version=data_version, strict=False
        )
        exporter.metadata["hero_stats_metadata"] = _jsonable(result.metadata)
        return {"contributions": result.contributions, "values": result.values}

    exporter.run_chunked_frames("hero_stats", ticks, hero_stats, kind="stats")


def export(demo_path: Path, out_dir: Path, args: argparse.Namespace) -> Path:
    print(f"Opening {demo_path}")
    started = time.perf_counter()
    demo = Demo(str(demo_path), preload=False)
    exporter = Exporter(demo, out_dir)
    exporter.collect_metadata()
    print(f"  opened in {time.perf_counter() - started:.1f}s")

    print("Roster")
    exporter.run("players", lambda: demo.players, kind="metadata")
    exporter.run("banned_heroes", lambda: demo.banned_heroes, kind="metadata")

    print("Native datasets")
    names = args.datasets or DATASETS
    for name in names:
        exporter.run(name, lambda n=name: getattr(demo, n))

    export_summary(exporter)

    print("Derived analytics")
    exporter.run("enemy_minimap_ticks", lambda: demo.enemy_minimap_ticks(), kind="derived")
    exporter.run("in_combat", lambda: demo.in_combat(), kind="derived")
    exporter.run("kill_participation", lambda: demo.kill_participation(), kind="derived")
    exporter.run("time_dead", lambda: demo.time_dead(), kind="derived")
    exporter.run("teamfights", lambda: demo.teamfights(), kind="derived")

    if args.with_catalog or args.with_stats:
        version = args.data_version
        if version is None:
            from boon import data as boon_data

            version = boon_data.resolve_version(None)
        export_catalog(exporter, version, args.with_stats, args.catalog_every)

    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(exporter.metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest_path = out_dir / "manifest.json"
    manifest = {
        "demo": str(demo_path),
        "out_dir": str(out_dir),
        "elapsed_seconds": round(time.perf_counter() - started, 1),
        "datasets": exporter.entries,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Metadata -> {metadata_path}")
    print(f"Manifest -> {manifest_path}")
    return out_dir


def make_zip(folder: Path, zip_path: Path) -> Path:
    print(f"Archiving {folder} -> {zip_path}")
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(folder.parent))
    print(f"Archive -> {zip_path} ({zip_path.stat().st_size / 2**20:.1f} MB)")
    return zip_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("demo", type=Path, help="Path to a .dem replay")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("exports"),
        help="Parent output directory (default: ./exports)",
    )
    parser.add_argument("--zip", dest="zip_path", type=Path, default=None,
                        help="Archive path (default: <out>/<demo-stem>_parquet.zip)")
    parser.add_argument("--no-zip", action="store_true", help="Do not create the archive")
    parser.add_argument("--clean", action="store_true",
                        help="Remove the Parquet folder after a successful archive")
    parser.add_argument("--datasets", nargs="+", metavar="NAME", default=None,
                        help="Export only these native datasets")
    parser.add_argument("--with-catalog", action="store_true",
                        help="Also export player_states and imbues (downloads boon-data)")
    parser.add_argument("--with-stats", action="store_true",
                        help="Also export calculated ability/hero stats (implies --with-catalog)")
    parser.add_argument("--data-version", default=None,
                        help="Boon-data client version for catalog-backed exports")
    parser.add_argument("--catalog-every", type=int, default=64, metavar="N",
                        help="Sample catalog-backed per-tick data every N recorded ticks "
                             "(default: 64; use 1 for every tick)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    demo_path = args.demo.expanduser().resolve()
    if not demo_path.is_file():
        print(f"Demo not found: {demo_path}", file=sys.stderr)
        return 2
    if args.catalog_every < 1:
        print("--catalog-every must be >= 1", file=sys.stderr)
        return 2

    out_dir = (args.out / f"{demo_path.stem}_parquet").resolve()
    export(demo_path, out_dir, args)

    if not args.no_zip:
        zip_path = args.zip_path
        if zip_path is None:
            zip_path = out_dir.parent / f"{demo_path.stem}_parquet.zip"
        make_zip(out_dir, zip_path.resolve())
        if args.clean:
            import shutil

            shutil.rmtree(out_dir)
            print(f"Removed {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
