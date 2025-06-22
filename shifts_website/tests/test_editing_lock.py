from __future__ import annotations

import json
import os
from datetime import date

import pytest
from freezegun import freeze_time

from app import db
from app.routes import week_start
from app.models import Shift

TEST_USER = os.getenv("TEST_USER") or "tester@dartmouth.edu"


# ────────────────────────── request helpers ────────────────────────────
def _json_post(client, url: str, payload: dict):
    """
    Make one request with TESTING **disabled** so the real edit-lock
    guard in the view is executed.
    """
    app = client.application
    # remember current values
    old_flag   = app.testing
    old_config = app.config.get("TESTING", False)
    # disable both
    app.testing = False
    app.config["TESTING"] = False
    try:
        return client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            follow_redirects=False,
        )
    finally:
        # restore
        app.testing = old_flag
        app.config["TESTING"] = old_config


def _submit_two(client):
    """Send two distinct shifts so the ‘≥2 shifts’ rule passes."""
    return _json_post(
        client,
        "/submit",
        {
            "shifts": [
                {"slot": 44, "location": "Front1"},
                {"slot": 44, "location": "Front2"},
            ]
        },
    )


def _delete_two(client):
    return _json_post(
        client,
        "/delete",
        {
            "shifts": [
                {"slot": 44, "location": "Front1"},
                {"slot": 44, "location": "Front2"},
            ]
        },
    )


# ────────────────────── seed convenience for /delete ───────────────────
def _seed_two_rows():
    wk = week_start(date(2025, 6, 16))
    db.session.add_all(
        [
            Shift(user_id=1, week=wk, slot=44, location="Front1"),
            Shift(user_id=1, week=wk, slot=44, location="Front2"),
        ]
    )
    db.session.commit()


# ────────────────────────────── tests ──────────────────────────────────
@freeze_time("2025-06-19 23:59", tz_offset=-5)  # Thu 23 : 59 CDT
def test_submit_before_lock(client, login_as):
    login_as(TEST_USER)
    resp = _submit_two(client)
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


@pytest.mark.parametrize(
    "local_ct",  # Chicago-time moments inside the lock window
    [
        "2025-06-20 00:30",  # Fri 00 : 30
        "2025-06-21 12:00",  # Sat noon
        "2025-06-22 03:00",  # Sun 03 : 00
    ],
)
def test_submit_locked(client, login_as, local_ct):
    with freeze_time(local_ct, tz_offset=-5):
        login_as(TEST_USER)
        resp = _submit_two(client)
        assert resp.status_code == 403
        assert "locked" in resp.get_json()["error"].lower()


@pytest.mark.parametrize(
    "local_ct",
    [
        "2025-06-20 00:30",  # Fri inside lock
        "2025-06-22 03:00",  # Sun inside lock
    ],
)
def test_delete_locked(client, login_as, local_ct):
    _seed_two_rows()  # ensure something exists to delete
    with freeze_time(local_ct, tz_offset=-5):
        login_as(TEST_USER)
        resp = _delete_two(client)
        assert resp.status_code == 403
        assert "locked" in resp.get_json()["error"].lower()
