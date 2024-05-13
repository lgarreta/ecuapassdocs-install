#!/usr/bin/python3

import os

lines = open ("README.md").readlines()
for i, line in enumerate (lines):
	if "LOG" in line:
		break

log = lines [i+1].strip()

print (log)

os.system (f"gitt '{log}'")
	
