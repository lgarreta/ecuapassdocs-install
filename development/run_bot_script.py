iamport subprocess

botProgram = "Z:\\ecusrv\\ecuapass_server_bot.py"
jsonFilepath = 'C:\\Users\\LG\\AAA\\01-septiembre-2023-09_56_32\\CPI-COCO003644_nombreslargos-RESULTS.json'
output = subprocess.run  (["cmd.exe", "/c", "python", botProgram, jsonFilepath], capture_output=True, shell=True).stderr
print (output)
