#!/usr/bin/env python3

import os, sys, json, time
from traceback import format_exc as traceback_format_exc

# For server
from threading import Thread as threading_Thread

from flask import Flask as flask_Flask 
from flask import request as flask_request 

from werkzeug.serving import make_server

# For doc
from pickle import load as pickle_load
from pickle import dump as pickle_dump
import azure.core.credentials 
from azure.ai.formrecognizer import DocumentAnalysisClient

import re

# For bot
import pyautogui as py
from pyperclip import copy as pyperclip_copy
from pyperclip import paste as pyperclip_paste


USAGE = "ecuapass_server.py"
APP_HOME_DIR = os.environ ["PYECUAPASS"]
APP_KEYS_FILE = os.path.join (APP_HOME_DIR, "keys", "azure-keys-cognitive-resource.json")
PAUSE = 0


"""
Remember to remove the key from your code when you're done, 
and never post it publicly. For production, use secure 
methods to store and access your credentials. For more 
information, see https://docs.microsoft.com/en-us/azure/
cognitive-services/cognitive-services-security?tabs=command-
line%2Ccsharp#environment-variables-and-application-configuration
"""
def main ():
	EcuServer.run_server()
	
#-----------------------------------------------------------
# Ecuapass server: listen GUI messages and run processes
#-----------------------------------------------------------
app = flask_Flask (__name__)
class EcuServer:
	shouldStop = False
	server = None
	runningDir = os.getcwd()

	def run_server ():
		EcuServer.printx ("Running server...")
		EcuServer.printx ("Running dir : ", os.getcwd(), flush=True)
		server = make_server('127.0.0.1', 5000, app)
		server.serve_forever()

	@app.route('/start_processing', methods=['POST'])
	def start_processing ():
		EcuServer.printx ("Iniciando procesamiento...")
		if EcuServer.shouldStop:
			return {'result': 'Servidor cerrándose...'}

		# Get the file name from the request
		service = flask_request.json ['service']
		data    = flask_request.json ['data']

		EcuServer.printx ("Servicio    : ", service, flush=True)
		EcuServer.printx ("Datos       : ", data, flush=True)

		# Call your existing script's function to process the file
		result = None
		if (service == "doc_processing"):
			result = EcuServer.processDocuments (workingDir=data)
		elif (service == "bot_processing"):
			result = mainBot (jsonFilepath=data)
			#result = "Servicio bot ejecutado"
		elif (service == "stop"):
			EcuServer.stop_server ()
		else:
			result = f">>> Servicio '{service}' no disponible."

		EcuServer.printx (result)
		return {'result': result}

	def stop_server ():
		EcuServer.printx ("Cerrando servidor Ecuapass ...")
		EcuServer.should_stop = True
		sys.exit (0)

	def printx (*args, flush=True):
		print ("SERVER:", *args, flush=flush)

	#-- Concurrently process all documents in workingDir
	def processDocuments (workingDir):
		if workingDir is None: 
			return jsonify({'error': f"Directorio de trabajo: '{workingDir}' inválido."}), 400

		# Create and start threads for processing files
		inputFiles = [x for x in os.listdir (workingDir, ) if EcuServer.isValidDocument (x)]
		threads = []
		os.chdir (workingDir)
		for filename in inputFiles:
			thread = threading_Thread (target=mainDoc, args=(filename,))
			threads.append (thread)
			thread.start()

		# Wait for all threads to finish
		for k, thread in enumerate (threads):
			thread.join()
			docFilepath = os.path.join (workingDir, inputFiles [k])
			EcuServer.printx (f"Procesamiento exitoso del documento: '{docFilepath}'")

		message = "Procesamiento exitoso de todos los documentos."
		return message
		
	#-- Check if document filename is an image (.png) or a PDF file (.pdf)
	def isValidDocument (filename):
		extension = filename.split (".")[1]
		if extension.lower() in ["png", "pdf"]:
			return True
		return False

#----------------------------------------------------------
# Run Azure analysis for custom "cartaporte" document
#----------------------------------------------------------
def mainDoc (inputFilepath):
	try:
		filename	  = os.path.basename (inputFilepath)

		print (">>> Input File	  : ", inputFilepath)
		print (">>> Current Dir   : ", os.getcwd())

		# Document analysis using Azure cloud
		docJsonFile  = EcuDoc.processDocument (inputFilepath)
		mainFields	 = EcuInfo.getMainFields (docJsonFile)

		EcuDoc.saveFields (mainFields, filename, "RESULTS")
	except Exception as ex:
		print ("ERROR procesando documentos:", ex) 
		return (f"ERROR procesando documento '{inputFilepath}'")

	return (f"{inputFilepath} successfuly processed")

#-----------------------------------------------------------
# Run cloud analysis
#-----------------------------------------------------------
class EcuDoc:
	def processDocument (inputFilepath):
		print ("\n>>>", EcuAzure.getCloudName(), "document processing...")
		docJsonFile = None
		try:
			filename = os.path.basename (inputFilepath)
			docJsonFile = EcuDoc.loadPreviousDocument (filename)
			if (docJsonFile is None):
				docJsonFile = EcuAzure.analyzeDocument (inputFilepath)
		except Exception as ex:
			print (f"ERROR procesando documento '{inputFilepath}'") 
			raise
		return docJsonFile

	#-- Load previous result.
	def loadPreviousDocument (filename):
		try:
			docJsonFile = None
			#filename = os.path.basename (filename)
			pickleFilename = f"{filename.split ('.')[0]}-{EcuAzure.getCloudName()}-CACHE.pkl"
			print ("\t>>> Looking for previous file: ", pickleFilename)
			if os.path.isfile (pickleFilename): 
				print ("\t>>> Loading previous result from pickle file:", pickleFilename )
				with open (pickleFilename, 'rb') as inFile:
					result = pickle_load (inFile)
				docJsonFile = EcuAzure.saveResults (result, filename)
		except:
			print (f"ERROR cargando documento: '{filename}'")
			raise

		return (docJsonFile)

	#-- Save fields dict in JSON 
	def saveFields (fieldsDict, filename, suffixName):
		prefixName	= filename.split(".")[0]
		outFilename = f"{prefixName}-{suffixName}.json"
		print ("\t>>> Saving fields into", outFilename)
		with open (outFilename, "w") as fp:
			json.dump (fieldsDict, fp, indent=4, default=str)

