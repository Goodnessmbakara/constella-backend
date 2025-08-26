import datetime
import json
import requests
from typing import List, Dict
from db.weaviate.operations.general import insert_record, query_by_filter, update_record_metadata, do_milvus_querying
from db.milvus.operations import general as milvus_general
from weaviate.classes.query import Filter
from db.weaviate.records.tag import WeaviateTag
import time
from ai.embeddings import create_embedding
from db.weaviate.records.note import WeaviateNote
import traceback
from utils.json import clean_tag_weaviate_record, clean_weaviate_record
from sentry_sdk import capture_exception


def check_if_author_exists(tenant_name: str, author_name: str):
	try:
		if do_milvus_querying:
			filter_expr = milvus_general.convert_to_milvus_filter({
				"title": author_name,
				"recordType": "note"
			})
			results = milvus_general.query_by_filter(
				tenant_name=tenant_name,
				filter_expr=filter_expr,
				top_k=1
			).get('results', [])
		else:
			results = query_by_filter(
				tenant_name=tenant_name,
				filter=Filter.by_property("title").equal(author_name) & Filter.by_property("recordType").equal("note"),
				top_k=1
			).get('results', [])
		if len(results) > 0:
			return clean_weaviate_record(results[0])
		else:
			return None
	except Exception as e:
		capture_exception(e)
		return None

def check_if_document_exists(tenant_name: str, document_name: str):
	try:
		if do_milvus_querying:
			filter_expr = milvus_general.convert_to_milvus_filter({
				"title": document_name,
				"recordType": "note"
			})
			results = milvus_general.query_by_filter(
				tenant_name=tenant_name,
				filter_expr=filter_expr,
				top_k=1
			).get('results', [])
		else:
			results = query_by_filter(
				tenant_name=tenant_name, 
				filter=Filter.by_property("title").equal(document_name) & Filter.by_property("recordType").equal("note"),
				top_k=1
			).get('results', [])
		if len(results) > 0:
			return clean_weaviate_record(results[0])
		else:
			return None
	except Exception as e:
		capture_exception(e)
		return None

def check_if_tag_exists(tenant_name: str, tag_name: str):
	try:
		if do_milvus_querying:
			filter_expr = milvus_general.convert_to_milvus_filter({
				"name": tag_name,
				"recordType": "tag"
			})
			results = milvus_general.query_by_filter(
				tenant_name=tenant_name,
				filter_expr=filter_expr,
				top_k=1
			).get('results', [])
		else:
			results = query_by_filter(
				tenant_name=tenant_name, 
				filter=Filter.by_property("name").equal(tag_name) & Filter.by_property("recordType").equal("tag"),
				top_k=1
			).get('results', [])
		if len(results) > 0:
			return clean_tag_weaviate_record(results[0])
		else:
			return None
	except Exception as e:
		capture_exception(e)
		return None
	
def create_new_tag(tenant_name: str, tag_name: str):
	"""
	Creates a new tag object in Weaviate and returns it with its uniqueid
	"""
	tag_record = {
		"title": tag_name,
		"name": tag_name,
		"color": "#0065FF", # TODO: make a readwise tag color
		"content": "",
		"recordType": "tag",
		"created": int(datetime.datetime.utcnow().timestamp() * 1000),
		"lastModified": int(datetime.datetime.utcnow().timestamp() * 1000),
	}
	uniqueid = insert_record(tenant_name, WeaviateTag.from_rxdb(tag_record))
	tag_record['uniqueid'] = uniqueid
	return tag_record

