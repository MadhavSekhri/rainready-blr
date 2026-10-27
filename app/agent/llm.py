"""Optional: rewrite the situation brief with IBM Granite on watsonx.ai.

Set WATSONX_APIKEY, WATSONX_PROJECT_ID (and optionally WATSONX_URL,
WATSONX_MODEL). Without them, the deterministic brief is used, so the app
always works offline and in tests.
"""
from __future__ import annotations

import os

import httpx

DEFAULT_URL = "https://us-south.ml.cloud.ibm.com"
DEFAULT_MODEL = "ibm/granite-3-8b-instruct"


def enabled() -> bool:
    return bool(os.getenv("WATSONX_APIKEY") and os.getenv("WATSONX_PROJECT_ID"))


def _token(apikey: str) -> str:
    r = httpx.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": apikey},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def polish_brief(brief: str) -> tuple[str, str]:
    """Return (text, engine). Falls back silently on any error."""
    if not enabled():
        return brief, "rules"
    try:
        token = _token(os.environ["WATSONX_APIKEY"])
        prompt = (
            "You are the duty officer of a Bengaluru flood control room. Rewrite this machine "
            "situation brief as 3 short, plain sentences for ward engineers. Keep every number.\n\n"
            f"Brief: {brief}\n\nRewritten:"
        )
        r = httpx.post(
            f"{os.getenv('WATSONX_URL', DEFAULT_URL)}/ml/v1/text/generation?version=2023-05-29",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model_id": os.getenv("WATSONX_MODEL", DEFAULT_MODEL),
                "project_id": os.environ["WATSONX_PROJECT_ID"],
                "input": prompt,
                "parameters": {"decoding_method": "greedy", "max_new_tokens": 180},
            },
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["results"][0]["generated_text"].strip()
        return (text or brief), "granite"
    except Exception:
        return brief, "rules"
