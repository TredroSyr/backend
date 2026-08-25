from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Initialize the application - runs all necessary setup commands"

    def handle(self, *args, **options) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
        self.stdout.write(self.style.MIGRATE_HEADING("Application Initialization"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
        self.stdout.write("")

        # List of initialization tasks
        tasks = [
            {
                "name": "Seed Common Data",
                "command": "seed_common_data",
                "args": [],
                "kwargs": {},
            },
            # Add more initialization commands here in the future
            # Example:
            # {
            #     "name": "Create Default Admin",
            #     "command": "create_default_admin",
            #     "args": [],
            #     "kwargs": {},
            # },
        ]

        # Execute each task
        for task in tasks:
            self.stdout.write(
                self.style.MIGRATE_LABEL(f"→ Running: {task['name']}")
            )
            self.stdout.write("")

            try:
                call_command(
                    task["command"],
                    *task["args"],
                    **task["kwargs"],
                )
                self.stdout.write("")
                self.stdout.write(
                    self.style.SUCCESS(f"✓ {task['name']} completed successfully")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✗ {task['name']} failed: {str(e)}")
                )
                raise

            self.stdout.write("")

        # Final summary
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
        self.stdout.write(
            self.style.SUCCESS("✓ Application initialization completed successfully")
        )
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
