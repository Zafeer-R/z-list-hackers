"""Flask UI only. All data logic lives in app/data.py."""

import hmac
import os
from pathlib import Path

import pandas as pd
from flask import Flask, Response, abort, render_template, request

from app import data, explain

MAX_ROWS = 200
FOOTER = "Scores flag statistically unusual prescribing for review. They are not findings of wrongdoing."
RESULTS_FILE = Path(__file__).resolve().parent.parent / "data" / "backtest_results.csv"

app = Flask(__name__)
data.load_data()


def format_value(v):
    if v is None:
        return "n/a"
    if abs(v) >= 100:
        return f"{v:,.0f}"
    if abs(v) >= 1:
        return f"{v:,.2f}"
    return f"{v:.3f}"


def pct_label(p):
    if p is None:
        return "n/a"
    return f"{p * 100:.0f}%"


app.jinja_env.filters["fmt"] = format_value
app.jinja_env.filters["pct"] = pct_label


@app.context_processor
def inject_globals():
    return {"footer": FOOTER}


@app.before_request
def require_password():
    expected = os.environ.get("DASHBOARD_PASSWORD")
    if not expected:
        return None
    auth = request.authorization
    if auth and hmac.compare_digest(auth.password or "", expected):
        return None
    return Response("Authentication required", 401, {"WWW-Authenticate": 'Basic realm="Z-List Hackers"'})


def show_exclusion_flag():
    return request.args.get("show_exclusion") == "1"


@app.route("/")
def index():
    stats = data.get_stats()
    state = request.args.get("state", "").strip()
    specialty = request.args.get("specialty", "").strip()
    q = request.args.get("q", "").strip()
    show = show_exclusion_flag()
    try:
        min_score = float(request.args.get("min_score", "") or 0)
    except ValueError:
        min_score = 0.0

    rows = data.ranked_list(
        state=state or None,
        specialty=specialty or None,
        min_score=min_score,
        npi_search=q or None,
        show_exclusion=show,
    )
    total = len(rows)

    return render_template(
        "index.html",
        rows=rows.head(MAX_ROWS).to_dict("records"),
        total=total,
        max_rows=MAX_ROWS,
        states=stats["states"],
        specialties=stats["specialties"],
        state=state,
        specialty=specialty,
        q="" if q.isdigit() else q,
        min_score=min_score,
        show=show,
        query_suffix="?show_exclusion=1" if show else "",
    )


@app.route("/provider/<int:rank>")
def provider(rank):
    npi = data.npi_for_rank(rank)
    if npi is None:
        abort(404)
    show = show_exclusion_flag()
    detail = data.provider_detail(npi, show_exclusion=show)
    if detail is None:
        abort(404)
    detail.pop("npi", None)
    return render_template("provider.html", p=detail, rank=rank, show=show)


@app.route("/explain/<int:rank>", methods=["POST"])
def explain_provider(rank):
    npi = data.npi_for_rank(rank)
    if npi is None:
        abort(404)
    show = show_exclusion_flag()
    detail = data.provider_detail(npi, show_exclusion=show)
    detail.pop("npi", None)
    return render_template("provider.html", p=detail, rank=rank, show=show, explanation=explain.explain(detail))


@app.route("/results")
def results():
    table = pd.read_csv(RESULTS_FILE).to_dict("records") if RESULTS_FILE.exists() else None
    return render_template("results.html", table=table)


if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "8501"))
    if host not in ("127.0.0.1", "localhost") and not os.environ.get("DASHBOARD_PASSWORD"):
        raise SystemExit("Refusing to serve on a non-local address without DASHBOARD_PASSWORD set.")
    app.run(host=host, port=port, debug=False)
