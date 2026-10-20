# pyright: basic
# (django-stubs types model fields for mypy's plugin; strict pyright cannot read them)
"""Every Business's calls, minutes and dollars per month and kind: the totals page and the operator's list_totals (VOI-116)."""

from collections import defaultdict
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth

from portal.accounts.models import CALL_KINDS, CallRecord

Total = tuple[int, str, str, int]  # calls, minutes, dollars, calls with no cost


def totals_by_month() -> list[tuple[str, str, dict[str, Total]]]:
    """(month, Business name, a total per call kind), newest month first, on the Portal's clock."""
    month = TruncMonth("started_at", tzinfo=ZoneInfo(settings.TIME_ZONE))
    sums = (
        CallRecord.objects.annotate(month=month)
        .values("month", "business_id", "business__name", "kind")
        .annotate(
            calls=Count("id"),
            seconds=Sum("length_seconds"),
            dollars=Sum("cost_usd"),
            unpriced=Count("id", filter=Q(cost_usd__isnull=True)),
        )
    )
    by_row: dict[tuple[Any, int, str], dict[str, tuple[int, str, str, int]]] = (
        defaultdict(dict)
    )
    for s in sums:
        by_row[(s["month"], s["business_id"], s["business__name"])][s["kind"]] = (
            s["calls"],
            f"{s['seconds'] / 60:.1f}",
            f"{s['dollars'] or Decimal(0):.4f}",
            s["unpriced"],
        )
    empty = (0, "0.0", "0.0000", 0)
    return [
        (
            month.strftime("%Y-%m"),
            name,
            {kind: kinds.get(kind, empty) for kind in CALL_KINDS},
        )
        for (month, _, name), kinds in sorted(
            by_row.items(), key=lambda r: (-r[0][0].timestamp(), r[0][2], r[0][1])
        )
    ]
