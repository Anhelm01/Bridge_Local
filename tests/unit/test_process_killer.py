"""
Тесты для bridge_agent_win.process_killer — надежное уничтожение процессов и дочерних ветвей.
"""

from __future__ import annotations

import subprocess
import sys

from bridge_agent_win.process_killer import kill_process_tree


class TestProcessKiller:
    """Тесты функции kill_process_tree."""

    def test_kill_running_process(self) -> None:
        """Запускаем долгий процесс сна и проверяем, что killer его завершает."""
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        pid = proc.pid
        assert proc.poll() is None  # Процесс активен

        killed = kill_process_tree(pid, timeout_sec=2.0)
        assert pid in killed

        # Дожидаемся завершения процесса и проверяем, что он убит сигналом
        returncode = proc.wait(timeout=1.0)
        assert returncode is not None
        assert returncode != 0  # завершён аварийно (SIGKILL / -9)

    def test_kill_non_existent_pid(self) -> None:
        """Передача несуществующего PID не должна вызывать исключений."""
        killed = kill_process_tree(9999999, timeout_sec=0.5)
        assert isinstance(killed, list)

    def test_kill_invalid_pid(self) -> None:
        """Невалидный PID (<= 0) должен возвращать пустой список."""
        assert kill_process_tree(0) == []
        assert kill_process_tree(-10) == []