#-----------------------------------------------------------
# Custom document built with the Azure Form Recognizer client library. 
#-----------------------------------------------------------
class EcuAzure:
	AzureKeyCredential = azure.core.credentials.AzureKeyCredential

	#-- Online processing request return the first document 
	def analyzeDocument (docFilepath):
		docJsonFile = None
		try:

			print ("\t>>>", "Analyzing document...")
			credentialsDict  = EcuAzure.initCredentials ()
			lgEndpoint		 = credentialsDict ["endpoint"]
			lgKey			 = credentialsDict ["key"]	
			lgLocale		 = credentialsDict ["locale"]
			lgModel			 = credentialsDict ["modelId"]

			lgCredential = EcuAzure.AzureKeyCredential (lgKey)
			docClient	 = DocumentAnalysisClient (endpoint = lgEndpoint, 
												   credential = lgCredential)
			# Read the file into memory
			with open(docFilepath, "rb") as fp:
				poller = docClient.begin_analyze_document (lgModel, document=fp, locale=lgLocale)

			print ("\t>>>", "Polling result....")
			result	  = poller.result()
			document  = result.documents [0]
			docDict   = document.to_dict ()

			# Save original result as pickled and json files
			print ("\t>>>", "Saving result....")
			docFilename = os.path.basename (docFilepath)
			docJsonFile = EcuAzure.saveResults (result, docFilename)
		except Exception as ex:
			print ("EXCEPCION analizando documento." )
			print (traceback_format_exc())
			sys.exit (1)
			
		return (docJsonFile)

	#-----------------------------------------------------------
	# Read Azure account variables from environment Azure variable
	# Variable has the path to Azure JSON keys file
	# Also, initialize locale and Azure model id
	#-----------------------------------------------------------
	def initCredentials ():
		try:
			print ("\t>>> Reading credentials...")
			credentialsDict = {}
			with open (APP_KEYS_FILE) as fp:
				keys = json.load (fp)

			credentialsDict ["endpoint"] = keys.get ("endpoint")
			credentialsDict ["key"]		 = keys.get ("key1")
			credentialsDict ["locale"]	 = "es-CO"
			credentialsDict ["modelId"]  = "TrainModelCartaportesNTARegiones"
		except Exception as ex:
			print ("EXCEPCION: Problemas inicializando credenciales.")
			print (traceback_format_exc())
			sys.exit (1)

		return (credentialsDict)

	#-- Save request result as pickle and json files
	def saveResults (result, docFilepath):
		rootName = docFilepath.split ('.')[0]

		print (f"\t>>> Guardando resultados de Azure en %s-XXX.yyy" % rootName)

		# Save results as Pickle 
		outPickleFile = f"{rootName}-{EcuAzure.getCloudName()}-CACHE" ".pkl"
		with open(outPickleFile, 'wb') as outFile:
			pickle_dump (result, outFile)

		# Save results as JSON file
		resultDict		= result.to_dict ()
		outJsonFile = f"{rootName}-{EcuAzure.getCloudName()}-CACHE" ".json"
		with open (outJsonFile, 'w') as outFile:
			json.dump (resultDict, outFile, indent=4, default=str)

		# Save result document as JSON file
		document	 = result.documents [0]
		documentDict = document.to_dict ()
		outJsonFile = f"{rootName}-DOCUMENT-NONEWLINES" ".json"
		with open (outJsonFile, 'w') as outFile:
			json.dump (documentDict, outFile, indent=4, default=str)

		# Save document with original (newlines) content
		documentDictNewlines = EcuAzure.getDocumentWithNewlines (resultDict)
		docJsonNewlinesFile = f"{rootName}-DOCUMENT" ".json"
		with open (docJsonNewlinesFile, 'w') as outFile:
			json.dump (documentDictNewlines, outFile, indent=4, default=str)

		return (docJsonNewlinesFile)

	def getCloudName ():
		return "azure"


	#-- Add newlines to document content 
	def getDocumentWithNewlines (resultsDict):
		#-- Determine whether two floating-point numbers are close in value.
		def isClose(a, b, rel_tol=1e-09, abs_tol=0.0):
			if abs(a - b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol):
				return True
			return False

		#-- Check if the line is whithin the field box dimensions --
		def isContained (line, field):
			ERROR = 0.05
			lineContent = line ["content"]
			xl = round (line ["polygon"][0]["x"], 2)
			yl = round (line ["polygon"][0]["y"], 2)

			fieldContent = field ["content"]
			if (fieldContent == None):
				return False

			xf1   = round (field ["bounding_regions"][0]["polygon"][0]["x"], 2)
			yf1   = round (field ["bounding_regions"][0]["polygon"][0]["y"], 2)
			yf2   = round (field ["bounding_regions"][0]["polygon"][2]["y"], 2)

			if (lineContent in fieldContent and 
					isClose (xl, xf1, abs_tol=ERROR) and 
					(isClose (yl, yf1) or yf1 < yl and yl < yf2)):
				return True

			return False
		#--------------------------------------------------------------

		lines  = resultsDict ["pages"][0]["lines"]
		fields = resultsDict ["documents"][0]["fields"]

		for line in lines:
			lineContent = line ["content"]
			for key in fields:
				field = fields [key]
				fieldContent = field ["content"]

				if isContained (line, field):
					newlineContent = fieldContent.replace (lineContent+" ", lineContent+"\n")
					fields [key] ["content"] = newlineContent
					break

			resultsDict ["documents"][0]["fields"] = fields

		return (resultsDict ["documents"][0])

