"""
bridge_agent_win.cli — Консольная утилита управления агентом Windows (bridge-agent).

Предоставляет команды:
  - run: запуск демона службы.
  - drop <file>: отправка файла/каталога в локальный карман (Watchdog синхронизирует с Linux).
  - install-context-menu: установка пункта в контекстное меню Explorer.
  - uninstall-context-menu: удаление пункта из контекстного меню Explorer.
  - generate-reg [path]: экспорт .reg файла для ручной регистрации.
"""

import asyncio
import contextlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from bridge_core.models import NodeOS
from bridge_core.process_killer import is_pid_running
from bridge_core.transport import check_port_listening

# Автоматическое добавление каталога src/ в sys.path
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Принудительная настройка UTF-8 вывода для Windows-консоли
if sys.platform == "win32":
    with contextlib.suppress(Exception):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")


from bridge_agent_win.context_menu import (  # noqa: E402
    drop_file_to_pocket,
    install_context_menu,
    save_reg_file,
    uninstall_context_menu,
)

try:
    from bridge_agent_win.service import (
        HAS_WIN32SERVICE,
        handle_service_command,
        main_standalone,
        run_scm_service,
    )
except Exception:
    HAS_WIN32SERVICE = False

    def main_standalone() -> None:
        print("[FAIL] Служба недоступна (ошибка импорта service.py)")
        sys.exit(1)

    def run_scm_service() -> None:
        print("[FAIL] SCM служба недоступна")
        sys.exit(1)

    def handle_service_command(args: list[str]) -> None:
        print("[FAIL] Управление службой недоступно")


def get_local_ip_addresses() -> list[str]:
    """Возвращает список IPv4 адресов локальных сетевых интерфейсов."""
    ips: list[str] = []
    try:
        import socket

        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            import socket

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return ips


PID_FILE_NAME = ".bridge_agent.pid"


def get_pid_file_path() -> Path:
    """Возвращает путь к PID-файлу фонового агента в каталоге кармана."""
    from bridge_core.config import BridgeConfig

    cfg = BridgeConfig.load()
    return cfg.get_pocket_dir() / PID_FILE_NAME




def start_detached_daemon() -> None:
    """Запускает независимый фоновый процесс демона Windows без привязки к консоли."""
    from bridge_core.config import BridgeConfig

    cfg = BridgeConfig.load()
    port = cfg.connection.port
    host = cfg.connection.host

    if check_port_listening(host, port):
        print(f"[INFO] Агент Bridge Local уже запущен и слушает порт {port}.")
        return

    pid_file = get_pid_file_path()
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            if is_pid_running(old_pid):
                print(f"[INFO] Фоновый процесс агента уже работает (PID={old_pid}).")
                return
        except Exception:
            pass

    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "run"]
    else:
        cmd = [sys.executable, "-m", "bridge_agent_win.cli", "run"]

    # Win32 DETACHED_PROCESS (0x00000008) | CREATE_NO_WINDOW (0x08000000)
    creationflags = (0x00000008 | 0x08000000) if sys.platform == "win32" else 0

    p_dir = cfg.get_pocket_dir()
    cwd = str(p_dir.parent) if p_dir.parent.exists() else str(Path.cwd())

    try:
        proc = subprocess.Popen(
            cmd,
            creationflags=creationflags,
            cwd=cwd,
            close_fds=True,
        )
        try:
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(str(proc.pid))
        except Exception as e:
            print(f"[WARN] Не удалось сохранить PID: {e}")

        # Ожидание активации сокета агента (до 2.5 сек)
        online = False
        for _ in range(25):
            time.sleep(0.1)
            if check_port_listening(host, port, timeout_sec=0.1):
                online = True
                break

        if online:
            print(f"[OK] Фоновый демон Bridge Local успешно запущен (PID={proc.pid}, порт {port}).")
        else:
            print(f"[OK] Фоновый процесс запущен (PID={proc.pid}), ожидает открытия порта {port}.")
    except Exception as e:
        print(f"[ERROR] Ошибка запуска фонового демона: {e}")
        sys.exit(1)


