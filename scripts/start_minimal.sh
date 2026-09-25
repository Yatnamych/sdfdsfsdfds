# Стартовый скрипт: минимальный VFS и базовые команды
echo "=== Этап 1: REPL и базовые команды ==="
echo "Переменная HOME=$HOME"
echo "Переменная USER=$USER"
pwd
ls
ls -l
cd /home
pwd
ls -la
cd /home/user
cat readme.txt
# Проверка обработки ошибок
cd /nonexistent
ls /nonexistent
foo bar
echo "Готово"