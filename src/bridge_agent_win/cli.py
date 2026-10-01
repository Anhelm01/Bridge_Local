"""
bridge_agent_win.cli — Консольная утилита управления агентом Windows (bridge-agent).

Предоставляет команды:
  - run: запуск демона службы.
  - drop <file>: отправка файла/каталога в локальный карман (Watchdog синхронизирует с Linux).
  - install-context-menu: установка пункта в контекстное меню Explorer.
  - uninstall-context-menu: удаление пункта из контекстного меню Explorer.
  - generate-reg [path]: экспорт .reg файла для ручной регистрации.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

# Принудительная настройка UTF-8 вывода для Windows-консоли
if sys.platform == "win32":
    with contextlib.suppress(Exception):
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")


from bridge_agent_win.context_menu import (
    drop_file_to_pocket,
    install_context_menu,
    save_reg_file,
    uninstall_context_menu,
)
from bridge_agent_win.service import (
    HAS_WIN32SERVICE,
    handle_service_command,
    main_standalone,
    run_scm_service,
)


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
    cur_token = cfg.connection.psk_token or "BridgeLocalSecretKey_Anhelm_2026_Secure"
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
    except KeyboardInterrupt, EOFError:
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


def main() -> None:
    """Главная точка входа bridge-agent."""
    args = sys.argv[1:]

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

    if not args or args[0] in ("-h", "--help", "help"):
        print("bridge-agent - Windows Agent Management CLI")
        print("\nКоманды:")
        print("  setup                   Мастер быстрой настройки (IP, порт, токен)")
        print("  config [show|opts]      Просмотр и изменение сетевых параметров")
        print("  run                     Запуск фонового демона службы Windows (консольный режим)")
        print("  service-run             Запуск в режиме диспетчера системной службы SCM")
        print("  service [cmd]           Управление службой SCM (install/start/stop/remove)")
        print("  drop <file>             Отправить файл в локальный Карман")
        print("  install-context-menu    Установить пункт контекстного меню в Проводник")
        print("  uninstall-context-menu  Удалить пункт контекстного меню из Проводника")
        print("  generate-reg [out.reg]  Сгенерировать файл реестра .reg")
        sys.exit(0)

    cmd = args[0].lower()
    if cmd == "setup":
        setup_interactive()
    elif cmd == "config":
        handle_config_command(args[1:])
    elif cmd == "run":
        main_standalone()
    elif cmd in ("service-run", "scm-run"):
        run_scm_service()
    elif cmd == "service":
        handle_service_command(args[1:])
    elif cmd == "drop":
        if len(args) < 2:
            print("[ERROR] Укажите путь к файлу: bridge-agent drop <file>")
            sys.exit(1)
        target = args[1]
        try:
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
    else:
        print(f"Неизвестная команда: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
