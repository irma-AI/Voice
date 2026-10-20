"""A destructive Command waits for the Business's approval in the Portal (VOI-239, make test-db). No mocks of our own code.

The Commands run on the SDK's worker threads with their own database connection, so these tests commit (transaction=True).
"""

# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)

import logging
import threading
import time
from datetime import timedelta
from typing import Any, get_args

import pytest
from django.db import IntegrityError, connection, transaction
from django.test import Client

from portal.accounts import changes, views
from portal.accounts.models import CHANGE_KINDS, CommandRecord, Module, PendingChange
from tests.portal.helpers import business_with_login
from tests.portal.test_agent_endpoint import a_token, ask

pytestmark = [pytest.mark.db, pytest.mark.django_db(transaction=True)]

ADDRESS = "https://8.8.8.8/mcp"


def remove(secret: str, name: str) -> dict[str, Any]:
    answer = ask(
        "tools/call", {"name": "remove_module", "arguments": {"name": name}}, secret
    )
    assert answer.status_code == 200, answer.content
    return answer.json()["result"]


def decided(client: Client, change: PendingChange, decision: str) -> str:
    """Approve or Reject on the page: it always goes back to the page, which says what happened."""
    answer = client.post(f"/changes/{change.pk}/{decision}/")
    assert answer.status_code == 302 and answer["Location"] == "/changes/"
    return client.get(answer["Location"]).content.decode()


def audited(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "portal.audit"]


def a_business_with_a_module(
    email: str = "user-a@example.com",
) -> tuple[Client, str, Module]:
    business, client = business_with_login(email, "Owner's Salon")
    module = Module.objects.create(business=business, name="Bookings", url=ADDRESS)
    return client, a_token(business, "full"), module


def test_removing_a_module_is_staged_and_only_the_businesss_approval_removes_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="portal.audit")
    client, secret, module = a_business_with_a_module()
    answer = remove(secret, "Bookings")
    staged = answer["structuredContent"]
    change = PendingChange.objects.get()
    assert not answer.get("isError")
    assert staged["staged"] is True and staged["change"] == change.pk
    assert staged["preview"] == "Remove the Module “Bookings”"
    assert staged["risk_level"] == "medium"
    assert "/changes/" in staged["next"] and "approve" in staged["next"]
    assert Module.objects.filter(pk=module.pk).exists()  # nothing changed yet
    assert CommandRecord.objects.get().result == "staged"
    assert "Remove the Module “Bookings”" in client.get("/changes/").content.decode()

    assert views.OUTCOMES["applied"] in decided(client, change, "approve")
    assert not Module.objects.filter(pk=module.pk).exists()
    assert PendingChange.objects.get().decision == "approved"
    # A second approval is refused and nothing is left on the page to approve.
    page = decided(client, change, "approve")
    assert views.OUTCOMES["already_decided"] in page and "Remove the Module" not in page
    assert audited(caplog) == [
        f"staged pending change {change.pk} (remove_module) for business {module.business.pk} by token {change.token.pk}",
        f"approved pending change {change.pk} (remove_module) for business {module.business.pk} by account {module.business.account_id}",
    ]  # ids only: no Module name, email or Business name


def test_a_rejected_change_never_applies(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="portal.audit")
    client, secret, module = a_business_with_a_module()
    remove(secret, "Bookings")
    change = PendingChange.objects.get()
    assert views.OUTCOMES["rejected"] in decided(client, change, "reject")
    assert views.OUTCOMES["already_decided"] in decided(client, change, "approve")
    assert Module.objects.filter(pk=module.pk).exists()
    assert PendingChange.objects.get().decision == "rejected"
    assert audited(caplog)[-1].startswith(
        f"rejected pending change {change.pk} (remove_module)"
    )


def test_another_business_can_neither_see_nor_decide_a_change() -> None:
    _, secret, module = a_business_with_a_module()
    remove(secret, "Bookings")
    change = PendingChange.objects.get()
    _, other = business_with_login("user-b@example.com", "Owner B's Garage")
    assert "Bookings" not in other.get("/changes/").content.decode()
    for decision in ("approve", "reject"):
        assert other.post(f"/changes/{change.pk}/{decision}/").status_code == 404
    assert Module.objects.filter(pk=module.pk).exists()
    assert PendingChange.objects.get().decision == ""


def test_a_decision_must_be_a_post_behind_the_login() -> None:
    client, secret, module = a_business_with_a_module()
    remove(secret, "Bookings")
    change = PendingChange.objects.get()
    assert client.get(f"/changes/{change.pk}/approve/").status_code == 302
    assert Client().post(f"/changes/{change.pk}/approve/").status_code == 302
    assert Module.objects.filter(pk=module.pk).exists()
    assert PendingChange.objects.get().decision == ""


