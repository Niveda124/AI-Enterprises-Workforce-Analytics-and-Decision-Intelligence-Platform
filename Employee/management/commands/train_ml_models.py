from django.core.management.base import BaseCommand
from Employee.ml.train_models import train_all_models


class Command(BaseCommand):
    help = "Audits data, trains/tunes/evaluates all ML models, and saves the best model per target."

    def handle(self, *args, **options):
        results = train_all_models()
        for name, result in results.items():
            self.stdout.write(self.style.WARNING(f"\n=== {name} ==="))
            status = result.get('status')

            if status == 'trained':
                m = result['metrics']
                self.stdout.write(self.style.SUCCESS(f"Selected algorithm: {m['algorithm']}"))
                self.stdout.write(f"Candidates compared: {m['candidates_compared']}")
                if 'total_training_records' in m:
                    self.stdout.write(f"Total training records: {m['total_training_records']}")
                if 'total_rows' in m:
                    self.stdout.write(f"Total rows: {m['total_rows']}")
                self.stdout.write(f"Training samples: {m['training_samples']} | Test samples: {m['test_samples']}")
                if 'classes' in m:
                    self.stdout.write(f"Classes: {m['classes']}")
                self.stdout.write(f"Features used: {m['features_used']}")
                if 'cross_validation' in m:
                    self.stdout.write(f"Cross-validation: {m['cross_validation']}")
                self.stdout.write(f"Test metrics: {m['test_metrics']}")
                self.stdout.write(f"Saved to: {result['file_path']}")

            elif status == 'MODEL_NOT_READY':
                m = result['metrics']
                self.stdout.write(self.style.ERROR("MODEL_NOT_READY — trained but NOT registered as active."))
                self.stdout.write(f"Algorithm tried: {m.get('algorithm')}")
                self.stdout.write(f"Training samples: {m.get('training_samples')} | Test samples: {m.get('test_samples')}")
                if 'cross_validation' in m:
                    self.stdout.write(f"Cross-validation: {m['cross_validation']}")
                self.stdout.write(f"Test metrics: {m['test_metrics']}")
                self.stdout.write(self.style.WARNING(m.get('rejection_reason', 'No reason provided.')))

            elif status == 'TASK_DELAY_MODEL_NOT_READY':
                self.stdout.write(self.style.ERROR(result['message']))

            else:
                self.stdout.write(self.style.ERROR(result.get('message', 'Unknown status')))
                if 'validation_report' in result:
                    self.stdout.write(f"Validation report: {result['validation_report']}")