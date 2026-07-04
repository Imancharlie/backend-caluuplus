from django.core.management.base import BaseCommand, CommandError

from api.models import GPACalculation


class Command(BaseCommand):
    help = "Verify GPA privacy migration and encrypted payload completeness."

    def handle(self, *args, **options):
        total = GPACalculation.objects.count()
        missing_cipher = GPACalculation.objects.filter(gpa_ciphertext__isnull=True).count() + GPACalculation.objects.filter(gpa_ciphertext="").count()
        missing_iv = GPACalculation.objects.filter(gpa_iv__isnull=True).count() + GPACalculation.objects.filter(gpa_iv="").count()
        missing_salt = GPACalculation.objects.filter(gpa_salt__isnull=True).count() + GPACalculation.objects.filter(gpa_salt="").count()
        missing_alg = GPACalculation.objects.filter(gpa_alg__isnull=True).count() + GPACalculation.objects.filter(gpa_alg="").count()

        self.stdout.write(self.style.NOTICE("GPA Privacy Verification"))
        self.stdout.write(f"Total GPACalculation rows: {total}")
        self.stdout.write(f"Missing gpa_ciphertext: {missing_cipher}")
        self.stdout.write(f"Missing gpa_iv: {missing_iv}")
        self.stdout.write(f"Missing gpa_salt: {missing_salt}")
        self.stdout.write(f"Missing gpa_alg: {missing_alg}")

        if any([missing_cipher, missing_iv, missing_salt, missing_alg]):
            raise CommandError(
                "Verification failed: some GPA rows are missing encrypted fields. "
                "Check migration state and data quality before going live."
            )

        alg_counts = (
            GPACalculation.objects.values_list("gpa_alg")
            .order_by("gpa_alg")
        )
        summary = {}
        for alg, in alg_counts:
            summary[alg] = summary.get(alg, 0) + 1

        self.stdout.write(self.style.SUCCESS("All GPA rows have encrypted payload fields."))
        self.stdout.write("Algorithm distribution:")
        for alg, count in summary.items():
            self.stdout.write(f"- {alg}: {count}")
