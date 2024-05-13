
echo "\n>>>>>>>>>> Building exe for python server <<<<<<<<<<\n"
cd exe-server-python
call "build-exe-python.bat"
cd ..

echo "\n>>>>>>>>>> Building exe for java GUI <<<<<<<<<<\n"
cd exe-gui-java
call "build2-exe-javacmd-launch4jc.bat"
cd..

echo "\n>>>>>>>>>> Building exe for installer <<<<<<<<<<\n"
cd exe-installer
call "build2-inno-installer.bat"