#----------------------------------------------------------
# Class that gets main info from Ecuapass document 
#----------------------------------------------------------
class EcuInfo:
	ecudoc = {}		  # Dic for Ecuappass document info

	#-- Main function for testing
	def main ():
		inputJsonFile = "CPI-COCO003629-DOCUMENT.json"
		EcuInfo.getMainFields (inputJsonFile)

	def getMainFields (inputJsonFile):
		""" Get data and value from document main fields"""

		print (">>> Obteniendo principales valores del documento %s..." % inputJsonFile)
		# Get all fields from document
		fields = EcuInfo.getFieldsFromDocument (inputJsonFile)

		EcuInfo.ecudoc ["01_Distrito"]			= EcuDB.getDistrito ("TULCAN", "ecu")
		EcuInfo.ecudoc ["02_NumeroCPIC"]		= EcuInfo.getNumeroDocumento (fields)
		EcuInfo.ecudoc ["03_MRN"]				= "CEC202340350941"
		EcuInfo.ecudoc ["04_MSN"]				= "0001"
		EcuInfo.ecudoc ["05_TipoProcedimiento"] = EcuInfo.getTipoProcedimiento (fields)
		EcuInfo.ecudoc ["06_EmpresaTransporte"] = "N.T.A."
		EcuInfo.ecudoc ["07_DepositoMercancia"] = EcuInfo.getDepositoMercancia (fields)
		EcuInfo.ecudoc ["08_DirTransportista"]	= EcuDB.getDistrito ("TULCAN", "dir")
		EcuInfo.ecudoc ["09_NroIdentificacion"] = EcuInfo.getNroIdentificacion (fields)

		# Remitente company box
		entity								 = EcuInfo.getEntitiesCompany (fields, "Remitente")
		EcuInfo.ecudoc ["10_PaisRemitente"]		= entity ["pais"] 
		EcuInfo.ecudoc ["11_TipoIdRemitente"]	 = entity ["tipoId"] 
		EcuInfo.ecudoc ["12_NroIdRemitente"]	 = entity ["numeroId"] 
		EcuInfo.ecudoc ["13_NroCertSanitario"]	 = None
		EcuInfo.ecudoc ["14_NombreRemitente"]	 = entity ["nombre"] 
		EcuInfo.ecudoc ["15_DireccionRemitente"] = entity ["direccion"] 

		# Destinatario company box
		entity									= EcuInfo.getEntitiesCompany (fields, "Destinatario")
		EcuInfo.ecudoc ["16_PaisDestinatario"]		= entity ["pais"] 
		EcuInfo.ecudoc ["17_TipoIdDestinatario"]	= entity ["tipoId"] 
		EcuInfo.ecudoc ["18_NroIdDestinatario"] = entity ["numeroId"] 
		EcuInfo.ecudoc ["19_NombreDestinatario"]	= entity ["nombre"] 
		EcuInfo.ecudoc ["20_DireccionDestinatario"] = entity ["direccion"] 

		# Consignatario company box
		entity								 = EcuInfo.getEntitiesCompany (fields, "Consignatario")
		EcuInfo.ecudoc ["21_PaisConsignatario"]		 = entity ["pais"] 
		EcuInfo.ecudoc ["22_TipoIdConsignatario"]	 = entity ["tipoId"] 
		EcuInfo.ecudoc ["23_NroIdConsignatario"]	 = entity ["numeroId"] 
		EcuInfo.ecudoc ["24_NombreConsignatario"]	 = entity ["nombre"] 
		EcuInfo.ecudoc ["25_DireccionConsignatario"] = entity ["direccion"] 

		#-- Location box: 28..36
		# Notificado location box
		entity							  = EcuInfo.getEntitiesCompany (fields, "Notificado")
		EcuInfo.ecudoc ["26_NombreNotificado"]	  = entity ["nombre"] 
		EcuInfo.ecudoc ["27_DireccionNotificado"] = entity ["direccion"] 
		EcuInfo.ecudoc ["28_PaisNotificado"]	  = entity ["pais"] 

		# Recepcion location box
		entity						   = EcuInfo.getEntitiesLocation (fields, "Recepcion")
		EcuInfo.ecudoc ["29_PaisRecepcion"]    = entity ["pais"] 
		EcuInfo.ecudoc ["30_CiudadRecepcion"]  = entity ["ciudad"] 
		EcuInfo.ecudoc ["31_FechaRecepcion"]   = entity ["fecha"] 

		# Embarque location box
		entity						  = EcuInfo.getEntitiesLocation (fields, "Embarque")
		EcuInfo.ecudoc ["32_PaisEmbarque"]	  = entity ["pais"] 
		EcuInfo.ecudoc ["33_CiudadEmbarque"]  = entity ["ciudad"] 
		EcuInfo.ecudoc ["34_FechaEmbarque"]   = entity ["fecha"] 

		# Entrega location box
		entity						 = EcuInfo.getEntitiesLocation (fields, "Entrega")
		EcuInfo.ecudoc ["35_PaisEntrega"]	 = entity ["pais"] 
		EcuInfo.ecudoc ["36_CiudadEntrega"]  = entity ["ciudad"] 
		EcuInfo.ecudoc ["37_FechaEntrega"]	 = entity ["fecha"] 

		# 37..38: Condiciones
		condiciones							= EcuInfo.getCondiciones (fields)
		EcuInfo.ecudoc ["38_CondicionesTransporte"] =  condiciones ["transporte"]
		EcuInfo.ecudoc ["39_CondicionesPago"]		=  condiciones ["pago"]

		# 39..41: Bultos info
		bultos					  = EcuInfo.getBultosInfo (fields)
		EcuInfo.ecudoc ["40_PesoNeto"]	  =  bultos ["pesoNeto"]
		EcuInfo.ecudoc ["41_PesoBruto"]   =  bultos ["pesoBruto"]
		EcuInfo.ecudoc ["42_TotalBultos"] =  bultos ["total"]
		EcuInfo.ecudoc ["43_Volumen"]	  =  bultos ["volumen"]
		EcuInfo.ecudoc ["44_OtraUnidad"]  =  bultos ["otraUnidad"]

		# Mercancia
		mercancia						= EcuInfo.getMercanciaInfo (fields)
		EcuInfo.ecudoc ["45_PrecioMercancias"]	= mercancia ["precio"]
		EcuInfo.ecudoc ["46_INCOTERM"]			= mercancia ["incoterm"] 
		EcuInfo.ecudoc ["47_TipoMoneda"]		= mercancia ["moneda"] 
		EcuInfo.ecudoc ["48_PaisMercancia"]		= mercancia ["pais"] 
		EcuInfo.ecudoc ["49_CiudadMercancia"]	= mercancia ["ciudad"] 

		# Gastos
		gastos								  = EcuInfo.getGastosInfo (fields)
		EcuInfo.ecudoc ["50_GastosRemitente"]		  = gastos ["fleteRemi"] 
		EcuInfo.ecudoc ["51_MonedaRemitente"]		  = gastos ["monedaRemi"] 
		EcuInfo.ecudoc ["52_GastosDestinatario"]	  = gastos ["fleteDest"] 
		EcuInfo.ecudoc ["53_MonedaDestinatario"]	  = gastos ["monedaDest"] 
		EcuInfo.ecudoc ["54_OtrosGastosRemitente"]	  = gastos ["otrosGastosRemi"] 
		EcuInfo.ecudoc ["55_OtrosMonedaRemitente"]	  = gastos ["otrosMonedaRemi"] 
		EcuInfo.ecudoc ["56_OtrosGastosDestinatario"] = gastos ["otrosGastosDest"] 
		EcuInfo.ecudoc ["57_OtrosMonedaDestinataio"]  = gastos ["otrosMonedaDest"] 
		EcuInfo.ecudoc ["58_TotalRemitente"]		  = gastos ["totalGastosRemi"] 
		EcuInfo.ecudoc ["59_TotalDestinatario"]		  = gastos ["totalGastosDest"] 

		# Documentos remitente
		EcuInfo.ecudoc ["60_DocsRemitente"] = EcuInfo.getDocsRemitente (fields)

		# Emision location box
		entity						 = EcuInfo.getEntitiesLocation (fields, "Recepcion")
		EcuInfo.ecudoc ["61_FechaEmision"]	 = entity ["fecha"] 
		EcuInfo.ecudoc ["62_PaisEmision"]	 = entity ["pais"] 
		EcuInfo.ecudoc ["63_CiudadEmision"]  = entity ["ciudad"] 

		# Instrucciones y Observaciones
		entity						  = EcuInfo.getInstruccionesObservaciones (fields)
		EcuInfo.ecudoc ["64_Instrucciones"]   = entity ["instrucciones"]
		EcuInfo.ecudoc ["65_Observaciones"]   = entity ["observaciones"]

		# Detalles
		EcuInfo.ecudoc ["66_Secuencia"]    = "1"
		EcuInfo.ecudoc ["67_CantidadBultos"]  = EcuInfo.ecudoc ["42_TotalBultos"]
		EcuInfo.ecudoc ["68_TipoEmbalaje"]	   = bultos ["embalaje"]
		EcuInfo.ecudoc ["69_MarcasNumeros"]   = bultos ["marcas"]
		EcuInfo.ecudoc ["70_PesoNeto"]		   = EcuInfo.ecudoc ["40_PesoNeto"]
		EcuInfo.ecudoc ["71_PesoBruto"]    = EcuInfo.ecudoc ["41_PesoBruto"]
		EcuInfo.ecudoc ["72_Volumen"]		   = EcuInfo.ecudoc ["43_Volumen"]
		EcuInfo.ecudoc ["73_OtraUnidad"]	   = EcuInfo.ecudoc ["44_OtraUnidad"]

		# IMOs
		EcuInfo.ecudoc ["74_Subpartida"]	   = None
		EcuInfo.ecudoc ["75_IMO1"]			   = None
		EcuInfo.ecudoc ["76_IMO2"]			   = None
		EcuInfo.ecudoc ["77_IMO2"]			   = None
		EcuInfo.ecudoc ["78_NroCertSanitario"] = EcuInfo.ecudoc ["13_NroCertSanitario"]
		EcuInfo.ecudoc ["79_DescripcionCarga"] = bultos ["descripcion"]

		#EcuInfo.printFieldsValues (EcuInfo.ecudoc)
		return (EcuInfo.ecudoc)

	#-- Get instrucciones y observaciones
	def getInstruccionesObservaciones (fields):
		instObs = {}
		instObs ["instrucciones"] = fields ["21_Instrucciones"]["value"]
		instObs ["observaciones"] = fields ["22_Observaciones"]["value"]

		return instObs
		
	#-----------------------------------------------------------
	# Get id type "tipoId" comparing with id types in data info
	#-----------------------------------------------------------
	def getInfoIdentificacion (text):
		reId   = r"(?P<tipo>(RUC|NIT))\s*:?\s*(?P<id>\d+\-?\d*)"
		result = re.search (reId, text, flags=re.S)

		# Tipo id
		tipoId = None if result == None else result.group ("tipo")
		tiposIdList = EcuDB.getTiposId ()
		if tipoId is not None and tipoId not in tiposIdList:
			tipoId = "OTROS"

		# Numero id
		nroId = None if result == None else result.group ("id")

		idInfo = {"tipo": tipoId, "numero": nroId}
		return (idInfo)

	#-----------------------------------------------------------
	# Get info from 'documentos recibidos remitente'
	#-----------------------------------------------------------
	def getDocsRemitente (fields):
		return fields ["18_Documentos"]["value"]
	#-----------------------------------------------------------
	# Get 'gastos' info: monto, moneda, otros gastos
	#-----------------------------------------------------------
	def getGastosInfo (fields):
		gastos = {}
		tabla = fields ["17_Gastos"]["value"]

		#-- Local: Return value or None if problems ------
		def getValueTabla (firstKey, secondKey):
			try:
				return tabla [firstKey]["value"][secondKey]["value"]
			except:
				print (f"EXCEPTION: Problemas con campo '{firstKey}'-'{secondKey}'. Asignado valor 'None'.")
				return None
		#--------------------------------------------------

		# DESTINATARIO:
		#-- Valor flete 
		gastos ["fleteDest"]  = getValueTabla ("ValorFlete", "MontoDestinatario")
		gastos ["monedaDest"] = getValueTabla ("ValorFlete", "MonedaDestinatario")

		#-- Otros gastos suplementarios
		gastos ["otrosGastosDest"] = getValueTabla ("OtrosGastos", "MontoDestinatario")
		gastos ["otrosMonedaDest"] = getValueTabla ("OtrosGastos", "MonedaDestinatario")

		#-- Total
		gastos ["totalGastosDest"] = getValueTabla ("Total", "MontoDestinatario")
		gastos ["totalMonedaDest"] = getValueTabla ("Total", "MonedaDestinatario")

		# REMITENTE: Assumed not exist for N.T.A. company
		gastos ["fleteRemi"] = None
		gastos ["monedaRemi"] = None
		gastos ["otrosGastosRemi"] = None
		gastos ["otrosMonedaRemi"] = None
		gastos ["totalGastosRemi"]	= None
		gastos ["totalMonedaRemi"] = None

		return gastos


	#-----------------------------------------------------------
	# Get info from mercancia: INCONTERM, Tipo Moneda, Precio
	#-----------------------------------------------------------
	def getMercanciaInfo (fields):
		mercancia = {}
		text	  = fields ["16_Incoterms"]["value"]

		# Precio
		rePrecio = r"(\d+[.]?\d*)"	# RE for float number 
		mercancia ["precio"] = EcuInfo.getValueRE (rePrecio, text)

		# Inconterm
		incoterms	= EcuDB.getIncoterms ()
		termsString = "|".join (incoterms)
		reTerms = rf"\b({termsString})\b" # RE for incoterm
		mercancia ["incoterm"] = EcuInfo.getValueRE (reTerms, text)

		# Moneda
		mercancia ["moneda"] = "USD"

		# Ciudad
		reCiudad = rf"\b(?:{termsString})\b\W+\b(.*)\b" # RE for city after incoterm
		ciudad	 = EcuInfo.getValueRE (reCiudad, text)

		# Search 'pais' in previos boxes
		mercancia ["ciudad"] = ciudad
		mercancia ["pais"]	 = None
		if (ciudad != None):
			if ciudad in EcuInfo.ecudoc ["30_CiudadRecepcion"]:
				mercancia ["pais"]	 = EcuInfo.ecudoc ["29_PaisRecepcion"]
				mercancia ["ciudad"] = EcuInfo.ecudoc ["30_CiudadRecepcion"]
			elif ciudad in EcuInfo.ecudoc ["33_CiudadEmbarque"]:
				mercancia ["pais"]	 = EcuInfo.ecudoc ["32_PaisEmbarque"]
				mercancia ["ciudad"] = EcuInfo.ecudoc ["33_CiudadEmbarque"]
			elif ciudad in EcuInfo.ecudoc ["36_CiudadEntrega"]:
				mercancia ["pais"]	 = EcuInfo.ecudoc ["35_PaisEntrega"]
				mercancia ["ciudad"] = EcuInfo.ecudoc ["36_CiudadEntrega"]

		return mercancia
		
	#-----------------------------------------------------------
	# Get "bultos" info:"peso neto, peso bruto, total
	#-----------------------------------------------------------
	def getBultosInfo (fields):
		bultos = {}
		reNumber = r"(\d+[.]?\d*)"	# RE for extracting a float number 

		bultos ["pesoNeto"]   = EcuInfo.getValueRE (reNumber, fields ["13a_Peso_Neto"]["value"])
		bultos ["pesoBruto"]  = EcuInfo.getValueRE (reNumber, fields ["13b_Peso_Bruto"]["value"])
		bultos ["volumen"]	  = EcuInfo.getValueRE (reNumber, fields ["14_Volumen"]["value"])
		bultos ["otraUnidad"] = EcuInfo.getValueRE (reNumber, fields ["15_Otras_Unidades"]["value"])

		# Total
		reTotal = r".*?(?:TOTAL)?\s*(\d+).*" # RE for extracting value after a word
		text = fields ["10_CantidadClase_Bultos"]["value"]
		bultos ["total"]	  = EcuInfo.getValueRE (reTotal, text, flags=re.I) 

		# Tipo embalaje
		reEmbalaje = r"(\w+)$"
		bultos ["embalaje"]   = EcuInfo.getValueRE (reEmbalaje, text, flags=re.I) 

		# Marcas y numeros
		text = fields ["11_MarcasNumeros_Bultos"]["value"]
		bultos ["marcas"] = "SIN MARCAS" if text == None else text

		# Descripcion
		bultos ["descripcion"] = fields ["12_Descripcion_Bultos"]["value"]

		return bultos

	#-----------------------------------------------------------
	# Extracts first value from regular expresion. Validate input and output 
	#-----------------------------------------------------------
	def getValueRE (RE, text, flags=re.I):
		if text != None:
			result = re.search (RE, text, flags=flags)
			if result != None:
				return result.group(1)
		return None

	#-----------------------------------------------------------
	# Get "transporte" and "pago" conditions
	#-----------------------------------------------------------
	def getCondiciones (fields):
		conditions = {}
		text = fields ["09_Condiciones"]["value"]
		reTwoTexts = r"^(?P<pago>.*?)\.(?P<transporte>.*)$"
		result = re.search (reTwoTexts, text)
		conditions ["pago"]		  = None if result == None else result.group ("pago").strip()
		conditions ["transporte"] = None if result == None else result.group ("transporte").strip()
		return conditions
		
	#-----------------------------------------------------------
	# Get location entities from box text: ciudad, pais, fecha 
	# Boxes: Recepcion, Embarque, Entrega
	#-----------------------------------------------------------
	def getEntitiesLocation (fields, type):
		""" 28...36 """
		text = ""
		if type == "Recepcion":
			text   = fields ["06_Recepcion"]["content"]
		elif type == "Embarque":
			text   = fields ["07_Embarque"]["content"]
		elif type == "Entrega":
			text   = fields ["08_Entrega"]["content"]
		elif type == "Emision":
			text   = fields ["19_Emision"]["value"]

		entities = EcuInfo.getEntitiesLocationDefult (text)

		return (entities)

	def getEntitiesLocationDefult (text):
		entities = {}
		 
		# Pais
		paisesString = "|".join (EcuDB.getPaises ())
		reCiudadPais = r"\b(?P<ciudad>.*?)\b[\s\-]+\b(?P<pais>"+paisesString +r")\b"
		result = re.search (reCiudadPais, text, flags=re.I)
		entities ["ciudad"] = None if result == None else result.group ("ciudad")
		entities ["pais"]	= None if result == None else result.group ("pais")

		# Fecha
		reDate = r"\b\d{1,2}-\d{1,2}-\d{4}\b"
		result = re.search (reDate, text, flags=re.S )
		entities ["fecha"] = None if result == None else result [0]

		# Ciudad
		return (entities)

	#-----------------------------------------------------------
	# Get company entities from box text
	# Boxes: Remitente, Destinatario, Consignatario, Notificado
	#-----------------------------------------------------------
	def getEntitiesCompany (fields, type):
		""" 10...27 """
		text = ""
		if type == "Remitente":
			text   = fields ["02_Remitente"]["content"]
		elif type == "Destinatario":
			text   = fields ["03_Destinatario"]["content"]
		elif type == "Consignatario":
			text   = fields ["04_Consignatario"]["content"]
		elif type == "Notificado":
			text   = fields ["05_Notificado"]["content"]

		lines  = text.split ("\n")
		entities = None
		if len (lines) == 3:
			entities = EcuInfo.getEntitiesDefaultStructure_3Lines (lines)
		elif len (lines) == 4:
			entities = EcuInfo.getEntitiesDefaultStructure_4Lines (lines)
		return (entities)

	#-- Assume default 3 lines: nombre \n direccion \n ciudad-pais. ID:Numero
	def getEntitiesDefaultStructure_3Lines (lines):
		# Line 0: Name
		entities = {}
		entities ["nombre"]  = lines [0]

		# Line 1: Address
		entities ["direccion"] = lines [1]
		 
		# Line 2: Pais and ciudad
		text  = lines [2]
		reLocation = f"(?P<ciudad>.*?)[\-\s]*(?P<pais>ECUADOR|COLOMBIA)"
		result = re.search (reLocation, text, flags=re.S )
		entities ["ciudad"] = None if result == None else result.group ("ciudad")
		entities ["pais"] = None if result == None else result.group ("pais")

		# Line 2: Id (RUC|NIT|...)
		idInfo = EcuInfo.getInfoIdentificacion (text)
		entities ["tipoId"]   = idInfo ["tipo"]
		entities ["numeroId"] = idInfo ["numero"] 
		return (entities)

	# Assume default 4 lines: nombre, address01 \n address02, ciudad-pais + ID:Number
	def getEntitiesDefaultStructure_4Lines (lines):
		newLines = [lines [0], lines [1] + " " + lines [2], lines [3]]
		entities = EcuInfo.getEntitiesDefaultStructure_3Lines (newLines)
		return (entities)

	#-----------------------------------------------------------
	def getNroIdentificacion (fields):
		""" 09 """
		empresa  = EcuInfo.ecudoc ["06_EmpresaTransporte"]
		numeroId = EcuDB.getNumeroIdEmpresa (empresa)
		return numeroId

	def getNumeroDocumento (fields):
		""" 02 """
		return fields ["00b_Numero"]["value"]

	def getTipoProcedimiento (fields):
		""" 05 """
		distrito = EcuInfo.ecudoc ["01_Distrito"] 
		if distrito == "TULCAN":
			return ("IMPORTACION")
		return None

	def getDepositoMercancia (fields):
		""" 07 """
		text = fields ["21_Instrucciones"]["value"]
		if (text != None):
			text = text.replace ("\n", " ")
			text = text.strip ()
			values = text.split ()
			bodega = values [-1] if len (values) > 1 else None
			return (bodega)

		return None

	#--
	def getPaisRemitente (fields):
		key = "22_Observaciones"
		data, value = getCommonDataValues (fields, key)
		print ("DATA: \n", data)
		print ("VALUES: \n", value)


		
	#-- Get data/values from table "Gastos A Pagar". 
	#-- Assumes only one item. Return the first one
	def getGastosPagarFromCartaporte (fieldsDict, key):
		fieldColumn = fieldsDict [key]
		def getColumnValue (itemDict, key):
			value = itemDict [key]["value"] if key in itemDict.keys () else None
			return (value)

		gastosDic = {"17_Gastos_A_Pagar":""}

		valorFlete = fieldColumn ["value"][0]["value"]
		gastosDic ["17a_Valor_Flete_Monto_Remitente"]	  = getColumnValue (valorFlete, "Monto_Remitente") 
		gastosDic ["17b_Valor_Flete_Moneda_Remitente"]	  = getColumnValue (valorFlete, "Moneda_Remitente") 
		gastosDic ["17c_Valor_Flete_Monto_Destinatario"]  = getColumnValue (valorFlete, "Monto_Destinatario") 
		gastosDic ["17d_Valor_Flete_Moneda_Destinatario"] = getColumnValue (valorFlete, "Moneda_Destinatario") 

		OtrosGastos = fieldColumn ["value"][1]["value"]
		gastosDic ["17e_Otros_Gastos_Monto_Remitente"]	   = getColumnValue (OtrosGastos, "Monto_Remitente") 
		gastosDic ["17f_Otros_Gastos_Moneda_Remitente"]    = getColumnValue (OtrosGastos, "Moneda_Remitente") 
		gastosDic ["17g_Otros_Gastos_Monto_Destinatario"]  = getColumnValue (OtrosGastos, "Monto_Destinatario") 
		gastosDic ["17h_Otros_Gastos_Moneda_Destinatario"] = getColumnValue (OtrosGastos, "Moneda_Destinatario") 

		total = fieldColumn ["value"][2]["value"]
		gastosDic ["17i_TOTAL_Monto_Remitente"]		= getColumnValue (total, "Monto_Remitente") 
		gastosDic ["17j_TOTAL_Moneda_Remitente"]	= getColumnValue (total, "Moneda_Remitente") 
		gastosDic ["17k_TOTAL_Monto_Destinatario"]	= getColumnValue (total, "Monto_Destinatario") 
		gastosDic ["17l_TOTAL_Moneda_Destinatario"] = getColumnValue (total, "Moneda_Destinatario") 

		return (gastosDic, gastosDic)

	#-- Get data/values from table mercancia. 
	#-- Assumes only one item. Return the first one
	def getMercanciaFromCartaporte (fieldColumn, columnName):
		#itemListData, itemListValues = [], []
		data, value = None, None
		
		for item in fieldColumn ["value"]:
			itemDict = item ["value"]
			data, value = getCommonDataValues (itemDict, columnName)
			break
		return (data, value)

			#itemListData.append (data)
			#itemListValues.append (value)
		#return (itemListData, itemListValues)

	#-- Get common data from field
	#-- Common fields are used for info and checking
	def getCommonDataValues (fields, key):
		data, value = None, None
		if key in fields.keys ():
			data = {}
			data ["value_type"] = fields [key]["value_type"]
			data ["content"]	= fields [key]["content"]
			data ["confidence"] = fields [key]["confidence"]
			data ["value"] = fields [key]["value"] if "value" in fields [key].keys() else fields [key]["content"]
			value = data ["value"]

		return data, value

	#-- Get first line when data get multiple lines
	#-- Generally, important info is in first line
	def getValueFirstLine (field, data):
		data ["value"] = field ["content"].split ("\n")[0] 
		return (data, data ["value"])

	#-- Get document fields from Azure results
	def getFieldsFromDocument (inputJsonFile):
		print ("\t>>> Getting fields from Azure document...")

		document = json.load (open (inputJsonFile))
		fields	 = document ["fields"]
		return (fields)

	#-- Get data from field (source, type, value, and confidence)
	def getDataFromAzureField (field):
		data = {}
		data ["source"]		= "azure"
		data ["type"]		= field ["value_type"]
		data ["confidence"] = field ["confidence"]
		data ["text"]		= field ["content"]

		#print ("\t>>>> Field:", field)
		if field['value_type'] == 'float':
			data ["value"] =  field['value']
		elif field['value_type'] == 'currency':
			data ["value"] =  field['value']['amount']
		elif field['value_type'] == 'string':
			data ["value"] =  removeDupsString (field['value'])
		elif field['value_type'] == 'date':
			data ["value"] =  field['value']			 
		elif field['value_type'] == 'address':
			data ["value"] =  field['content']			   
		elif field['value_type'] == 'array':
			itemInfo = "\n\t"
			for item in field["valueArray"]:
				itemInfo += getDataFromAzureField(item) + "\n\t"
			data ["value"] =  itemInfo[:-3] 
		elif field['value_type'] == 'object':
			objectKeys = field['valueObject'].keys()
			item_info = "" 
			for ok in objectKeys:
				item_info += ok + ":" + str (getDataFromAzureField(field['valueObject'][ok])) + " "
			data ["value"] =  item_info
		elif field['value_type'] == 'number':
			data ["value"] =  field['valueNumber']
		elif field['value_type'] == 'time':
			data ["value"] =  field['valueTime']
		elif field['value_type'] == 'phoneNumber':
			data ["value"] =  field['valuePhoneNumber']
		else:
			print ("\t>>> Skipping Unsupported Type")

		return (data)

	#-----------------------------------------------------------
	# Remove duplicates from string
	#-----------------------------------------------------------
	def removeDupsString (string):
		names = string.split (os.linesep)
		if (len (names) > 1):
			for i in range (len(names)-1):
				if (names [i] in names [i+1:]): 
					string = "\n".join (names [i+1:])
				names = string.split (os.linesep)

		return (string)

	#----------------------------------------------------------
	#-- Print fields values
	#----------------------------------------------------------
	def printFieldsValues (fields):
		keys = sorted (fields.keys())
		for key in keys:
			item = fields [key]
			if type (item) != dict:
				print (f"\t\t{key}: {fields[key]}")
			else:
				printFieldsValues (item)
	#----------------------------------------------------------
	#-- Print fields data
	#----------------------------------------------------------
	def printFieldsData (fields):
		print ("\t>>> Printing main values...")
		keys = sorted (fields.keys())
		for key in keys:
			value = fields [key]
			if type (value) != list:
				print (f"\t\t{key}: {value}")
			else:
				for i, item in enumerate(value):
					print ("\t\tItem %s:\t" % i)
					for k in item.keys():
						print (f"\t\t\t{k}: {item [k]}")

	#-----------------------------------------------------------
	# Not used functions (maybe obsolete)
	#-----------------------------------------------------------
	#-----------------------------------------------------------
	# Save data in JSON and CSV formats
	#-----------------------------------------------------------
	def saveData (fieldsDict, mainFieldsDict, inputJsonFile):
		outName = inputJsonFile.split (".")[0]

		print ("\t>>> Writing ALL fields to JSON file...")
		outJsonFile = "%s-FIELDS-ALL.json" % outName
		with open (outJsonFile, "w") as fp:
			json.dump (fieldsDict, fp, indent=4, default=str)

		print ("\t>>> Writing MAIN fields to JSON file...")
		outJsonFile = "%s-FIELDS-MAIN.json" % outName
		with open (outJsonFile, "w") as fp:
			json.dump (mainFieldsDict, fp, indent=4, default=str)

	#	 print ("\t>>> Writing main values to CSV file...")
	#	 outCsvFile = "%s-TABLE.csv" % inputJsonFile.split (".")[0]
	#	 with open (outCsvFile, "w") as csvFile:
	#		 csvFile.write ("Cliente,Vendedor, Id, Fecha, Total"+os.linesep)
	#		 csvFile.write (",".join(fieldsList))

		return (outJsonFile)

