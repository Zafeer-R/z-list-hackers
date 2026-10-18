"""IBM Granite explanation for one provider. No UI imports.

Sends only the provider's specialty, state, scores and reasons, never an NPI or pseudonym.
Credentials come from the environment and are never written to disk:
IBM_API_KEY (preferred, tokens are refreshed automatically) or IBM_ACCESS_TOKEN (expires in about an hour).
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

BANNED_WORDS = re.compile(r"\b(fraud\w*|kickback\w*|banned)\b", re.IGNORECASE)
WITHHELD = "Explanation withheld: the generated wording did not pass the review wording check."
IAM_URL = "https://iam.cloud.ibm.com/identity/token"

_cached_token = None
_cached_expiry = 0.0


def access_token():
    """Return a valid IAM token, refreshing it from IBM_API_KEY a few minutes before it expires."""
    global _cached_token, _cached_expiry
    api_key = os.environ.get("IBM_API_KEY")
    if not api_key:
        return os.environ.get("IBM_ACCESS_TOKEN")
    if _cached_token and time.time() < _cached_expiry - 300:
        return _cached_token
    body = urllib.parse.urlencode({
        "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
        "apikey": api_key,
    }).encode("utf-8")
    request = urllib.request.Request(
        IAM_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        token = json.load(response)
    _cached_token = token["access_token"]
    _cached_expiry = float(token.get("expiration", time.time() + 3600))
    return _cached_token


def build_prompt(p):
    lines = [
        "You are an evidence-grounded assistant for Z-List Hackers, a Medicare Part D prescribing "
        "anomaly review project. Explain in under 100 words why the following provider may warrant "
        "further review. Use only the provided indicators. Do not accuse the provider, do not use "
        "the words fraud or kickback, do not claim regulatory violations, do not invent clinical facts, "
        "and do not describe the score as a probability. Say that legitimate clinical and "
        "patient-population explanations may exist.",
        "",
        f"Specialty: {p['specialty']}",
        f"State: {p['state']}",
        f"Combined score (0 to 100, higher means more unusual): {p['combined_score']:.2f}",
        f"Measures in the top 10% of peers: {p['rules_score']} of 8",
        "Indicators:",
    ]
    lines += [f"{i}. {r['text']}" for i, r in enumerate(p["reasons"], 1)]
    return "\n".join(lines)


def explain(p):
    try:
        token = access_token()
    except (urllib.error.URLError, KeyError, ValueError):
        return "Granite could not sign in to IBM Cloud. Check IBM_API_KEY and the network connection."
    if not token:
        return "Granite explanations are off: set IBM_API_KEY (or IBM_ACCESS_TOKEN) on this machine."

    payload = {
        "model_id": config.GRANITE_MODEL,
        "project_id": config.GRANITE_PROJECT_ID,
        "messages": [{"role": "user", "content": build_prompt(p)}],
        "temperature": 0,
        "max_tokens": 200,
    }
    request = urllib.request.Request(
        config.GRANITE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = json.load(response)["choices"][0]["message"]["content"]
    except urllib.error.URLError:
        return "Granite could not be reached. Check the network connection and the token."
    except (KeyError, IndexError, ValueError):
        return "Granite returned an unexpected response."

    if BANNED_WORDS.search(text):
        return WITHHELD
    return text.strip()
