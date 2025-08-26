from bson import json_util
import json

potential_date_fields = [
  'datetime',
  'lastUsed',
]

def parse_json(data):
  """
  helper function to parse json data
  converts ObjectId to string
  converts date fields to string
  """
  if not data:
    return None
  res = json.loads(json_util.dumps(data))
  res['_id'] = res['_id']['$oid']

  # Convert all potential date fields to string
  for field in res:
    # check if res[field] is of type object
    if isinstance(res[field], dict):
      if '$date' in res[field]:
        res[field] = res[field]['$date']

  return res


def clean_weaviate_record(record):
	"""
	Cleans a returned Weaviate record (such as those retrieved in readwise.py)
	1. Deletes vector
	2. Converts uuid to string wherever they could be
	"""
	try:
		# delete vector before adding
		del record['vector']

		record['uniqueid'] = str(record['uniqueid'])

		if 'outgoingConnections' in record and record['outgoingConnections']:
			record['outgoingConnections'] = [str(connection) for connection in record['outgoingConnections']]
		if 'incomingConnections' in record and record['incomingConnections']:
			record['incomingConnections'] = [str(connection) for connection in record['incomingConnections']]

		if 'tags' in record:
			for tag in record['tags']:
				if 'uniqueid' in tag:
					tag['uniqueid'] = str(tag['uniqueid'])

		if 'tagIds' in record and record['tagIds'] and isinstance(record['tagIds'], list):
			record['tagIds'] = [str(tag) for tag in record['tagIds']]

		if 'tagIds' in record and not record['tagIds']:
			record['tagIds'] = []

		if 'content' in record and not record['content']:
			record['content'] = ""

		if 'foreignId' in record:
			record['foreignId'] = str(record['foreignId'])

		if 'startId' in record:
			record['startId'] = str(record['startId'])

		if 'endId' in record:
			record['endId'] = str(record['endId'])

		if 'miscData' in record:
			record['miscData'] = str(record['miscData'])

		if 'startData' in record:
			record['startData'] = str(record['startData'])

		if 'endData' in record:
			record['endData'] = str(record['endData'])

		if 'type' in record:
			record['type'] = str(record['type'])

		# if incomingConnections is not of type list, convert to list
		if 'incomingConnections' in record and not isinstance(record['incomingConnections'], list):
			record['incomingConnections'] = []
		# if outgoingConnections is not of type list, convert to list
		if 'outgoingConnections' in record and not isinstance(record['outgoingConnections'], list):
			record['outgoingConnections'] = []

		# Set any null/None values to empty string
		for key in record:
			if record[key] is None or record[key] == "null" or record[key] == "nil" or record[key] == "<nil>" or not record[key]:
				record[key] = ""

		return record
	except:
		return record

def clean_tag_weaviate_record(record):
	"""
	Deletes everything except for uniqueid, name, color
	"""
	try:
		return {
			"uniqueid": record['uniqueid'],
			"name": record['name'],
			"color": record['color']
		}
	except:
		return clean_weaviate_record(record)
