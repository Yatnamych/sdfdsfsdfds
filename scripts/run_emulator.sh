#!/bin/bash
# Тестирование всех параметров командной строки эмулятора
set -e
cd "$(dirname "$0")/.."

echo ">>> 1. Без параметров (пустая VFS, prompt по умолчанию)"
echo "help" | python3 emulator.py --no-interactive

echo ">>> 2. С VFS minimal"
echo "ls /" | python3 emulator.py --vfs vfs/minimal.xml --no-interactive

echo ">>> 3. С VFS files и своим prompt"
echo "ls /home/user" | python3 emulator.py --vfs vfs/files.xml \
    --prompt "tester@emu:~$ " --no-interactive

echo ">>> 4. С VFS deep и стартовым скриптом"
python3 emulator.py --vfs vfs/deep.xml \
    --prompt "emu> " --script scripts/start_minimal.sh --no-interactive

echo ">>> 5. Отладочный вывод"
python3 emulator.py --vfs vfs/files.xml --prompt "dbg> " \
    --debug --script scripts/start_errors.sh --no-interactive

echo ">>> 6. Интерактивный режим (ввод через pipe)"
printf 'pwd\nls\ndate\nexit\n' | python3 emulator.py --vfs vfs/minimal.xml