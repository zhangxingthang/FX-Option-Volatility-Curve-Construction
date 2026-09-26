"""Track EUR/AUD option smiles across daily TFS-ICAP CSV exports.

Run once to rebuild the history, or pass --watch to refresh when CSVs change.
The public sample contains only one actual date; later dates require new exports.
"""

import argparse
import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sabr_euraud import fit_smile, parse_quotes


def collect_daily(input_folder):
    """Use the latest synchronized one-month quote set for each source calendar day."""
    if not input_folder.is_dir():
        raise ValueError(f"Create the quote folder first: {input_folder}")
    latest = {}
    for path in sorted(input_folder.glob("*.csv")):
        try:
            quotes = parse_quotes(path)
        except (ValueError, KeyError) as exc:
            print(f"Skipping {path.name}: {exc}")
            continue
        date = quotes["timestamp"][:10]
        if date not in latest or quotes["timestamp"] > latest[date]["timestamp"]:
            latest[date] = dict(quotes, file=path.name)
    history = []
    for date, quotes in sorted(latest.items()):
        strikes, vols, parameters, errors = fit_smile(quotes)
        history.append({
            "date": date,
            "quote_timestamp": quotes["timestamp"],
            "file": quotes["file"],
            "atm_rr_bf_vol_points": {key: quotes[key] for key in ("atm", "rr", "bf")},
            "put_25d_atm_call_vol_percent": (vols * 100).tolist(),
            "relative_strikes_put_atm_call": strikes.tolist(),
            "sabr_beta_1_alpha_rho_nu": parameters.tolist(),
            "maximum_anchor_error_vol_percentage_points": float(max(abs(errors)) * 100),
        })
    return history


def save_history(history, output_folder):
    if not history:
        raise ValueError("No valid dated EUR/AUD 1M ATM/RR/BF quote sets found")
    output_folder.mkdir(parents=True, exist_ok=True)
    dates = [day["date"] for day in history]
    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    for index, label in enumerate(("25D put", "ATM", "25D call")):
        ax.plot(dates, [day["put_25d_atm_call_vol_percent"][index] for day in history],
                marker="o", label=label)
    ax.set(title="EUR/AUD 1M option volatility: daily quote-derived anchors",
           xlabel="Quote date in source timestamp", ylabel="Annualized implied volatility (%)")
    ax.tick_params(axis="x", labelrotation=35)
    ax.grid(alpha=0.2)
    ax.legend()
    fig.savefig(output_folder / "euraud_daily_volatility.png", dpi=180)
    plt.close(fig)
    (output_folder / "euraud_daily_history.json").write_text(
        json.dumps(history, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Updated {len(history)} distinct date(s): {dates[0]} through {dates[-1]}")


def snapshot(folder):
    return tuple(sorted((path.name, path.stat().st_size, path.stat().st_mtime_ns)
                        for path in folder.glob("*.csv")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data"), help="Folder of daily TFS-ICAP CSV files")
    parser.add_argument("--output", type=Path, default=Path("results"), help="Folder for updated chart and JSON")
    parser.add_argument("--watch", action="store_true", help="Keep running and refresh when a new CSV arrives")
    args = parser.parse_args()
    if not args.input.is_dir():
        parser.error(f"Create the quote folder first: {args.input}")
    previous = None
    while True:
        current = snapshot(args.input)
        if current != previous:
            try:
                save_history(collect_daily(args.input), args.output)
            except ValueError as exc:
                print(exc)
            previous = current
        if not args.watch:
            break
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            print("Stopped watching for new quotes.")
            break


if __name__ == "__main__":
    main()
