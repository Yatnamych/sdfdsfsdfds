# Полный тест всех команд этапов 1–5
echo "=== Этап 4: ls, cd, tree, uniq, date ==="
date
date +%Y-%m-%d
pwd
tree
tree -a
ls -la
cd /home/user
cat notes.txt
uniq notes.txt
uniq -c notes.txt
echo "a
a
b
b
b
c" > /tmp_test.txt
cat /tmp_test.txt
uniq -c /tmp_test.txt

echo "=== Этап 5: mkdir / rmdir ==="
mkdir /home/user/newdir
ls /home/user
mkdir /home/user/newdir/sub
tree /home/user/newdir
rmdir /home/user/newdir
rmdir /home/user/newdir
# Ошибки:
mkdir /home/user/readme.txt
rmdir /home/user/readme.txt
cd /etc
pwd
ls
cat hostname
cat motd
echo "=== Готово ==="