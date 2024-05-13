:: Create windows installer from java JAR file

rmdir /S /Q last
mkdir last
move Output last

"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "inno-installer-EcuapassDocsAnalisisGUI.iss"
