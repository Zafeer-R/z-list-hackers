"""Flask UI only. All data logic lives in app/data.py."""

import os

from flask import Flask, abort, render_template, request

from app import data

MAX_ROWS = 200
FOOTER = "Scores flag statistically unusual prescribing for review. They are not findings of wrongdoing."

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


@app.route("/")
def index():
    stats = data.get_stats()
    state = request.args.get("state", "").strip()
    specialty = request.args.get("specialty", "").strip()
    q = request.args.get("q", "").strip()
    try:
        min_score = float(request.args.get("min_score", "") or 0)
    except ValueError:
        min_score = 0.0

    rows = data.ranked_list(
        state=state or None,
        specialty=specialty or None,
        min_score=min_score,
        npi_search=q or None,
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
        q=q,
        min_score=min_score,
    )


@app.route("/provider/<int:rank>")
def provider(rank):
    npi = data.npi_for_rank(rank)
    if npi is None:
        abort(404)
    detail = data.provider_detail(npi)
    if detail is None:
        abort(404)
    detail.pop("npi", None)
    return render_template("provider.html", p=detail, rank=rank)


if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "8501"))
    app.run(host=host, port=port, debug=False)
