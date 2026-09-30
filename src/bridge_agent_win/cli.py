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

import sys
from pathlib import Path

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


def main() -> None:
    """Главная точка входа bridge-agent."""
    # Проверка запуска в качестве системной службы Windows SCM
    if HAS_WIN32SERVICE:
        try:
            import servicemanager

            if servicemanager.RunningAsService():
                run_scm_service()
                return
        except Exception:
            pass

    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print("bridge-agent — Windows Agent Management CLI")
        print("\nКоманды:")
        print("  run                     Запуск фонового демона службы Windows (консольный режим)")
        print("  service-run             Запуск в режиме диспетчера системной службы SCM")
        print("  service [cmd]           Управление службой SCM (install/start/stop/remove)")
        print("  drop <file>             Отправить файл в локальный Карман")
        print("  install-context-menu    Установить пункт контекстного меню в Проводник")
        print("  uninstall-context-menu  Удалить пункт контекстного меню из Проводника")
        print("  generate-reg [out.reg]  Сгенерировать файл реестра .reg")
        sys.exit(0)

    cmd = args[0].lower()
    if cmd == "run":
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