def test_another_businesss_module_or_an_unknown_one_stages_nothing() -> None:
    _, secret, _ = a_business_with_a_module()
    a_business_with_a_module("user-b@example.com")  # also has a "Bookings"
    Module.remove(Module.objects.filter(business__account__email="user-a@example.com"))
    for name in ("Bookings", "Nothing by this name"):
        answer = remove(secret, name)
        assert answer["isError"]
        assert (
            answer["content"][0]["text"] == "Your Business has no Module by that name."
        )
    assert not PendingChange.objects.exists()


def stage_one() -> PendingChange:
    _, secret, _ = a_business_with_a_module()
    remove(secret, "Bookings")
    return PendingChange.objects.get()


# What changes.decide sets before it decides; the database refuses a decision without it.
GATE = "SELECT set_config('voice.change_decide', 'on', true); "


def refused(statement: str, rule: str) -> None:
    with (
        pytest.raises(IntegrityError, match=rule),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(statement)


def test_the_database_applies_a_change_once_and_never_after_it_was_rejected() -> None:
    stage_one()
    decide = "UPDATE accounts_pendingchange SET decision = '{}', decided_at = statement_timestamp()"
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(GATE + decide.format("rejected"))
    for decision in ("approved", "rejected"):
        refused(GATE + decide.format(decision), "pending_change_is_decided_once")


def test_the_database_keeps_a_change_as_it_was_staged() -> None:
    stage_one()
    for statement, rule in (
        (
            "UPDATE accounts_pendingchange SET target = '{\"module\": 1}'",
            "pending_change_is_decided_once",
        ),
        (
            "UPDATE accounts_pendingchange SET decision = 'approved', decided_at = now() - interval '1 day'",
            "pending_change_decided_at_is_the_databases_clock",
        ),
        (
            GATE
            + "UPDATE accounts_pendingchange SET id = id + 1000, decision = 'rejected', decided_at = statement_timestamp()",
            "pending_change_is_decided_once",
        ),
        (  # an approval anywhere but changes.decide would leave the Module in place
            "UPDATE accounts_pendingchange SET decision = 'approved', decided_at = statement_timestamp()",
            "pending_change_is_decided_in_the_portal",
        ),
        ("DELETE FROM accounts_pendingchange", "pending_change_is_kept"),
    ):
        refused(statement, rule)
    assert PendingChange.objects.get().decision == ""


def test_the_database_refuses_to_approve_an_expired_change() -> None:
    change = stage_one()
    with (
        connection.cursor() as cursor
    ):  # a change staged a week ago: only a test may write that time
        cursor.execute("SET session_replication_role = replica")
        cursor.execute(
            "UPDATE accounts_pendingchange SET staged_at = statement_timestamp() - %s::interval",
            [f"{changes.WAITS.total_seconds()} seconds"],
        )
        cursor.execute("SET session_replication_role = DEFAULT")
    refused(
        GATE
        + "UPDATE accounts_pendingchange SET decision = 'approved', decided_at = statement_timestamp()",
        "pending_change_has_expired",
    )
    client = Client()
    client.force_login(change.token.business.account)
    assert "Bookings" not in client.get("/changes/").content.decode()
    assert views.OUTCOMES["expired"] in decided(client, change, "approve")
    assert Module.objects.exists()


def test_the_database_stages_a_change_undecided_at_its_own_clock() -> None:
    change = stage_one()
    insert = (
        "INSERT INTO accounts_pendingchange (token_id, kind, target, staged_at, decision) "
        "VALUES ({}, 'remove_module', '{{}}', {}, '{}')"
    )
    refused(
        insert.format(change.token.pk, "now() - interval '1 hour'", ""),
        "pending_change_staged_at_is_the_databases_clock",
    )
    refused(
        insert.format(change.token.pk, "statement_timestamp()", "approved"),
        "pending_change_is_staged_undecided",
    )
    refused(
        insert.format(change.token.pk, "statement_timestamp()", "").replace(
            "'remove_module'", "'drop_everything'"
        ),
        "pending_change_kind_must_be_a_known_kind",
    )


def test_a_change_can_be_approved_until_its_last_minute() -> None:
    """With the test above, the database's 7 days and changes.WAITS agree: edit both together."""
    change = stage_one()
    with connection.cursor() as cursor:
        cursor.execute("SET session_replication_role = replica")
        cursor.execute(
            "UPDATE accounts_pendingchange SET staged_at = statement_timestamp() - %s::interval",
            [f"{(changes.WAITS - timedelta(minutes=1)).total_seconds()} seconds"],
        )
        cursor.execute("SET session_replication_role = DEFAULT")
    client = Client()
    client.force_login(change.token.business.account)
    assert "Bookings" in client.get("/changes/").content.decode()
    assert views.OUTCOMES["applied"] in decided(client, change, "approve")
    assert not Module.objects.exists()


def test_every_kind_of_change_has_its_preview_risk_and_way_to_apply() -> None:
    """A sweep: a kind the database accepts must be in changes.Kind (whose closed matches preview and apply it) and changes.RISK."""
    assert set(CHANGE_KINDS) == set(get_args(changes.Kind)) == set(changes.RISK), (
        "add the kind to models.CHANGE_KINDS, changes.Kind and changes.RISK, then handle it in changes.preview and changes._apply"
    )


def test_approving_a_removal_whose_module_is_already_gone_changes_nothing_else(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="portal.audit")
    client, secret, module = a_business_with_a_module()
    remove(secret, "Bookings")
    change = PendingChange.objects.get()
    client.post(f"/modules/{module.pk}/remove/")
    again = Module.objects.create(
        business=module.business, name="Bookings", url=ADDRESS
    )
    assert views.OUTCOMES["nothing_left"] in decided(client, change, "approve")
    assert Module.objects.filter(
        pk=again.pk
    ).exists()  # the change named the Module that was, not its name
    assert audited(caplog)[-1].endswith(": nothing left to change")


def test_a_change_keeps_no_module_name_and_revoking_its_token_cancels_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Offboarding revokes every token and removes the Modules: a change it leaves holds no name and is cancelled."""
    caplog.set_level(logging.INFO, logger="portal.audit")
    client, secret, module = a_business_with_a_module()
    remove(secret, "Bookings")
    change = PendingChange.objects.get()
    assert change.target == {"module": module.pk}
    change.token.revoke()
    assert PendingChange.objects.get().decision == "cancelled"
    assert (
        audited(caplog)[-1]
        == f"cancelled pending changes [{change.pk}] with the revoke of token {change.token.pk}"
    )
    assert "Bookings" not in client.get("/changes/").content.decode()
    for decision in ("approve", "reject"):
        assert views.OUTCOMES["cancelled"] in decided(client, change, decision)
    assert Module.objects.filter(pk=module.pk).exists()


def test_only_a_revoke_cancels_and_a_revoked_token_stages_nothing() -> None:
    change = stage_one()
    refused(
        GATE
        + "UPDATE accounts_pendingchange SET decision = 'cancelled', decided_at = statement_timestamp()",
        "pending_change_is_cancelled_by_its_tokens_revoke",
    )
    change.token.revoke()
    refused(
        f"INSERT INTO accounts_pendingchange (token_id, kind, target, staged_at, decision) "
        f"VALUES ({change.token.pk}, 'remove_module', '{{}}', statement_timestamp(), '')",
        "pending_change_token_is_revoked",
    )


def test_every_outcome_of_a_decision_has_its_words() -> None:
    assert set(views.OUTCOMES) == set(get_args(changes.Decided))


def test_a_link_cannot_show_an_outcome_that_did_not_happen() -> None:
    client, _, _ = a_business_with_a_module()
    page = client.get(
        "/changes/?outcome=applied&change_outcome=applied"
    ).content.decode()
    assert not any(words in page for words in views.OUTCOMES.values())


def test_a_revoke_racing_an_approval_logs_only_what_it_cancelled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="portal.audit")
    change = stage_one()
    token = change.token
    holding, release = threading.Event(), threading.Event()

    def approve() -> (
        None
    ):  # an approval that holds the change's row lock while the revoke waits on it
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    GATE
                    + f"UPDATE accounts_pendingchange SET decision = 'approved', decided_at = statement_timestamp() WHERE id = {change.pk}"
                )
                holding.set()
                release.wait(10)
        finally:
            connection.close()

    def revoke() -> None:
        try:
            token.revoke()
        finally:
            connection.close()

    approving = threading.Thread(target=approve)
    approving.start()
    assert holding.wait(10)
    revoking = threading.Thread(target=revoke)
    revoking.start()
    time.sleep(0.3)  # the revoke is now waiting on the change's row
    release.set()
    approving.join(10)
    revoking.join(10)
    assert PendingChange.objects.get().decision == "approved"
    assert not any("cancelled" in line for line in audited(caplog))
