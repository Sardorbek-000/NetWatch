

import asyncio
import threading

from desktop_notifier import DesktopNotifier


class Notifier:
    def __init__(self, app_name="NetWatch"):
        self._notifier = DesktopNotifier(app_name=app_name)
        self._loop = asyncio.new_event_loop()
        self._lock = threading.Lock()

    def notify(self, title, message=""):
        with self._lock:
            try:
                self._loop.run_until_complete(
                    self._notifier.send(title=title, message=message)
                )
            except Exception as exc:
                print(f"fail to send notification: {exc}")


notifier = Notifier()


def notify(title, message=""):
    notifier.notify(title, message)
