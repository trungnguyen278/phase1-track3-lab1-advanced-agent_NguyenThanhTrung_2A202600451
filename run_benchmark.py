from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich import print
from rich.progress import Progress

from src.reflexion_lab.agents import ReActAgent, ReflexionAgent
from src.reflexion_lab.reporting import build_report, save_report
from src.reflexion_lab.utils import load_dataset, save_jsonl

app = typer.Typer(add_completion=False)


@app.command()
def main(
    dataset: str = "data/hotpot_mini.json",
    out_dir: str = "outputs/sample_run",
    reflexion_attempts: int = 3,
    mode: str = "real",
    limit: int = 0,
) -> None:
    examples = load_dataset(dataset)
    if limit > 0:
        examples = examples[:limit]

    react = ReActAgent()
    reflexion = ReflexionAgent(max_attempts=reflexion_attempts)

    react_records = []
    reflexion_records = []
    with Progress() as progress:
        task_r = progress.add_task("[cyan]ReAct", total=len(examples))
        for ex in examples:
            react_records.append(react.run(ex))
            progress.advance(task_r)
        task_x = progress.add_task("[magenta]Reflexion", total=len(examples))
        for ex in examples:
            reflexion_records.append(reflexion.run(ex))
            progress.advance(task_x)

    all_records = react_records + reflexion_records
    out_path = Path(out_dir)
    save_jsonl(out_path / "react_runs.jsonl", react_records)
    save_jsonl(out_path / "reflexion_runs.jsonl", reflexion_records)
    report = build_report(
        all_records,
        dataset_name=Path(dataset).name,
        mode=mode,
        model_name=os.getenv("LAB_LLM_MODEL", "gpt-3.5-turbo"),
    )
    json_path, md_path = save_report(report, out_path)
    print(f"[green]Saved[/green] {json_path}")
    print(f"[green]Saved[/green] {md_path}")
    print(json.dumps(report.summary, indent=2))


if __name__ == "__main__":
    app()
