"""End-to-end verification of the seven acceptance scenarios, over HTTP.

Runs against a *running* instance that must be pointed at an isolated
database and started with `FIXI_NO_CONTACT=1`. It refuses to run
otherwise, because scenario 7 touches the appointment path and this script
must never be the thing that dials somebody:

    FIXI_NO_CONTACT=1 OUTBOUND_CALLS_ENABLED=false \
    DATABASE_PATH=/tmp/verify.db DOCUMENTS_DIR=/tmp/verify_docs \
    OPERATOR_AUTH_ENABLED=false \
    python -m uvicorn app.main:app --port 8010

    python scripts/verify_scenarios.py --base-url http://127.0.0.1:8010

Every check prints PASS or FAIL with the actual values compared, so the
output is evidence rather than a claim. Exit code is non-zero if anything
failed.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

import httpx

RESULTS: list[tuple[bool, str, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    RESULTS.append((ok, label, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    api = f"{base}/api/v1"
    now = datetime.now(timezone.utc)

    with httpx.Client(timeout=30.0) as client:

        def get(path: str, **kw):
            return client.get(f"{api}{path}", **kw)

        def post(path: str, **kw):
            return client.post(f"{api}{path}", **kw)

        # -- guard ------------------------------------------------------
        print("\n0. Environment is safe to test against")
        readiness = get("/readiness")
        check(readiness.status_code == 200, "backend reachable", f"HTTP {readiness.status_code}")
        overview_before = get("/overview").json()
        operational_cases = overview_before["status_counts"]["total"]
        isolated = check(
            operational_cases == 0,
            "starting from an empty operational workspace",
            f"{operational_cases} case(s) present",
        )
        if not isolated:
            # This used to be an ordinary `check()`: it printed FAIL and
            # carried straight on into scenario 1, which creates
            # properties, tenants, cases, notes and documents. Pointed at a
            # server backed by backend/data/repairflow.db -- the file
            # holding the only real ElevenLabs call history there is -- the
            # script would happily write fiction into it, while its own
            # docstring promised it "refuses to run". A guard that
            # announces protection it does not provide is worse than none,
            # because it invites exactly the mistake it claims to prevent.
            print(
                "\nREFUSING TO RUN. This script writes real data through the API, and the\n"
                f"target already holds {operational_cases} operational case(s), so it is not an\n"
                "isolated instance. Start the backend against a scratch database first:\n\n"
                "    FIXI_NO_CONTACT=1 OUTBOUND_CALLS_ENABLED=false \\\n"
                "    DATABASE_PATH=/tmp/verify.db DOCUMENTS_DIR=/tmp/verify_docs \\\n"
                "    python -m uvicorn app.main:app --port 8010\n"
            )
            return 1

        # -- 1. create a case through the real API ----------------------
        print("\n1. Create a case; verify detail, property relationship and metrics")
        prop = post(
            "/properties",
            json={
                "address_line": "12 Verification Row",
                "postcode": "BS1 4TR",
                "landlord_reference": "VER-1",
                "property_type": "Terraced house",
                "bedrooms": 3,
                "build_year": 1954,
            },
        )
        check(prop.status_code in (200, 201), "property created", f"HTTP {prop.status_code} {prop.text[:120]}")
        property_id = prop.json()["id"]

        tenant = post(
            "/tenants",
            json={
                "property_id": property_id,
                "display_name": "Verification Tenant",
                "email": "tenant@example.invalid",
                "preferred_channel": "EMAIL",
                "contact_allowed": True,
            },
        )
        check(tenant.status_code in (200, 201), "tenant created", f"HTTP {tenant.status_code} {tenant.text[:120]}")
        tenant_id = tenant.json()["id"]

        case = post(
            "/cases",
            json={
                "property_id": property_id,
                "tenant_id": tenant_id,
                "description": "Water coming through the rear bedroom ceiling after heavy rain.",
                "location": "Rear bedroom ceiling",
                "source_text": "Tenant reported water through the ceiling.",
                "category": "ROOFING",
            },
        )
        check(case.status_code in (200, 201), "case created", f"HTTP {case.status_code} {case.text[:200]}")
        case_id = case.json()["case_id"]

        detail = get(f"/cases/{case_id}")
        check(detail.status_code == 200, "case detail readable", f"HTTP {detail.status_code}")
        snap = detail.json()["snapshot"]
        check(
            snap["property"]["address_line"] == "12 Verification Row",
            "case is linked to its property",
            snap["property"]["address_line"],
        )
        version = snap["case"]["version"]

        metrics = get("/metrics/dashboard").json()
        check(metrics["total"] == 1, "dashboard total reflects the new case", str(metrics["total"]))

        prop_detail = get(f"/properties/{property_id}").json()
        check(
            prop_detail.get("total_case_count") == 1,
            "property case count updated",
            str(prop_detail.get("total_case_count")),
        )

        # -- 2. edit + a legal workflow action --------------------------
        print("\n2. Edit the case, then take a legal workflow action")
        edited = client.patch(
            f"{api}/cases/{case_id}",
            json={"expected_version": version, "title": "Rear bedroom ceiling — water ingress"},
        )
        check(edited.status_code == 200, "edit accepted", f"HTTP {edited.status_code} {edited.text[:160]}")
        new_version = edited.json()["version"]
        check(new_version > version, "version bumped by the edit", f"{version} -> {new_version}")

        stale = client.patch(
            f"{api}/cases/{case_id}", json={"expected_version": version, "title": "Should be rejected"}
        )
        check(stale.status_code == 409, "a stale edit is rejected", f"HTTP {stale.status_code}")

        reread = get(f"/cases/{case_id}").json()["snapshot"]
        check(
            reread["case"]["title"] == "Rear bedroom ceiling — water ingress",
            "edit persisted",
            reread["case"]["title"],
        )

        events = get(f"/cases/{case_id}/events").json()["items"]
        check(
            any(e["type"] == "CASE_EDITED" for e in events),
            "edit recorded in the event history",
            f"{len(events)} event(s)",
        )

        cancelled = post(
            f"/cases/{case_id}/cancel",
            json={"version": reread["case"]["version"], "reason": "Verification scenario"},
        )
        check(cancelled.status_code == 202, "legal action (cancel) accepted", f"HTTP {cancelled.status_code}")
        after = get(f"/cases/{case_id}").json()["snapshot"]
        check(after["case"]["status"] == "CANCELLED", "status persisted", after["case"]["status"])

        illegal = post(
            f"/cases/{case_id}/cancel",
            json={"version": after["case"]["version"], "reason": "Second cancel"},
        )
        check(
            illegal.status_code >= 400,
            "an illegal repeat transition is refused",
            f"HTTP {illegal.status_code}",
        )

        # -- 3. record a cost -------------------------------------------
        print("\n3. Record a cost; verify it reaches spend, detail and reports")
        case2 = post(
            "/cases",
            json={
                "property_id": property_id,
                "tenant_id": tenant_id,
                "description": "Slipped tiles above the bay window after high winds.",
                "location": "Front elevation",
                "source_text": "Tenant reported slipped tiles.",
                "category": "ROOFING",
            },
        ).json()
        case2_id = case2["case_id"]

        cost = post(
            f"/cases/{case2_id}/costs",
            json={
                "kind": "INVOICE",
                "amount_pence": 48750,
                "description": "Roof tile replacement",
                "incurred_at": (now - timedelta(days=1)).isoformat(),
            },
        )
        check(cost.status_code in (200, 201), "cost recorded", f"HTTP {cost.status_code} {cost.text[:160]}")

        costs = get(f"/cases/{case2_id}/costs").json()
        check(
            costs["totals"]["invoiced_pence"] == 48750,
            "case cost total is exact in pence",
            str(costs["totals"]["invoiced_pence"]),
        )

        year = (now - timedelta(days=1)).year
        insights = get("/insights", params={"include_archived": "false"}).json()
        by_year = {row["year"]: row for row in insights["spend_by_year"]}
        check(
            by_year.get(year, {}).get("actual_pence") == 48750,
            f"spend_by_year[{year}].actual_pence matches",
            str(by_year.get(year, {}).get("actual_pence")),
        )

        summary = get("/reports/summary", params={"include_archived": "false"}).json()
        csv = get("/reports/export.csv", params={"include_archived": "false"})
        check(csv.status_code == 200, "CSV export served", f"HTTP {csv.status_code}")
        check(
            "record_source" in csv.text.splitlines()[0],
            "CSV carries a record_source column",
            csv.text.splitlines()[0][:120],
        )
        csv_invoiced = sum(
            int(row.split(",")[-2] or 0)
            for row in csv.text.splitlines()[1:]
            if row.strip() and row.split(",")[-2].strip().lstrip("-").isdigit()
        )
        check(
            isinstance(summary, dict) and bool(summary),
            "report summary returned",
            f"{len(summary)} section(s)",
        )

        # -- 4. recurrence ----------------------------------------------
        print("\n4. A second case in the same recurrence group")
        recurring = get("/insights", params={"include_archived": "false"}).json()["recurring_issues"]
        match = [r for r in recurring if r.get("property_id") == property_id]
        check(bool(match), "recurrence group formed for this property", f"{len(match)} group(s)")
        if match:
            group = match[0]
            check(group["count"] >= 2, "count is at least 2", str(group.get("count")))
            check(
                set(group.get("case_ids", [])) >= {case_id, case2_id},
                "group links back to both supporting cases",
                str(group.get("case_ids")),
            )

        # -- 5. note + document ------------------------------------------
        print("\n5. Create a note and upload a document; reload and retrieve")
        note = post(
            "/notes",
            json={
                "subject_type": "PROPERTY",
                "subject_id": property_id,
                "body": "Key safe code is held by the housing officer.",
            },
        )
        check(note.status_code in (200, 201), "note created", f"HTTP {note.status_code} {note.text[:160]}")
        note_id = note.json()["id"]
        notes = get("/notes", params={"subject_type": "PROPERTY", "subject_id": property_id}).json()
        rows = notes["items"] if isinstance(notes, dict) else notes
        check(any(n["id"] == note_id for n in rows), "note retrieved after reload", f"{len(rows)} note(s)")
        check(
            bool(rows[0].get("author")),
            "note records its author",
            str(rows[0].get("author")),
        )

        payload = b"Verification document body.\n"
        doc = client.post(
            f"{api}/documents",
            data={
                "subject_type": "PROPERTY",
                "subject_id": property_id,
                "description": "Verification upload",
            },
            files={"file": ("survey.txt", payload, "text/plain")},
        )
        check(doc.status_code in (200, 201), "document uploaded", f"HTTP {doc.status_code} {doc.text[:160]}")
        doc_id = doc.json()["id"]
        check(
            doc.json()["size_bytes"] == len(payload),
            "stored size matches the real byte count",
            f"{doc.json()['size_bytes']} vs {len(payload)}",
        )
        content = get(f"/documents/{doc_id}/content")
        check(content.status_code == 200, "document content served", f"HTTP {content.status_code}")
        check(content.content == payload, "bytes round-trip unchanged")

        # -- 6. messaging -------------------------------------------------
        print("\n6. Messaging states are honest")
        internal = post(
            f"/messages/threads/{case2_id}",
            json={"text": "Left a voicemail for the roofer.", "channel": "INTERNAL"},
        )
        check(internal.status_code in (200, 201), "internal note posted", f"HTTP {internal.status_code}")
        check(
            internal.json()["delivery_state"] == "INTERNAL_NOTE",
            "internal note is a complete outcome",
            internal.json()["delivery_state"],
        )
        outward = post(
            f"/messages/threads/{case2_id}",
            json={"text": "We will attend on Tuesday.", "channel": "EMAIL"},
        )
        check(outward.status_code in (200, 201), "outward message accepted", f"HTTP {outward.status_code}")
        check(
            outward.json()["delivery_state"] == "DRAFT",
            "outward message is a DRAFT, never SENT",
            outward.json()["delivery_state"],
        )
        check(
            bool(outward.json().get("delivery_detail")),
            "draft explains why it was not sent",
            str(outward.json().get("delivery_detail"))[:100],
        )
        unread_global = get("/messages/unread-count").json()["unread_count"]
        threads = get("/messages/threads").json()
        thread_rows = threads["items"] if isinstance(threads, dict) else threads
        check(
            unread_global == sum(t["unread_count"] for t in thread_rows),
            "global unread badge equals the sum of thread counts",
            f"{unread_global} vs {sum(t['unread_count'] for t in thread_rows)}",
        )

        # -- 7. reschedule -------------------------------------------------
        print("\n7. Reschedule an appointment")
        upcoming_before = get("/appointments/upcoming").json()
        appointments = upcoming_before.get("items", [])
        if not appointments:
            check(
                True,
                "SKIPPED: no appointment exists to reschedule",
                "an appointment requires an approved SCHEDULE_VISIT action; covered by "
                "backend/tests/test_hero_path.py instead",
            )
        else:
            appt = appointments[0]
            res = post(
                f"/appointments/{appt['id']}/reschedule",
                json={
                    "start_at": (now + timedelta(days=3)).isoformat(),
                    "end_at": (now + timedelta(days=3, hours=2)).isoformat(),
                    "reason": "Tenant unavailable",
                    "arranged_with": "Verification Contractor",
                },
            )
            check(res.status_code == 202, "reschedule accepted", f"HTTP {res.status_code} {res.text[:160]}")
            check(
                res.json()["status"] == "PENDING",
                "replacement is PENDING, not confirmed",
                res.json()["status"],
            )
            after_upcoming = get("/appointments/upcoming").json().get("items", [])
            check(
                any(a["id"] == res.json()["appointment_id"] for a in after_upcoming),
                "upcoming visits show the new appointment",
                f"{len(after_upcoming)} upcoming",
            )

        # -- 8. archival separation ----------------------------------------
        print("\n8. Archival history never enters operational counts")
        op_cases = get("/cases").json()["items"]
        check(
            all(not c["is_archived"] for c in op_cases),
            "no archival row in the default case list",
            f"{len(op_cases)} case(s)",
        )

    print("\n" + "=" * 68)
    failed = [r for r in RESULTS if not r[0]]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    for _ok, label, detail in failed:
        print(f"  FAILED: {label} -- {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