def stop_detached_daemon() -> None:
    """Останавливает фоновый процесс демона Windows."""
    from bridge_agent_win.process_killer import kill_process_tree
    from bridge_core.config import BridgeConfig

    cfg = BridgeConfig.load()
    port = cfg.connection.port
    host = cfg.connection.host

    pid_file = get_pid_file_path()
    stopped = False

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if is_pid_running(pid):
                kill_process_tree(pid, timeout_sec=2.0)
                stopped = True
        except Exception as e:
            print(f"[WARN] Ошибка остановки по PID: {e}")
        with contextlib.suppress(Exception):
            pid_file.unlink()

    # Если порт все еще слушается, находим и завершаем процесс по номеру порта
    if check_port_listening(host, port) and sys.platform == "win32":
        try:
            res = subprocess.run(
                f"netstat -ano | findstr :{port}",
                shell=True,
                capture_output=True,
                text=True,
                check=False,
            )
            for line in res.stdout.splitlines():
                if "LISTENING" in line:
                    parts = line.strip().split()
                    if parts:
                        p_pid = int(parts[-1])
                        if p_pid > 0:
                            kill_process_tree(p_pid, timeout_sec=2.0)
                            stopped = True
        except Exception:
            pass

    if stopped or not check_port_listening(host, port):
        print(f"[OK] Фоновый демон Bridge Local остановлен (порт {port} свободен).")
    else:
        print(f"[WARN] Не удалось подтвердить освобождение порта {port}.")


def print_agent_status() -> None:
    """Выводит сводный статус агента, службы SCM, сокета и кармана."""
    from bridge_core.config import BridgeConfig

    cfg = BridgeConfig.load()
    host = cfg.connection.host
    port = cfg.connection.port
    ips = get_local_ip_addresses()

    port_online = check_port_listening(host, port)
    pid_file = get_pid_file_path()
    pid_val = None
    if pid_file.exists():
        try:
            p = int(pid_file.read_text().strip())
            if is_pid_running(p):
                pid_val = p
        except Exception:
            pass

    print("=" * 65)
    print("           СТАТУС BRIDGE LOCAL WINDOWS AGENT")
    print("=" * 65)
    if port_online:
        print(f"  Сетевой порт:     {port} [ONLINE / LISTENING]")
    else:
        print(f"  Сетевой порт:     {port} [OFFLINE / STOPPED]")

    if pid_val:
        print(f"  Фоновый демон:    PID {pid_val} [АКТИВЕН / DETACHED]")
    else:
        print("  Фоновый демон:    НЕ ЗАПУЩЕН")

    if HAS_WIN32SERVICE:
        try:
            import win32service
            import win32serviceutil

            st = win32serviceutil.QueryServiceStatus("BridgeLocalAgent")[1]
            st_map = {
                win32service.SERVICE_RUNNING: "RUNNING [ONLINE]",
                win32service.SERVICE_STOPPED: "STOPPED [OFFLINE]",
                win32service.SERVICE_START_PENDING: "STARTING...",
                win32service.SERVICE_STOP_PENDING: "STOPPING...",
            }
            print(f"  Служба SCM:       {st_map.get(st, f'Код {st}')}")
        except Exception:
            print("  Служба SCM:       НЕ УСТАНОВЛЕНА")

    print(f"  Каталог кармана:  {cfg.get_pocket_dir()}")
    print("\n  Локальные IP-адреса для подключения с Linux:")
    for ip in ips:
        print(f"    --> {ip}:{port}")
    print("=" * 65)