#-----------------------------------------------------------
#-- Class containing data for filling Ecuapass document
#-----------------------------------------------------------
class EcuDB:
	ecudb = {
		"tiposId": {"RUC", "CEDULA", "CATASTRO", "PASAPORTE", "OTROS"},

		"distritos": { 
			"TULCAN" : {"dir": "ARGENTINA Y JUAN LEON MERA", "ecu": "TULCAN"},
			"IPIALES" : "Centro Comercial Rumichaca Of. 02"
			}, 
		"empresas": { 
			"N.T.A." : { 
				"nombre" : "NUEVO TRANSPORTE DE AMERICA COMPAÑIA LIMITADA", 
				"tipoId" : "RUC", 
				"numeroId" : "1791834461001"
				}
			}, 
		"paises": ["Ecuador", "Colombia", "Perú", "Bolivia"],
		"incoterms": {
			"EXW": "En Fábrica",
			"FCA": "Franco transportista",
			"CPT": "Transporte Pagado Hasta",
			"CIP": "Transporte y Seguro Pagados hasta",
			"DAT": "Entregado en Terminal",
			"DAP": "Entregado en un Lugar",
			"DDP": "Entregado con Pago de Derechos",
			"FAS": "Franco al costado del buque",
			"FOB": "Franco a bordo",
			"CFR": "Costo y flete",
			"CIF": "Costo: flete y seguro"
			}
		}

	def getTiposId ():
		return EcuDB.ecudb ["tiposId"]

	def getIncoterms ():
		return list (EcuDB.ecudb ["incoterms"].keys())

	def getDistrito (distrito, key):
		return EcuDB.ecudb ["distritos"][distrito][key]

	def getPaises ():
		return EcuDB.ecudb ["paises"]

	def getNumeroIdEmpresa (empresa):
		return EcuDB.ecudb ["empresas"][empresa]["numeroId"]

