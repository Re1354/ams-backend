"""
Correct ExamSchedule times entered before the TIME_ZONE switch.

settings.TIME_ZONE was changed from 'UTC' to 'Asia/Dhaka' (UTC+6) in commit
17c9cb1 (2026-07-06 02:00:58 +06 = 2026-07-05 20:00:58 UTC). With USE_TZ=True,
a naive datetime entered *before* the switch was interpreted as UTC, so a
schedule intended for e.g. 2:00 PM Dhaka was stored as 2:00 PM UTC = 8:00 PM
Dhaka — 6 hours late. That shifts when `schedule.end_time <= now` trips, which
is what gates absentee generation.

This is DELIBERATELY a management command, not an auto-applied migration: the
correction depends on how schedules were entered, so it must be eyeballed on
real data first. It is a DRY RUN by default and only writes with --apply.

  # inspect what would change (safe, read-only)
  python manage.py fix_pre_switch_schedule_times

  # apply the -6h correction after confirming the list looks right
  python manage.py fix_pre_switch_schedule_times --apply

  # undo (shift the same rows back +6h)
  python manage.py fix_pre_switch_schedule_times --apply --hours 6
"""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from mainapp.models import ExamSchedule


# 2026-07-06 02:00:58 +06 == 2026-07-05 20:00:58 UTC
TZ_SWITCH_INSTANT = datetime(2026, 7, 5, 20, 0, 58, tzinfo=dt_timezone.utc)


class Command(BaseCommand):
    help = (
        "Shift ExamSchedule start/end times that were entered before the "
        "UTC->Asia/Dhaka TIME_ZONE switch and whose window is still open. "
        "Dry run by default; pass --apply to write."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write the shift (default is a read-only dry run).",
        )
        parser.add_argument(
            "--hours",
            type=int,
            default=-6,
            help="Hours to shift (default -6; use 6 to reverse a prior --apply).",
        )
        parser.add_argument(
            "--include-ended",
            action="store_true",
            help=(
                "Also shift schedules whose window already ended. Off by "
                "default: an already-ended window's status is already settled."
            ),
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        hours = options["hours"]
        include_ended = options["include_ended"]
        now = timezone.now()
        delta = timedelta(hours=hours)

        qs = ExamSchedule.objects.filter(created_at__lt=TZ_SWITCH_INSTANT)
        if not include_ended:
            qs = qs.filter(end_time__gt=now)
        qs = qs.order_by("end_time")

        count = qs.count()
        mode = f"APPLY ({hours:+d}h)" if apply else "DRY RUN"
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"[{mode}] {count} pre-switch schedule(s) "
                f"{'(including ended)' if include_ended else '(still-open only)'}"
            )
        )
        self.stdout.write(
            "id | created_at(UTC) | end_time now (local) | end_time after (local)"
        )
        for schedule in qs:
            after_end = schedule.end_time + delta if schedule.end_time else None
            self.stdout.write(
                f"  {schedule.id} | "
                f"{schedule.created_at.astimezone(dt_timezone.utc):%Y-%m-%d %H:%M} | "
                f"{self._local(schedule.end_time)} | {self._local(after_end)}"
            )

        if not apply:
            self.stdout.write(
                self.style.WARNING(
                    "Dry run only — nothing written. Re-run with --apply once the "
                    "list above matches the intended wall-clock times."
                )
            )
            return

        with transaction.atomic():
            updated = 0
            for schedule in qs:
                if schedule.start_time:
                    schedule.start_time = schedule.start_time + delta
                if schedule.end_time:
                    schedule.end_time = schedule.end_time + delta
                schedule.save(update_fields=["start_time", "end_time"])
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(f"Shifted {updated} schedule(s) by {hours:+d}h.")
        )

    @staticmethod
    def _local(value):
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M") if value else None