def setup_interactive() -> None:
    """Интерактивный мастер первоначальной настройки подключения без ручной правки TOML."""
    from bridge_core.config import BridgeConfig

    print("=" * 65)
    print("  Bridge Local Windows Agent - Мастер настройки подключения")
    print("=" * 65)

    ips = get_local_ip_addresses()
    print("\nСетевые адреса этого компьютера (вводите их на Linux):")
    if ips:
        for ip in ips:
            print(f"  --> {ip}")
    else:
        print("  --> 127.0.0.1 (локальный loopback)")

    cfg = BridgeConfig.load()
    cur_port = cfg.connection.port
    cur_host = cfg.connection.host
    cur_token = cfg.connection.psk_token or "BridgeLocalSecretKey_CHANGE_ME"
    cur_pocket = cfg.pocket.path
    tok_preview = f"{cur_token[:8]}..." if cur_token else "(отключен)"

    print(f"\nТекущие параметры ({cfg._config_path or 'bridge.toml'}):")
    print(f"  Порт агента:                   {cur_port}")
    print(f"  Слушать на адресе (Bind Host): {cur_host}")
    print(f"  Ключ безопасности (PSK):       {tok_preview}")
    print(f"  Каталог кармана:               {cur_pocket}")

    try:
        prompt_port = f"\n[1/3] Введите TCP-порт [Enter = {cur_port}]: "
        new_port_str = input(prompt_port).strip()
        if new_port_str:
            try:
                cfg.connection.port = int(new_port_str)
            except ValueError:
                print(f"[WARN] Некорректный порт '{new_port_str}', оставлен {cur_port}")

        prompt_tok = "[2/3] Введите ключ безопасности (PSK) [Enter = оставить]: "
        new_token_str = input(prompt_tok).strip()
        if new_token_str:
            cfg.connection.psk_token = new_token_str

        prompt_pock = f"[3/3] Каталог кармана [Enter = {cur_pocket}]: "
        new_pocket_str = input(prompt_pock).strip()
        if new_pocket_str:
            cfg.pocket.path = new_pocket_str

        cfg.save()
        print("\n" + "=" * 65)
        print("[OK] Параметры успешно сохранены в bridge.toml!")
        print(f"  Порт агента: {cfg.connection.port}")
        print(f"  Слушать на:  {cfg.connection.host}")
        print(f"  Карман:      {cfg.pocket.path}")
        print("=" * 65)
        print("\nЧто делать дальше:")
        if ips:
            print(f"  1. На Linux введите: bridge connect {ips[0]}:{cfg.connection.port}")
            print(f"     или в TUI на [F7:CONNECT] введите: {ips[0]}:{cfg.connection.port}")
        print("  2. На Windows запустите run_agent.bat или install_service.bat")
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Настройка отменена пользователем.")


def handle_config_command(args: list[str]) -> None:
    """Управление конфигурацией из командной строки."""
    from bridge_core.config import BridgeConfig

    cfg = BridgeConfig.load()
    if not args or args[0] in ("show", "list", "status"):
        ips = get_local_ip_addresses()
        print("Текущая конфигурация Windows Agent:")
        print(f"  Конфиг-файл: {cfg._config_path or 'bridge.toml'}")
        print(f"  Порт:        {cfg.connection.port}")
        print(f"  Bind Host:   {cfg.connection.host}")
        print(f"  Карман:      {cfg.pocket.path}")
        print(f"  Токен:       {'Задан' if cfg.connection.psk_token else 'Отключен'}")
        print("\nIP-адреса для подключения с Linux:")
        for ip in ips:
            print(f"  --> {ip}:{cfg.connection.port}")
        return

    if args[0] == "path":
        print(str(cfg._config_path.resolve()) if cfg._config_path else "bridge.toml")
        return

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--port", "-p") and i + 1 < len(args):
            with contextlib.suppress(ValueError):
                cfg.connection.port = int(args[i + 1])
            i += 2
        elif a in ("--host", "-h") and i + 1 < len(args):
            cfg.connection.host = args[i + 1]
            i += 2
        elif a in ("--token", "-t") and i + 1 < len(args):
            cfg.connection.psk_token = args[i + 1]
            i += 2
        elif a in ("--pocket",) and i + 1 < len(args):
            cfg.pocket.path = args[i + 1]
            i += 2
        else:
            i += 1
    cfg.save()
    print(f"[OK] Конфигурация сохранена в {cfg._config_path or 'bridge.toml'}")


def _output_json(data: Any, exit_code: int = 0) -> None:
    """Выводит чистый JSON без ANSI-символов в stdout и завершает процесс."""
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    sys.stdout.write(serialized + "\n")
    sys.stdout.flush()
    if exit_code != 0:
        sys.exit(exit_code)


def _handle_client_error(e: Exception, as_json: bool = False) -> None:
    """Обрабатывает исключения клиента с возвратом детерминированных кодов завершения."""
    from bridge_core.exceptions import format_error_payload

    code, payload = format_error_payload(e)

    if as_json:
        _output_json(payload, exit_code=code)
    else:
        print(f"[ERROR {code}] {e}")
        sys.exit(code)


