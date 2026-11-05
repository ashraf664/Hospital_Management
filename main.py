"""Application entry point."""

import logging
from pathlib import Path

from ui import HospitalManagementApp
from ui.bootstrap import create_service_container


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    project_root = Path(__file__).resolve().parent
    services = create_service_container(
        project_root / "data" / "hospital_management.db"
    )
    try:
        app = HospitalManagementApp(services)
        app.mainloop()
    finally:
        services.close()


if __name__ == "__main__":
    main()