def parse_full_data(tenant_name: str, full_data: List[Dict]):
	"""
	Uses the current UTC time for created time instead of the actual ones for syncing reasons.
	For initial, could use the current time of the user so that it fetches the data and then use the created of the Readwise provided 
	Note: 'readwise' tag is added to all inserted records
	:return: list of all newly created tags, authors, and documents (NOTE: old ones will not be returned)
	"""
	all_tags = {} # map of tag name: tag data

	try:
		# Add the readwise tag to all tags
		readwise_tag = check_if_tag_exists(tenant_name, 'readwise')
		if not readwise_tag:
			readwise_tag = create_new_tag(tenant_name, 'readwise')
		all_tags['readwise'] = readwise_tag
	except Exception as e:
		traceback.print_exc()
		capture_exception(e)
		print("Error creating readwise tag: " + str(e))
		raise e
		
	results = []

	# Process all tags first
	for document in full_data:
		try:
			# Add category and source as tags
			document_book_tags = document.get('book_tags', [])
			document_book_tag_names = []
			try:
				for tag in document_book_tags:
					if tag.get('name'):
						document_book_tag_names.append(tag.get('name'))
			except Exception as e:
				print("Error getting document book tags: " + str(e))
				capture_exception(e)

			all_document_tags = document_book_tag_names + [document['category'], document['source'], 'readwise']

			try:
				for tag_name in all_document_tags:
					if tag_name not in all_tags:
						existing_tag = check_if_tag_exists(tenant_name, tag_name)
						if existing_tag:
							all_tags[tag_name] = existing_tag
						else:
							# Create new tag
							tag_record = create_new_tag(tenant_name, tag_name)
							all_tags[tag_name] = tag_record
							results.append(tag_record)
			except Exception as e:
				traceback.print_exc()
				capture_exception(e)

			# Check/create author
			author = document.get('author')
			author_did_not_exist = False
			author_record = None
			if author:
				try:
					author_record = check_if_author_exists(tenant_name, author)
					if not author_record:
						author_record = {
							"title": author,
							"content": "",
							"recordType": "note",
							"created": int(datetime.datetime.utcnow().timestamp() * 1000),
							"lastModified": int(datetime.datetime.utcnow().timestamp() * 1000),
							"vector": create_embedding(author),
							"tags": [all_tags['readwise']] if 'readwise' in all_tags else [],
							"incomingConnections": [],
							"outgoingConnections": []
						}
						uniqueid = insert_record(tenant_name, WeaviateNote.from_rxdb(author_record))
						author_record['uniqueid'] = uniqueid
						author_did_not_exist = True
						# delete vector before adding
						del author_record['vector']
						results.append(author_record)
				except Exception as e:
					print("Error creating author: " + str(e))
					capture_exception(e)
					traceback.print_exc()

			# Check/create document
			doc_title = document.get('readable_title')
			# Use title if readable_title is not provided
			if not doc_title:
				doc_title = document.get('title')

			doc_record = None
			doc_did_not_exist = False
			if doc_title:
				try:
					doc_record = check_if_document_exists(tenant_name, doc_title)
					if not doc_record:
						doc_content = f"{document.get('document_note', '')} {document.get('summary', '')}"
						doc_tags = [all_tags[tag] for tag in all_document_tags if tag in all_tags]
						doc_did_not_exist = True

						doc_record = {
							"title": doc_title,
							"content": doc_content,
							"recordType": "note",
							"created": int(datetime.datetime.utcnow().timestamp() * 1000),
							"lastModified": int(datetime.datetime.utcnow().timestamp() * 1000),
							"tags": doc_tags,
							"vector": create_embedding(f"{doc_title} {doc_content}"),
							"incomingConnections": [author_record['uniqueid']] if author_record and 'uniqueid' in author_record else [],
							"outgoingConnections": []
						}
						uniqueid = insert_record(tenant_name, WeaviateNote.from_rxdb(doc_record))
						doc_record['uniqueid'] = uniqueid
						# will add to results after adding outgoing connections to highlights
				except Exception as e:
					print("Error creating document: " + str(e))
					capture_exception(e)
					# Try deleting tags and trying again
					try:
						doc_record['tags'] = []
						uniqueid = insert_record(tenant_name, WeaviateNote.from_rxdb(doc_record))
						doc_record['uniqueid'] = uniqueid
						results.append(doc_record)
					except Exception as e:
						capture_exception(e)
						traceback.print_exc()

			# Update author's outgoing connections to include this document
			# Only need to this when the document is first created to its author
			try:
				if doc_did_not_exist and author_record and 'uniqueid' in author_record and 'uniqueid' in doc_record:
					existing_connections = author_record.get('outgoingConnections', [])
					
					# if not of type list, convert to list
					if not isinstance(existing_connections, list):
						existing_connections = []
					new_connections = existing_connections + [doc_record['uniqueid']]
					update_record_metadata(tenant_name, author_record['uniqueid'], {"outgoingConnections": new_connections})

					# Update the author record in memory
					author_record['outgoingConnections'] = new_connections
					
					# Update the author record in results if it exists there
					if author_did_not_exist:  # we know it's in results if it's new
						for i, record in enumerate(results):
							if record.get('uniqueid') == author_record['uniqueid']:
								results[i] = author_record
								break
					else:
							# Add to results since now the author is updated
							results.append(author_record)
			except Exception as e:
				traceback.print_exc()
				capture_exception(e)
				print("Error updating author's outgoing connections: " + str(e))

			highlight_uniqueids = []

			# Process highlights
			for highlight in document.get('highlights', []):
				try:
					# Skip deleted highlights
					if highlight.get('is_deleted', False):
						continue
					
					highlight_tag_names = []
					try:
						for tag in highlight.get('tags', []):
							if tag.get('name'):
								highlight_tag_names.append(tag.get('name'))
					except Exception as e:
						print("Error getting highlight tags: " + str(e))
						# capture sentry exception
						capture_exception(e)

					try:
						# Check/create highlight tags
						for tag_name in highlight_tag_names:
							if tag_name not in all_tags:
								existing_tag = check_if_tag_exists(tenant_name, tag_name)
								if existing_tag:
									all_tags[tag_name] = existing_tag
								else:
									tag_record = create_new_tag(tenant_name, tag_name)	
									all_tags[tag_name] = tag_record
									results.append(tag_record)
					except Exception as e:
						print("Error creating highlight tags: " + str(e))
						capture_exception(e)
						traceback.print_exc()

					# Convert highlighted_at to timestamp in milliseconds
					highlighted_at = highlight.get('highlighted_at')
					if highlighted_at:
						try:
							# Try parsing with microseconds format first
							try:
								dt = datetime.datetime.strptime(highlighted_at, "%Y-%m-%dT%H:%M:%S.%fZ")
							except Exception:
								# If that fails, try without microseconds
								dt = datetime.datetime.strptime(highlighted_at, "%Y-%m-%dT%H:%M:%SZ")
							highlighted_at_ms = int(dt.timestamp() * 1000)
						except Exception as e:
							print(f"Error parsing highlighted_at date: {e}")
							highlighted_at_ms = int(datetime.datetime.utcnow().timestamp() * 1000)
					else:
						highlighted_at_ms = int(datetime.datetime.utcnow().timestamp() * 1000)

					# Create highlight record
					highlight_tags = [all_tags[tag] for tag in highlight_tag_names if tag in all_tags]
					highlight_record = {
						"title": highlight.get('text', ''),
						"content": highlight.get('note', ''),
						"recordType": "note",
						"created": highlighted_at_ms,
						"lastModified": highlighted_at_ms,
						"tags": highlight_tags,
						"vector": create_embedding(f"{highlight.get('text', '')}"),
						"incomingConnections": [doc_record['uniqueid']] if doc_record and 'uniqueid' in doc_record else []
					}
					uniqueid = insert_record(tenant_name, WeaviateNote.from_rxdb(highlight_record))
					highlight_record['uniqueid'] = uniqueid
					# delete vector before adding
					del highlight_record['vector']
					results.append(highlight_record)
					highlight_uniqueids.append(uniqueid)
				except Exception as e:
					traceback.print_exc()
					capture_exception(e)
					print("Error creating highlight: " + str(e))


			# Update document's outgoing connections to include highlights
			if doc_record and 'uniqueid' in doc_record:
				try:
					# Get existing outgoing connections or initialize empty list
					existing_connections = doc_record.get('outgoingConnections', [])

					# if not of type list, convert to list
					if not isinstance(existing_connections, list):
						existing_connections = []

					# Combine existing connections with new highlight connections
					all_connections = existing_connections + highlight_uniqueids
					# Update in database
					update_record_metadata(tenant_name, doc_record['uniqueid'], {"outgoingConnections": all_connections})
					# Update the document record in memory
					doc_record['outgoingConnections'] = all_connections
					if 'vector' in doc_record:
						# delete vector before adding
						del doc_record['vector']
					results.append(doc_record)
				except Exception as e:
					traceback.print_exc()
					capture_exception(e)
					print("Error updating document's outgoing connections: " + str(e))
		except Exception as e:
			traceback.print_exc()
			capture_exception(e)

	return results



def fetch_from_export_api(tenant_name: str, token: str, updated_after=None):
	"""
	If no updated_after is provided, it will fetch all data from Readwise.
	Otherwise, it will fetch all data updated after the provided date.
	"""
	full_data = []
	next_page_cursor = None
	
	while True:
		params = {}
		if next_page_cursor:
			params['pageCursor'] = next_page_cursor
		if updated_after:
			params['updatedAfter'] = updated_after
			
		response = requests.get(
			url="https://readwise.io/api/v2/export/",
			params=params,
			headers={"Authorization": f"Token {token}"}, verify=False
		)
		json_response = response.json()
		if 'detail' in json_response and not 'results' in json_response:
			raise Exception(json_response['detail'])

		full_data.extend(json_response['results'])
		next_page_cursor = json_response.get('nextPageCursor')
		if not next_page_cursor:
			break
	return parse_full_data(tenant_name, full_data)