:: Create executable from python script
::rmdir /S /Q last
::mkdir last
::move build last
::move dist last
::move *.spec last
::move *.exe last

pyinstaller --add-data "ecuapassdocs/resources/images;images" --add-data "ecuapassdocs/resources/data_cartaportes/*.txt";"ecuapassdocs/resources/data_cartaportes/" --add-data "ecuapassdocs/resources/data_manifiestos/*.txt";"ecuapassdocs/resources/data_manifiestos/" --add-data "ecuapassdocs/resources/docs/*.png";"ecuapassdocs/resources/docs/" --add-data "ecuapassdocs/resources/docs/*.pdf";"ecuapassdocs/resources/docs/" --add-data "ecuapassdocs/resources/docs/*.json";"ecuapassdocs/resources/docs/" ecuapass_server.py

copy dist\*.exe .
