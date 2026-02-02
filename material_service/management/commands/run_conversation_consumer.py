import signal
import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Runs a dedicated Daphne instance that only serves the AI conversation "
        "WebSocket consumer. Use this to deploy the audio conversation pipeline "
        "as an isolated worker"
    )

    def add_arguments(self, parser):
        parser.add_argument("--host", default="0.0.0.0", help="Host/interface to bind Daphne to")
        parser.add_argument("--port", type=int, default=8100, help="Port to expose Daphne on")
        parser.add_argument(
            "--application",
            default="material_service.asgi:application",
            help="ASGI application path to serve",
        )

    def handle(self, *args, **options):
        host = options["host"]
        port = options["port"]
        application = options["application"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Launching AiConversation consumer on {host}:{port} using {application}"
            )
        )

        cmd = [
            sys.executable, "-m", "daphne",
            "-b", host,
            "-p", str(port),
            application,
        ]

        try:
            process = subprocess.Popen(cmd)
            
            def _graceful_shutdown(signum, frame):  # pragma: no cover - manual signal handling
                self.stdout.write("Received shutdown signal, stopping Daphne...")
                process.terminate()
                
            signal.signal(signal.SIGTERM, _graceful_shutdown)
            
            process.wait()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("AiConversation consumer stopped"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error running Daphne: {e}"))