def _parse_client_flags(args: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Парсит стандартные флаги подключения и фильтрации для клиентских команд."""
    flags: dict[str, Any] = {
        "json": False,
        "host": None,
        "port": None,
        "token": None,
        "node": None,
        "timeout": None,
        "dir": None,
        "admin": True,
        "count": 1,
        "path": None,
    }
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--json", "-j"):
            flags["json"] = True
            i += 1
        elif a in ("--host", "-h") and i + 1 < len(args):
            flags["host"] = args[i + 1]
            i += 2
        elif a in ("--port", "-p") and i + 1 < len(args):
            with contextlib.suppress(ValueError):
                flags["port"] = int(args[i + 1])
            i += 2
        elif a in ("--token", "-t") and i + 1 < len(args):
            flags["token"] = args[i + 1]
            i += 2
        elif a in ("--node", "-n", "--target") and i + 1 < len(args):
            flags["node"] = args[i + 1]
            i += 2
        elif a in ("--timeout", "-T") and i + 1 < len(args):
            with contextlib.suppress(ValueError):
                flags["timeout"] = float(args[i + 1])
            i += 2
        elif a in ("--dir", "-d") and i + 1 < len(args):
            flags["dir"] = args[i + 1]
            i += 2
        elif a == "--admin":
            flags["admin"] = True
            i += 1
        elif a == "--no-admin":
            flags["admin"] = False
            i += 1
        elif a in ("--count", "-c") and i + 1 < len(args):
            with contextlib.suppress(ValueError):
                flags["count"] = int(args[i + 1])
            i += 2
        elif a in ("--path",) and i + 1 < len(args):
            flags["path"] = args[i + 1]
            i += 2
        else:
            positional.append(a)
            i += 1
    return flags, positional


def _get_bridge_client(flags: dict[str, Any]) -> Any:
    """Создаёт инстанс BridgeClient с переопределениями из флагов."""
    from bridge_core.client import BridgeClient
    from bridge_core.config import BridgeConfig

    cfg = BridgeConfig.load()
    timeout = flags.get("timeout")
    timeout_sec = float(timeout) if timeout is not None else None
    return BridgeClient(
        config=cfg,
        host=flags.get("host"),
        port=flags.get("port"),
        psk_token=flags.get("token"),
        target_node=flags.get("node"),
        timeout_sec=timeout_sec,
    )


def handle_exec_command(args: list[str]) -> None:
    """Удалённый запуск команд на целевом узле (Linux или Windows) через BridgeClient."""
    from bridge_core.exit_codes import ExitCode

    flags, pos = _parse_client_flags(args)
    if not pos:
        if flags.get("json"):
            _output_json(
                {"status": "error", "error_code": int(ExitCode.GENERAL_ERROR), "message": "Command required"},
                exit_code=int(ExitCode.GENERAL_ERROR),
            )
        else:
            print("Ошибка: укажите команду для выполнения (bridge-agent exec <команда>)")
            sys.exit(int(ExitCode.GENERAL_ERROR))

    command = " ".join(pos)
    client = _get_bridge_client(flags)
    timeout = flags.get("timeout")
    timeout_sec = int(timeout) if timeout is not None else 30
    run_as_admin = flags.get("admin", True)
    working_dir = flags.get("dir")
    target_node = flags.get("node")

    async def _action() -> Any:
        async with client:
            return await client.exec(
                command=command,
                timeout_sec=timeout_sec,
                run_as_admin=run_as_admin,
                working_dir=working_dir,
                target_node=target_node,
            )

    try:
        res = asyncio.run(_action())
    except Exception as e:
        _handle_client_error(e, as_json=bool(flags.get("json")))
        return

    if flags.get("json"):
        data = res.model_dump()
        exit_code = ExitCode.SUCCESS if res.exit_code == 0 else ExitCode.COMMAND_FAILED
        _output_json(data, exit_code=int(exit_code))
        return

    if res.stdout:
        sys.stdout.write(res.stdout)
        if not res.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if res.stderr:
        sys.stderr.write(res.stderr)
        if not res.stderr.endswith("\n"):
            sys.stderr.write("\n")

    if res.exit_code != 0:
        sys.exit(int(ExitCode.COMMAND_FAILED))


def handle_ping_command(args: list[str]) -> None:
    """Heartbeat-проверка доступности удаленного узла."""
    flags, _ = _parse_client_flags(args)
    count = flags.get("count") or 1
    client = _get_bridge_client(flags)

    async def _action() -> list[dict[str, Any]]:
        results = []
        async with client:
            for _ in range(count):
                pong, rtt = await client.ping(client_os=NodeOS.WINDOWS)
                results.append({"latency_ms": rtt, "pong": pong.model_dump()})
                if count > 1:
                    await asyncio.sleep(0.5)
        return results

    try:
        data = asyncio.run(_action())
    except Exception as e:
        _handle_client_error(e, as_json=bool(flags.get("json")))
        return

    if flags.get("json"):
        _output_json({"pings": data, "target_node": client.target_node})
        return

    for item in data:
        rtt = item["latency_ms"]
        p = item["pong"]
        print(
            f"PONG from {client.target_node} ({p['agent_os']}): rtt={rtt}ms "
            f"status={p['status']} cpu={p['cpu_percent']}% ram={p['memory_used_mb']}MB"
        )


def handle_ls_command(args: list[str]) -> None:
    """Удалённый просмотр каталога на целевом узле."""
    flags, pos = _parse_client_flags(args)
    path = pos[0] if pos else "."
    client = _get_bridge_client(flags)

    async def _action() -> Any:
        async with client:
            return await client.fs_list(
                path=path,
                target_node=flags.get("node"),
            )

    try:
        res = asyncio.run(_action())
    except Exception as e:
        _handle_client_error(e, as_json=bool(flags.get("json")))
        return

    if flags.get("json"):
        _output_json(res.model_dump())
        return

    print(f"Каталог: {res.target_path} (всего объектов: {res.total_entries})")
    for entry in res.entries:
        kind = "<DIR> " if entry.is_dir else "      "
        size_str = f"{entry.size_bytes:>10} B" if not entry.is_dir else "          "
        print(f"  {kind} {size_str}  {entry.name}")


def handle_find_command(args: list[str]) -> None:
    """Удалённый поиск файлов на целевом узле."""
    flags, pos = _parse_client_flags(args)
    if not pos:
        print("Ошибка: укажите шаблон для поиска (bridge-agent find <паттерн>)")
        sys.exit(1)

    pattern = pos[0]
    root_dir = flags.get("path") or (pos[1] if len(pos) > 1 else None)
    client = _get_bridge_client(flags)

    async def _action() -> Any:
        async with client:
            return await client.fs_find(
                pattern=pattern,
                directory=root_dir,
                target_node=flags.get("node"),
            )

    try:
        res = asyncio.run(_action())
    except Exception as e:
        _handle_client_error(e, as_json=bool(flags.get("json")))
        return

    if flags.get("json"):
        _output_json(res.model_dump())
        return

    print(f"Поиск '{res.pattern}' в {res.searched_directory} (найдено: {res.total_found}):")
    for entry in res.entries:
        kind = "<DIR>" if entry.is_dir else f"{entry.size_bytes} B"
        print(f"  {entry.path} ({kind})")


def handle_send_command(args: list[str]) -> None:
    """Отправка локального файла в удалённый Карман целевого узла."""
    flags, pos = _parse_client_flags(args)
    if not pos:
        print("Ошибка: укажите локальный файл (bridge-agent send <файл>)")
        sys.exit(1)

    local_path = Path(pos[0])
    if not local_path.exists():
        print(f"Ошибка: файл не найден: {local_path}")
        sys.exit(1)

    client = _get_bridge_client(flags)

    async def _action() -> Any:
        async with client:
            return await client.send_pocket_file(
                local_file_path=local_path,
                target_node=flags.get("node"),
            )

    try:
        res = asyncio.run(_action())
    except Exception as e:
        _handle_client_error(e, as_json=bool(flags.get("json")))
        return

    if flags.get("json"):
        _output_json(res.model_dump())
        return

    file_path = getattr(res, "path", getattr(res, "relative_path", ""))
    size = getattr(res, "bytes_written", getattr(res, "size_bytes", 0))
    print(f"[OK] Файл '{file_path}' ({size} байт) успешно отправлен в удалённый Карман.")


def handle_note_command(args: list[str]) -> None:
    """Отправка или просмотр заметок."""
    flags, pos = _parse_client_flags(args)
    client = _get_bridge_client(flags)

    if pos and pos[0] == "history":
        async def _action_hist() -> Any:
            async with client:
                return await client.get_note_history(
                    limit=20,
                    target_node=flags.get("node"),
                )

        try:
            hist = asyncio.run(_action_hist())
        except Exception as e:
            _handle_client_error(e, as_json=bool(flags.get("json")))
            return

        if flags.get("json"):
            _output_json(hist.model_dump())
            return

        print(f"История заметок (всего: {hist.total_count}):")
        for n in hist.notes:
            status = "[ПРОЧИТАНО]" if getattr(n, "status", None) == "read" else "[НОВОЕ]"
            ts = getattr(n, "timestamp", getattr(n, "created_at", ""))
            print(f"  {ts[:19]} {status} {n.text}")
        return

    if not pos:
        print("Ошибка: укажите текст заметки (bridge-agent note <текст> или note history)")
        sys.exit(1)

    text = " ".join(pos)

    async def _action_send() -> Any:
        async with client:
            return await client.send_note(
                text=text,
                target_node=flags.get("node"),
            )

    try:
        res = asyncio.run(_action_send())
    except Exception as e:
        _handle_client_error(e, as_json=bool(flags.get("json")))
        return

    if flags.get("json"):
        _output_json(res.model_dump())
        return

    print(f"[OK] Заметка отправлена (ID: {res.note_id})")


def main(argv: list[str] | None = None) -> None:
    """Главная точка входа bridge-agent."""
    args = list(argv) if argv is not None else sys.argv[1:]

    # Проверка запуска в качестве системной службы Windows SCM
    # Выполняется только если процесс вызван без аргументов (SCM запуск)
    if not args and HAS_WIN32SERVICE:
        try:
            import servicemanager

            if servicemanager.RunningAsService():
                run_scm_service()
                return
        except Exception:
            pass

    if not args:
        # При запуске двойным кликом в проводнике или без параметров запускаем агент в консоли
        main_standalone()
        return

    if args[0] in ("-h", "--help", "help"):
        print("bridge-agent - Windows Agent & Client Management CLI (Dual-Role Peer)")
        print("\nСерверные команды агента (Server Node):")
        print("  start                   Запуск фонового демона в отвязанном режиме (Detached Process)")
        print("  stop                    Остановка фонового демона агента")
        print("  status                  Текущий статус демона, службы SCM, порта и кармана")
        print("  run                     Запуск фонового демона службы Windows (консольный режим)")
        print("  setup                   Мастер быстрой настройки (IP, порт, токен)")
        print("  config [show|opts]      Просмотр и изменение сетевых параметров")
        print("  service-run             Запуск в режиме диспетчера системной службы SCM")
        print("  service [cmd]           Управление службой SCM (install/start/stop/remove)")
        print("  drop <file>             Отправить файл в локальный Карман")
        print("  tray [--with-agent]     Запуск значка управления в системном трее Windows")
        print("  install-context-menu    Установить пункт контекстного меню в Проводник")
        print("  uninstall-context-menu  Удалить пункт контекстного меню из Проводника")
        print("  generate-reg [out.reg]  Сгенерировать файл реестра .reg")
        print("\nКлиентские команды P2P управления (Client Node):")
        print("  exec <cmd> [opts]       Удалённый запуск команды на целевом узле (Linux / Windows)")
        print("  ping [opts]             Heartbeat-проверка удаленного узла")
        print("  ls [path] [opts]        Удалённый просмотр каталога на узле")
        print("  find <pattern> [opts]   Удалённый поиск файлов на узле")
        print("  send <file> [opts]      Отправить локальный файл в удалённый Карман")
        print("  note <text|history>     Отправить текстовую заметку или просмотреть историю")
        print("\nОпции подключения:")
        print("  --host, -h <host>       Хост целевого узла (по умолчанию из bridge.toml)")
        print("  --port, -p <port>       Порт целевого узла (по умолчанию 9732)")
        print("  --token, -t <token>     PSK-токен аутентификации")
        print("  --node, -n <name>       Имя узла (маршрутизация F1/F2)")
        print("  --json, -j              Машиночитаемый JSON-вывод без ANSI-мусора для ИИ-агентов")
        sys.exit(0)

    cmd = args[0].lower()
    if cmd in ("start", "start-bg", "daemon"):
        start_detached_daemon()
    elif cmd in ("stop", "stop-bg"):
        stop_detached_daemon()
    elif cmd in ("status", "info"):
        print_agent_status()
    elif cmd == "setup":
        setup_interactive()
    elif cmd == "config":
        handle_config_command(args[1:])
    elif cmd == "run":
        main_standalone()
    elif cmd in ("service-run", "scm-run"):
        run_scm_service()
    elif cmd == "service":
        handle_service_command(args[1:])
    elif cmd == "tray":
        from bridge_agent_win.tray import BridgeTrayIcon

        tray = BridgeTrayIcon()
        if "--with-agent" in args or "--standalone" in args:
            tray.start_standalone_agent()
        try:
            tray.run()
        except (KeyboardInterrupt, SystemExit):
            tray.stop()
    elif cmd == "pocket":
        if len(args) > 1 and args[1] == "path":
            from bridge_core.config import BridgeConfig

            cfg = BridgeConfig.load()
            print(str(cfg.get_pocket_dir()))
            return
        if len(args) > 1 and args[1] == "drop":
            args = ["drop", *args[2:]]
            cmd = "drop"
        else:
            from bridge_core.config import BridgeConfig

            cfg = BridgeConfig.load()
            print(f"Каталог кармана: {cfg.get_pocket_dir()}")
            return
    elif cmd in ("drop", "clip", "drop-clipboard"):
        is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
        show_alert = sys.platform == "win32" and not is_tty
        if "--alert" in args:
            show_alert = True
        if "--quiet" in args or "--no-alert" in args:
            show_alert = False

        # Если файл не указан или передан флаг --clipboard: берем из буфера обмена!
        if len(args) < 2 or args[1] in ("--clipboard", "-c", "clipboard"):
            from bridge_agent_win.context_menu import drop_clipboard_to_pocket

            dropped = drop_clipboard_to_pocket(show_alert=show_alert)
            if dropped:
                names = ", ".join(p.name for p in dropped)
                print(f"[OK] Из буфера обмена скопировано в Карман: {names}")
            else:
                print("[WARN] Буфер обмена пуст или не содержит доступных файлов/текста.")
            return

        target = args[1]
        try:
            if show_alert:
                dest = drop_file_to_pocket(target, show_alert=True)
            else:
                dest = drop_file_to_pocket(target)
            print(f"[OK] Файл скопирован в Карман: {dest}")
        except Exception as e:
            print(f"[ERROR] Ошибка копирования в Карман: {e}")
            sys.exit(1)
    elif cmd == "install-context-menu":
        ok = install_context_menu()
        if ok:
            print("[OK] Контекстное меню установлено.")
        else:
            print("[WARN] Не удалось записать в реестр (не Windows?).")
            save_reg_file("windows_context_menu.reg")
            print("[INFO] Сгенерирован windows_context_menu.reg для ручного импорта.")
    elif cmd == "uninstall-context-menu":
        ok = uninstall_context_menu()
        if ok:
            print("[OK] Контекстное меню удалено.")
        else:
            print("[WARN] Не удалось удалить ключи реестра.")
    elif cmd == "generate-reg":
        out = Path(args[1]) if len(args) > 1 else Path("windows_context_menu.reg")
        reg_p = save_reg_file(out)
        print(f"[OK] Файл реестра создан: {reg_p}")
    elif cmd == "exec":
        handle_exec_command(args[1:])
    elif cmd == "ping":
        handle_ping_command(args[1:])
    elif cmd in ("ls", "list"):
        handle_ls_command(args[1:])
    elif cmd == "find":
        handle_find_command(args[1:])
    elif cmd == "send":
        handle_send_command(args[1:])
    elif cmd == "note":
        handle_note_command(args[1:])
    else:
        print(f"Неизвестная команда: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
