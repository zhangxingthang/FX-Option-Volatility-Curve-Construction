"""Fit one EUR/AUD SABR smile to genuine TFS-ICAP ATM/RR/BF quotes.

This educational example uses a normalized forward, a fixed one-month expiry,
forward delta and beta=1. It does not claim a broker-strangle calibration.
"""

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares
from scipy.stats import norm


RECORDS = {"atm": "IEURAUD_1M", "rr": "IEURAUDRR25_1M", "bf": "IEURAUDBF25_1M"}
T = 30 / 365  # illustrative 30-calendar-day tenor; actual 1M expiry is not in the CSV.


def parse_quotes(path, maximum_age_seconds=1):
    """Find the most recent BF update with contemporaneous ATM and RR quotes."""
    from datetime import datetime

    updates = {name: [] for name in RECORDS}
    with open(path, newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            if row["Currency"] != "EUR/AUD":
                continue
            name = next((name for name, record in RECORDS.items() if row["Record"] == record), None)
            if name is None:
                continue
            bid, ask = float(row["Bid"]), float(row["Ask"])
            if ask < bid:
                raise ValueError(f"Crossed {name} bid/ask: {row}")
            if name == "rr" and (row["CurrencyCode"], row["PricingConvention"]) != ("1", "1"):
                raise ValueError("Unrecognized risk reversal sign convention")
            updates[name].append((datetime.fromisoformat(row["Timestamp"]), (bid + ask) / 2, bid, ask))
    if any(not items for items in updates.values()):
        raise ValueError("Need EUR/AUD 1M ATM, 25D RR and 25D BF records")
    for bf_time, bf, bf_bid, bf_ask in sorted(updates["bf"], reverse=True):
        others = {}
        for name in ("atm", "rr"):
            candidates = [q for q in updates[name] if abs((q[0] - bf_time).total_seconds()) <= maximum_age_seconds]
            if not candidates:
                break
            others[name] = min(candidates, key=lambda q: abs((q[0] - bf_time).total_seconds()))
        if len(others) == 2:
            return {
                "timestamp": bf_time.isoformat(), "atm": others["atm"][1],
                "rr": others["rr"][1], "bf": bf,
                "bid_ask": {
                    "atm": [others["atm"][2], others["atm"][3]],
                    "rr": [others["rr"][2], others["rr"][3]],
                    "bf": [bf_bid, bf_ask],
                },
            }
    raise ValueError("No synchronized one-month EUR/AUD ATM/RR/BF quote set within one second")


def forward_delta_strike(vol, call, forward=1.0, t=T):
    """Strike with +25% call or -25% put *forward* delta."""
    d1 = norm.ppf(0.25 if call else 0.75)
    return float(forward * np.exp(-d1 * vol * np.sqrt(t) + 0.5 * vol**2 * t))


def sabr_lognormal_vol(forward, strike, t, alpha, rho, nu):
    """Hagan's beta=1 lognormal SABR implied-volatility approximation."""
    log_fk = np.log(forward / np.asarray(strike, dtype=float))
    z = (nu / alpha) * log_fk
    x = np.log((np.sqrt(1 - 2 * rho * z + z * z) + z - rho) / (1 - rho))
    ratio = np.divide(z, x, out=np.ones_like(z), where=np.abs(z) > 1e-8)
    correction = 1 + (rho * alpha * nu / 4 + (2 - 3 * rho**2) * nu**2 / 24) * t
    return alpha * ratio * correction


def fit_smile(quotes):
    """Convert vol-point quotes to 3 strike/vol anchors, then fit 3 parameters."""
    atm, rr, bf = (quotes[key] / 100 for key in ("atm", "rr", "bf"))
    put_vol, call_vol = atm + bf - rr / 2, atm + bf + rr / 2
    if min(put_vol, atm, call_vol) <= 0:
        raise ValueError("All derived option volatilities must be positive")
    strikes = np.array([
        forward_delta_strike(put_vol, call=False),
        1.0,
        forward_delta_strike(call_vol, call=True),
    ])
    targets = np.array([put_vol, atm, call_vol])
    def residual(parameters):
        alpha, rho, nu = parameters
        return sabr_lognormal_vol(1.0, strikes, T, alpha, rho, nu) - targets
    fit = least_squares(residual, [atm, 0.1, 0.5], bounds=([0.001, -0.99, 0.001], [1.0, 0.99, 10]),
                        xtol=1e-13, ftol=1e-13, gtol=1e-13)
    if not fit.success or max(abs(fit.fun)) > 0.0001:
        raise ValueError(f"Failed to fit the three market anchors: {fit.message}; residual={fit.fun}")
    return strikes, targets, fit.x, fit.fun


def run(source, output):
    quotes = parse_quotes(source)
    strikes, targets, parameters, errors = fit_smile(quotes)
    grid = np.linspace(strikes[0] * 0.98, strikes[-1] * 1.02, 151)
    smooth = sabr_lognormal_vol(1.0, grid, T, *parameters)
    output.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    ax.plot(grid, smooth * 100, label="SABR (beta=1)")
    ax.scatter(strikes, targets * 100, color="#b04c34", label="Market anchors", zorder=3)
    ax.set(title="EUR/AUD 1M option volatility smile (28 April 2025)",
           xlabel="Strike / assumed forward", ylabel="Annualized implied volatility (%)")
    ax.grid(alpha=0.2)
    ax.legend()
    fig.savefig(output / "euraud_one_month_smile.png", dpi=180)
    fig.savefig(output / "euraud_one_month_smile.svg")
    plt.close(fig)
    report = {
        "source": "CME TFS-ICAP sample, 28 April 2025",
        "quote_timestamp": quotes["timestamp"],
        "market_vol_points": {key: quotes[key] for key in ("atm", "rr", "bf")},
        "bid_ask_vol_points": quotes["bid_ask"],
        "derived_25d_put_atm_call_vol_percent": (targets * 100).tolist(),
        "relative_strikes_25d_put_atm_call": strikes.tolist(),
        "sabr_beta_1_parameters_alpha_rho_nu": parameters.tolist(),
        "maximum_anchor_error_vol_percentage_points": float(max(abs(errors)) * 100),
        "assumptions": ["30-calendar-day tenor proxy", "normalized forward = 1",
                        "25% forward delta", "25D butterfly quote is not a market-strangle quote"],
    }
    (output / "quote_and_fit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Locally downloaded CME TFS-ICAP sample CSV")
    parser.add_argument("--output", type=Path, default=Path("results"))
    arguments = parser.parse_args()
    run(arguments.csv_path, arguments.output)
