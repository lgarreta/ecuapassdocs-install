#!/usr/bin/env python3

import os, sys, json, re
import traceback

from pickle import load as pickle_load
from pickle import dump as pickle_dump
import azure.core.credentials 
from azure.ai.formrecognizer import DocumentAnalysisClient

APP_HOME_DIR = os.environ ["PYECUAPASS"]
APP_KEYS_FILE = os.path.join (APP_HOME_DIR, "keys", "azure-keys-cognitive-resource.json")

#----------------------------------------------------------
# Run Azure analysis for custom "cartaporte" document
#----------------------------------------------------------
def mainDoc (inputFilepath):
	try:
		filename	  = os.path.basename (inputFilepath)

		print (">>> Input File	  : ", inputFilepath)
		print (">>> Current Dir   : ", os.getcwd())

		# Document analysis using Azure cloud
		docJsonFile  = EcuMain.processDocument (inputFilepath)
		mainFields	 = EcuInfo.getMainFields (docJsonFile)

		EcuMain.saveFields (mainFields, filename, "RESULTS")
	except Exception as ex:
		print ("ERROR procesando documentos:", ex) 
		return (f"ERROR procesando documento '{inputFilepath}'")

	return (f"{inputFilepath} successfuly processed")

#-----------------------------------------------------------
# Cloud analysis
#-----------------------------------------------------------
class EcuMain:
	#-- Run cloud analysis
	def processDocument (inputFilepath):
		print ("\n>>>", EcuCloud.getCloudName(), "document processing...")
		docJsonFile = None
		try:
			filename = os.path.basename (inputFilepath)
			docJsonFile = EcuMain.loadPreviousDocument (filename)
			if (docJsonFile is None):
				docJsonFile = EcuCloud.analyzeDocument (inputFilepath)
		except Exception as ex:
			print (f"ERROR procesando documento '{inputFilepath}'") 
			raise
		return docJsonFile

	#-- Load previous result.
	def loadPreviousDocument (filename):
		try:
			docJsonFile = None
			#filename = os.path.basename (filename)
			pickleFilename = f"{filename.split ('.')[0]}-{EcuCloud.getCloudName()}-CACHE.pkl"
			print ("\t>>> Looking for previous file: ", pickleFilename)
			if os.path.isfile (pickleFilename): 
				print ("\t>>> Loading previous result from pickle file:", pickleFilename )
				with open (pickleFilename, 'rb') as inFile:
					result = pickle_load (inFile)
				docJsonFile = EcuCloud.saveResults (result, filename)
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
class EcuCloud:
	AzureKeyCredential = azure.core.credentials.AzureKeyCredential

	#-- Online processing request return the first document 
	def analyzeDocument (docFilepath):
		docJsonFile = None
		try:

			print ("\t>>>", "Analyzing document...")
			credentialsDict  = EcuCloud.initCredentials ()
			lgEndpoint		 = credentialsDict ["endpoint"]
			lgKey			 = credentialsDict ["key"]	
			lgLocale		 = credentialsDict ["locale"]
			lgModel			 = credentialsDict ["modelId"]

			lgCredential = EcuCloud.AzureKeyCredential (lgKey)
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
			docJsonFile = EcuCloud.saveResults (result, docFilename)
		except Exception as ex:
			print ("EXCEPCION analizando documento." )
			print (traceback.format_exc())
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
			print (traceback.format_exc())
			sys.exit (1)

		return (credentialsDict)

	#-- Save request result as pickle and json files
	def saveResults (result, docFilepath):
		rootName = docFilepath.split ('.')[0]

		print (f"\t>>> Guardando resultados de Azure en %s-XXX.yyy" % rootName)

		# Save results as Pickle 
		outPickleFile = f"{rootName}-{EcuCloud.getCloudName()}-CACHE" ".pkl"
		with open(outPickleFile, 'wb') as outFile:
			pickle_dump (result, outFile)

		# Save results as JSON file
		resultDict		= result.to_dict ()
		outJsonFile = f"{rootName}-{EcuCloud.getCloudName()}-CACHE" ".json"
		with open (outJsonFile, 'w') as outFile:
			json.dump (resultDict, outFile, indent=4, default=str)

		# Save result document as JSON file
		document	 = result.documents [0]
		documentDict = document.to_dict ()
		outJsonFile = f"{rootName}-DOCUMENT-NONEWLINES" ".json"
		with open (outJsonFile, 'w') as outFile:
			json.dump (documentDict, outFile, indent=4, default=str)

		# Save document with original (newlines) content
		documentDictNewlines = EcuCloud.getDocumentWithNewlines (resultDict)
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
# Class that fill Ecuapass document from extracted data
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

#--------------------------------------------------------------------
# Call main 
#--------------------------------------------------------------------
if __name__ == '__main__':
	inputFilepath = sys.argv [1]
	mainDoc (inputFilepath)