#----------------------------------------------------------
# Globals
#----------------------------------------------------------
win    = None	 # Global Ecuapass window  object

#----------------------------------------------------------
# Main function for testing
#----------------------------------------------------------
def mainBot (jsonFilepath):
	EcuBot.printx (">> External bot scrip")
	EcuBot.printx ("\t>>> Working dir: ", os.getcwd())
	EcuBot.printx ("\t>>> Input file : ", jsonFilepath)
	result = EcuBot.fillEcuapass (jsonFilepath)
	EcuBot.printx ("\t>>> Output result : ", result)
	return result

#--------------------------------------------------------------------
# EcuBot for filling Ecuapass cartaporte web form (in flash)
#--------------------------------------------------------------------
class EcuBot:
	#-- Main function for testing
	def fillEcuapass (jsonFilepath):
		py.sleep (1)
		EcuBot.printx (">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>><<")
		try:
			global win
			fields = Utils.readJsonFile (jsonFilepath)
			#py.sleep (1)
			win    = Utils.activateEcuapassWindow ()
			EcuBot.printx (">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>><<")
			#Utils.maximizeWindow (win)
			win.maximize ()
			#EcuBot.printx ("Scrolling up..")
			#Utils.scrollN (40, direction="up")
			#py.sleep (1)
			Utils.clearWebpageContent ()
			py.press ("Tab"); py.press ("Tab")
			Utils.checkCPITWebpage ()

			# Encabezado
			time.sleep (PAUSE)
			EcuBot.fillBoxSimpleIteration (fields, "01_Distrito"); py.press ("Tab")
			EcuBot.fillText (fields, "02_NumeroCPIC"); py.press ("Tab")
			EcuBot.fillText (fields, "03_MRN"); py.press ("Tab"); 
			EcuBot.fillText (fields, "04_MSN"); py.press ("Tab")
			EcuBot.fillBox (fields, "05_TipoProcedimiento"); py.press ("Tab")
			#EcuBot.fillTextSelection (fields, "06_EmpresaTransporte") # Selected by default
			py.press ("Tab")
			EcuBot.fillBox (fields, "07_DepositoMercancia"); py.press ("Tab")

			EcuBot.fillText (fields, "08_DirTransportista"); py.press ("Tab");
			EcuBot.fillText (fields, "09_NroIdentificacion"); py.press ("Tab")

			Utils.scrollN (5)

			# Remitente
			time.sleep (PAUSE)
			EcuBot.fillBox (fields, "10_PaisRemitente"); py.press ("Tab")
			EcuBot.fillBox (fields, "11_TipoIdRemitente") ; py.press ("Tab")
			EcuBot.fillText (fields, "12_NroIdRemitente"); py.press ("Tab")
			EcuBot.fillText (fields, "13_NroCertSanitario"); py.press ("Tab")
			EcuBot.fillBox (fields, "14_NombreRemitente"); py.press ("Tab")
			EcuBot.fillText (fields, "15_DireccionRemitente"); py.press ("Tab")


			# Destinatario
			time.sleep (PAUSE)
			EcuBot.fillTextSelection (fields, "16_PaisDestinatario"); py.press ("Tab")
			EcuBot.fillTextSelection (fields, "17_TipoIdDestinatario"); py.press ("Tab")
			EcuBot.fillText (fields, "18_NroIdDestinatario"); py.press ("Tab")
			py.press ("Tab")   # Skip Boton buscar
			EcuBot.fillTextSelection (fields, "19_NombreDestinatario"); py.press ("Tab")
			EcuBot.fillText (fields, "20_DireccionDestinatario"); py.press ("Tab")


			# Consignatario
			time.sleep (PAUSE)
			EcuBot.fillBox (fields, "21_PaisConsignatario"); py.press ("Tab")
			EcuBot.fillBox (fields, "22_TipoIdConsignatario"); py.press ("Tab")
			EcuBot.fillText (fields, "23_NroIdConsignatario"); py.press ("Tab")
			py.press ("Tab")    # Boton buscar consignatario por Id
			EcuBot.fillText (fields, "24_NombreConsignatario"); py.press ("Tab")
			EcuBot.fillText (fields, "25_DireccionConsignatario"); py.press ("Tab")

			Utils.scrollN (10)

			# Notificado
			time.sleep (PAUSE)
			EcuBot.fillText (fields, "26_NombreNotificado"); py.press ("Tab")
			EcuBot.fillText (fields, "27_DireccionNotificado"); py.press ("Tab")
			EcuBot.fillBox (fields, "28_PaisNotificado"); py.press ("Tab")

			# Paises: Recepcion, Embarque, Entrega
			#time.sleep (PAUSE)
			Utils.scrollN (10)
			EcuBot.fillBox (fields, "29_PaisRecepcion"); 
			py.press ("Tab"); py.press ("Tab"); py.press ("Tab")
			EcuBot.fillBox (fields, "32_PaisEmbarque"); 
			py.press ("Tab"); py.press ("Tab"); py.press ("Tab")
			EcuBot.fillBox (fields, "35_PaisEntrega"); 

			# Pais INCOTERM
			time.sleep (PAUSE)
			[py.press ("Tab") for i in range (13)]
			EcuBot.fillBox (fields, "48_PaisMercancia"); 

			# Pais Emision
			time.sleep (PAUSE)
			[py.press ("Tab") for i in range (14)]
			EcuBot.fillBox (fields, "62_PaisEmision"); 

			[py.hotkey ("shift", "Tab") for i in range (32)]

			# Fechas: Recepcion, Embarque, Entrega
			time.sleep (PAUSE)
			EcuBot.fillBox (fields, "30_CiudadRecepcion"); py.press ("Tab")
			EcuBot.fillFecha (fields, "31_FechaRecepcion"); 
			py.press ("Tab"); py.press ("Tab"); 

			EcuBot.fillBox (fields, "33_CiudadEmbarque"); py.press ("Tab")
			EcuBot.fillFecha (fields, "34_FechaEmbarque"); 
			py.press ("Tab"); py.press ("Tab"); 
			EcuBot.fillBox (fields, "36_CiudadEntrega"); py.press ("Tab")
			EcuBot.fillFecha (fields, "37_FechaEntrega"); py.press ("Tab") 

			Utils.scrollN (10)

			# Condiciones
			time.sleep (PAUSE)
			EcuBot.fillCondicionesTransporte (fields, "38_CondicionesTransporte"); py.press ("Tab")
			EcuBot.fillCondicionesPago (fields, "39_CondicionesPago"); py.press ("Tab")

			# Mercancia
			time.sleep (PAUSE)
			EcuBot.fillText (fields, "40_PesoNeto"); py.press ("Tab")
			EcuBot.fillText (fields, "41_PesoBruto"); py.press ("Tab")
			EcuBot.fillText (fields, "42_TotalBultos"); py.press ("Tab")
			EcuBot.fillText (fields, "43_Volumen"); py.press ("Tab")
			EcuBot.fillText (fields, "44_OtraUnidad"); py.press ("Tab")
			EcuBot.fillText (fields, "45_PrecioMercancias"); py.press ("Tab")

			# INCOTERM
			time.sleep (PAUSE)
			EcuBot.fillBox (fields, "46_INCOTERM"); py.press ("Tab")
			EcuBot.fillBox (fields, "47_TipoMoneda"); py.press ("Tab")
			py.press ("Tab")
			EcuBot.fillBox (fields, "49_CiudadMercancia"); py.press ("Tab")

			Utils.scrollN (5)

			# Gastos
			time.sleep (PAUSE)
			EcuBot.fillText (fields, "50_GastosRemitente"); py.press ("Tab")
			EcuBot.fillBox (fields, "51_MonedaRemitente"); py.press ("Tab")
			EcuBot.fillText (fields, "52_GastosDestinatario"); py.press ("Tab")
			EcuBot.fillBox (fields, "53_MonedaDestinatario"); py.press ("Tab")
			EcuBot.fillText (fields, "54_OtrosGastosRemitente"); py.press ("Tab")
			EcuBot.fillBox (fields, "55_OtrosMonedaRemitente"); py.press ("Tab")
			EcuBot.fillText (fields, "56_OtrosGastosDestinatario"); py.press ("Tab")
			EcuBot.fillBox (fields, "57_OtrosMonedaDestinataio"); py.press ("Tab")
			EcuBot.fillText (fields, "58_TotalRemitente"); py.press ("Tab")
			EcuBot.fillText (fields, "59_TotalDestinatario"); py.press ("Tab")

			Utils.scrollN (5)

			# Documentos
			EcuBot.fillText (fields, "60_DocsRemitente"); py.press ("Tab")

			# Emision
			EcuBot.fillFecha (fields, "61_FechaEmision"); py.press ("Tab")
			py.press ("Tab")
			EcuBot.fillBox (fields, "63_CiudadEmision"); py.press ("Tab")

			# Instrucciones
			EcuBot.fillText (fields, "64_Instrucciones"); py.press ("Tab")
			EcuBot.fillText (fields, "65_Observaciones"); py.press ("Tab")

			[py.press ("Tab") for i in range (3)]

			Utils.scrollN (10)
			# Detalles
			time.sleep (PAUSE)
			EcuBot.fillText (fields, "66_Secuencia"); py.press ("Tab")
			EcuBot.fillText (fields, "67_CantidadBultos"); py.press ("Tab")
			EcuBot.fillTipoEmbalaje (fields, "68_TipoEmbalaje"); py.press ("Tab")
			EcuBot.fillText (fields, "69_MarcasNumeros"); py.press ("Tab")
			EcuBot.fillText (fields, "70_PesoNeto"); py.press ("Tab")
			EcuBot.fillText (fields, "71_PesoBruto"); py.press ("Tab")
			EcuBot.fillText (fields, "72_Volumen"); py.press ("Tab")
			EcuBot.fillText (fields, "73_OtraUnidad"); py.press ("Tab")

			# IMOs
			time.sleep (PAUSE)
			EcuBot.fillText (fields, "74_Subpartida"); py.press ("Tab"); py.press ("Tab")
			EcuBot.fillBox (fields, "75_IMO1"); py.press ("Tab")
			EcuBot.fillBox (fields, "76_IMO2"); py.press ("Tab")
			EcuBot.fillBox (fields, "77_IMO2"); py.press ("Tab")
			EcuBot.fillText (fields, "78_NroCertSanitario"); py.press ("Tab")
			EcuBot.fillText (fields, "79_DescripcionCarga"); py.press ("Tab")
		except Exception as ex:
			EcuBot.printx (f"EXCEPCION: Problemas al llenar documento '{jsonFilepath}'")
			print (traceback_format_exc())
			return (str(ex))

		return (f"Ingresado exitosamente el documento {jsonFilepath}")

	#--------------------------------------------------------------------
	# Special fields
	#--------------------------------------------------------------------
	#-- Fill '68 Tipo Embalaje' combo box
	def fillTipoEmbalaje (fields, fieldName):
		value = fields [fieldName].upper()
		if value.upper() in ["ESTIBA", "PALLETS"]:
			value = "PALLETES"

		fields [fieldName] = value
		EcuBot.fillBox (fields, fieldName)


	#-- Fill '38 Condiciones Transporte' combo box
	def fillCondicionesTransporte (fields, fieldName):
		value = fields [fieldName].upper()
		if "DIRECTO" in value and "SIN" in value:
			text = "DIRECTO, SIN CAMBIO DEL CAMION"
		elif "DIRECTO" in value and "CON" in value:
			text = "DIRECTO, CON CAMBIO DEL TRACTO-CAMION"
		elif "TRANSBORDO" in value:
			text = "TRANSBORDO"

		fields [fieldName] = text
		EcuBot.fillBox (fields, fieldName)
		
	#-- 39_CondicionesPago
	def fillCondicionesPago (fields, fieldName):
		value = fields [fieldName].upper()
		if "CREDITO" in value: 
			text = "POR COBRAR"
		else: 
			text = value
			#text = "--Selección--"

		fields [fieldName] = text
		EcuBot.fillBox (fields, fieldName)

	#--------------------------------------------------------------------
	# Filling doc fields
	#--------------------------------------------------------------------
	#-- Fill combo box pasting text and selecting first value.
	#-- Without check. Default value, if not found.
	def fillBox (fields, fieldName):
		#py.pause = 0.01
		value = fields [fieldName]
		EcuBot.printx (f"Llenando CBox '{fieldName}' : {fields [fieldName]}'...")
		if value == None:
			return
		# Copy field text
		fieldText = value.upper()
		pyperclip_copy (fieldText)
		py.hotkey ("ctrl", "v")
		py.press ("down")

		# Check if selection is null
		py.hotkey ("ctrl", "c")
		if pyperclip_paste () == fieldText:
			EcuBot.printx (f"No se encontró la opción '{fieldText}' en el campo '{fieldName}'")
			py.press ("--")
		else:
			pyperclip_copy (fieldText)
			py.hotkey ("ctrl", "v")

		py.press ("down")
		py.press ("enter")

	#-- Fill box iterating, copying, comparing.
	def fillBoxSimpleIteration (fields, fieldName):
		fieldText = fields [fieldName].upper()
		EcuBot.printx (f"> >> Llenando simple CBox '{fieldName} : {fieldText}'...")

		lastText = "XXXYYYZZZ"
		while True:
			py.hotkey ("ctrl", "a");py.hotkey ("ctrl","c"); 
			text = pyperclip_paste().upper()
			if fieldText in text:
				EcuBot.printx (f"\t\t Encontrado {fieldText} en {text}") 
				py.press ("enter"); 
				break

			if (text == lastText):
				EcuBot.printx (f"\t\t No se pudo encontrar '{fieldText}'!")
				break

			py.press ("down");
			lastText = text 

	#-- fill text field with selection
	def fillTextSelection (fields, fieldName, imageName=None):
		EcuBot.fillText (fields, fieldName, imageName)
		py.press ("Enter")


	#-- fill text field
	def fillText (fields, fieldName, imageName=None):
		value = fields [fieldName]
		EcuBot.printx (f"Llenando TextField '{fieldName}' : '{value}'...")
		if value == None:
			return

		pyperclip_copy (value)
		if imageName == None:
			#py.write (value)
			py.hotkey ("ctrl", "v")


	#-- fill combo box iterating over all values (Ctrl+x+v+a+back)
	def fillCBoxFieldByIterating (fields, fieldName):
		#py.pause = 0.05
		fieldText = fields [fieldName].lower()
		EcuBot.printx (f"> >> Llenando CBox iterando uno a uno '{fieldName} : {fieldText}'...")

		py.hotkey ("ctrl","c"); py.hotkey ("ctrl","v"); py.hotkey ("ctrl","a");
		py.press ("backspace");
		py.press ("down");

		lastText = "XXXYYYZZZ"
		while True:
			py.hotkey ("ctrl","c"); py.hotkey ("ctrl","v")
			text = pyperclip_paste().lower()
			value = Utils.strCompare (fieldText, text) 
			EcuBot.printx (f"\t\t Comparando texto campo '{fieldText}' con texto CBox '{text}', valor: {value}")
			#if value > 0.8:
			if fieldText in text:
				EcuBot.printx (f"\t\t Encontrado!") 
				py.press ("enter"); py.press ("enter")
				break

			if (text == lastText):
				EcuBot.printx (f"\t\tERROR: No se pudo encontrar '{fieldText}'!")
				break

			py.hotkey ("ctrl","a"); py.press ("backspace"); py.press ("down");
			lastText = text 


	#-- Fill Date box widget (month, year, day)
	def fillFecha (fields, fieldName):
		EcuBot.printx (f"Llenando fecha '{fieldName}' : {fields [fieldName]}'...")
		fechaText = fields [fieldName]
		if (fechaText == None):
			return

		items = fechaText.split("-")
		day, month, year = int (items[0]), int (items[1]), int (items[2])

		boxDate    = EcuBot.getBoxDate ()
		dayBox	   = boxDate [0]
		monthBox   = boxDate [1]
		yearBox    = boxDate [2]

		py.hotkey ("ctrl", "down")
		EcuBot.setYear  (year, yearBox)
		EcuBot.setMonth (month, monthBox)
		EcuBot.setDay (day)

	#-- Get current date fron date box widget
	def getBoxDate ():
		py.hotkey ("ctrl", "down")
		py.press ("home")
		py.hotkey ("ctrl", "a")
		py.hotkey ("ctrl", "c")
		text	 = pyperclip_paste ()
		boxDate  = text.split ("/") 
		boxDate  = [int (x) for x in boxDate]
		return (boxDate)

	#-- Set year
	def setYear (yearDoc, yearOCR):
		diff = yearDoc - yearOCR
		pageKey = "pageup" if diff < 0 else "pagedown"
		EcuBot.printx (f"Localizando año. Doc: {yearDoc}. OCR: {yearOCR}. Diff: {diff}...")

		for i in range (abs(diff)):
			EcuBot.printx (f"Año %.2d: " % (i+1), end="")
			for k in range (12):
				EcuBot.printx (f">%.2d " % (k+1), end="")
				py.press (pageKey)
			EcuBot.printx ("")
		EcuBot.printx ("")

	#-- Set month
	def setMonth (monthDoc, monthOCR):											 
		diff = monthDoc - monthOCR
		pageKey = "pageup" if diff < 0 else "pagedown"
		EcuBot.printx (f"Localizando mes. Doc: {monthDoc}. OCR: {monthOCR}. Diff: {diff}...")

		for i in range (abs(diff)):
			EcuBot.printx (f"> %.2d " % (i+1), end="")
			py.press (pageKey)

	#-- Set day
	def setDay (dayDoc):
		try:
			nWeeks = dayDoc // 7
			nDays  = dayDoc % 7 - 1
			EcuBot.printx (f"Localizando dia {dayDoc}. Semanas: {nWeeks}, Dias: {nDays}...")

			py.press ("home")
			[py.press ("down") for i in range (nWeeks)]
			[py.press ("right") for i in range (nDays)]

			py.press ("enter")
		except:
			EcuBot.printx (f"EXCEPTION: Al buscar el dia '{dayDoc}'")
			raise

	def printx (*args, flush=True, end="\n"):
		print ("BOT:", *args, flush=flush, end=end)

#--------------------------------------------------------------------
# Utility function used in EcuBot class
#--------------------------------------------------------------------
class Utils:
	message = ""   # Message sent by 'checkError' function

	#-- Get path imagefile when running python or executable
	def imagePath (imageFilename):
		path = None
		try:
			path = os.path.join (os.environ ["PYECUAPASS"], "ecusrv", "images", imageFilename)
		except:
			path = os.path.join ("images", imageFilename)
		return path

	#-- Read JSON file
	def readJsonFile (jsonFilepath):
		EcuBot.printx (f"Leyendo archivo de datos JSON '{jsonFilepath}'...")
		data = json.load (open (jsonFilepath))
		return (data)

	#-- Detect and activate ECUAPASS window
	def activateEcuapassWindow ():
		EcuBot.printx ("Detectando ventana del ECUAPASS...")
		windows = py.getAllWindows ()
		ecuWin = None
		for win in windows:
			if win.title == 'ECUAPASS - SENAE browser':
				ecuWin = win
				break
		if Utils.checkError (ecuWin, "ERROR: No se detectó ventana del ECUAPASS"):
			return Utils.message

		EcuBot.printx ("Activando ventana del ECUAPASS...")
		ecuWin.activate ()
		return (ecuWin)

	#-- Maximize window clicking on 'maximize' buttone
	def maximizeWindow (win):
		if win.isMaximized:
			EcuBot.printx ("Ventana ya está maximizada...")
			return

		EcuBot.printx ("Maximixando la ventana...")
		EcuBot.printx ("\tWin info:", Utils.getWinInfo (win))
		win.moveTo (0,0)

		xy = py.locateCenterOnScreen (Utils.imagePath ("image-windows-WindowButtons.png"),
					confidence=0.8, grayscale=True, 
					region=(win.left, win.top, win.width, win.height))
		if Utils.checkError (xy, "ERROR:No se localizó botón de maximizar la ventana"):
			return Utils.message

		py.click (xy[0], xy[1])

		w, h = py.size ()
		win.left = win.top = 0
		win.width = w

	#-- Clear previous webpage content
	def clearWebpageContent ():
		EcuBot.printx ("Localizando botón de borrado...")
		xy = py.locateCenterOnScreen (Utils.imagePath ("image-field-ClearButton.png"), 
				confidence=0.8, grayscale=True)
		if Utils.checkError (xy, "No se detectó botón de borrado"):
			return Utils.message

		py.click (xy[0], xy[1], interval=1)    

		return xy

	#-- Check if active webpage is the true working webpage
	def checkCPITWebpage ():
		EcuBot.printx ("Verificando página de Cartaportes activa...")
		title = Utils.getBox (Utils.imagePath ("image-text-CartaporteCarretera.png"), 
				confidence=0.8, grayscale=True)
		if Utils.checkError (title, "ERROR: No se detectó página de Cartaportes"):
			return Utils.message

	#-- Scroll down/up N times (30 pixels each scroll)
	def scrollN (N, direction="down"):
		sizeScroll = -10000 if direction=="down" else 10000
		#EcuBot.printx (f"\tScrolling {sizeScroll} by {N} times...")
		for i in range (N):
			#EcuBot.printx (f"\t\tScrolling {i} : {30*i}")
			py.scroll (sizeScroll)

	#-- Center field in window by scrolling down
	def centerField (imageName):
		EcuBot.printx ("\tCentering field...")
		xy = Utils.getBox (imageName, grayscale=True)
		EcuBot.printx ("XY: ", xy)
		if Utils.checkError (xy, f"ERROR: campo no localizado"):
			return Utils.message

		while xy.top > 0.7 * win.height:
			EcuBot.printx ("\t\tScrolling down:", xy)
			Utils.scrollN (2)
			xy = Utils.getBox (imageName, confidence=0.8, grayscale=True)

	#-- Check if 'resultado' has values or is None
	def checkError (resultado, message):
		if resultado == None:
			Utils.message = f"ERROR: '{message}'"
			raise Exception (message)
		return False

	#-- Get information from window
	def getWinInfo (win):
		info = "Left: %s, Top: %s, Width: %s, Height: %s" % (
				win.left, win.top, win.width, win.height)
		return (info)

	#-- Redefinition of 'locateOnScreen' with error checking
	def getBox (imgName, region=None, confidence=0.7, grayscale=True):
		try:
			box = py.locateOnScreen (imgName, region=region,
				confidence=confidence, grayscale=grayscale)
			return (box)
		except Exception as ex:
			EcuBot.printx (f"EXCEPTION: Función 'getBox' falló. ImgName: '{imgName}'. Region: '{region}'.")
			raise 

	def printx (*args, flush=True):
		print ("UTILS:", *args, flush=flush)

#--------------------------------------------------------------------
# Call main 
#--------------------------------------------------------------------
if __name__ == '__main__':
	jsonFilepath = sys.argv [1]
	mainBot (jsonFilepath)
