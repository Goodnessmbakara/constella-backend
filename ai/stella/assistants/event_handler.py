"""
The event handler from the Stella Assistants API.
"""
'''
(C) 2024 Jean-Luc Vanhulst - Valor Ventures 
MIT License

An async assistant class that can be used to interact with the OpenAI Assistant API.

The most basic call is 

result = await assistant.generate(assistant_name=assistant_name, content=data.content)
where assistant_name is the name of the assistant to use and content is the prompt to use.
this will return json with the response, status_code and thread_id

you can also use the assistant_id instead of the assistant_name if you have it.

result = await assistant.generate(assistant_id=assistant_id, content=data.content)

optional parameters are:
    files: list of file_id's to be used by the assistant (the need to be uploaded first)
            Any file that is an image will automatically added to the message to be used for vision
            if the file is 'c', 'cs', 'cpp', 'doc', 'docx', 'html', 'java', 'json', 'md', 'pdf', 'php',
            'pptx', 'py', 'rb', 'tex', 'txt', 'css', 'js', 'sh', 'ts' it will available for retrieval.
            (summarize, extra etc)
            
    when_done: a function to be called when the assistant is done. this function will receive the thread_id as an argument and can be used to get the full response.
               and do things like send an email or store the results.
    If when_done is not provided the function will (await) the result of the assistant call and return the result.
    if when_done is provided the function will return immediately with a "queued" response that includes the thread_id (only)
    this one is useful for api type calls where you want to offload the processing to a background job
    
'''
import asyncio
import json
from openai.types.beta import Assistant, Thread
from openai.types.beta.threads.run import Run
from openai.types.beta.assistant_stream_event import (
    ThreadRunRequiresAction,
    ThreadMessageDelta,
    ThreadRunFailed,
    ThreadRunCancelling,
    ThreadRunCancelled,
    ThreadRunExpired,
    ThreadRunStepFailed,
    ThreadRunStepCancelled,
)
import types
from typing import Optional
import logging
from functools import partial
from pydantic import BaseModel, computed_field
import importlib
from ai.openai_setup import async_openai_client

logger = logging.getLogger(__name__)


def analyze_run_failure(event_type: str, error_details: dict) -> dict:
	"""
	Analyze the run failure and provide actionable suggestions.
	
	Returns a dict with 'reason' and 'suggestion' keys.
	"""
	suggestions = {
		"ThreadRunExpired": {
			"reason": "The assistant run took too long and expired",
			"suggestion": "Try breaking down your request into smaller parts or simplifying the task"
		},
		"ThreadRunFailed": {
			"reason": "The assistant encountered an error during execution",
			"suggestion": "Check if all required tools are properly configured and the request is valid"
		},
		"ThreadRunCancelled": {
			"reason": "The run was cancelled",
			"suggestion": "The operation was cancelled, you can try again"
		},
		"ThreadRunStepFailed": {
			"reason": "A specific step in the assistant's process failed",
			"suggestion": "There might be an issue with one of the tools or the data being processed"
		}
	}
	
	# Check for specific error codes
	if "last_error" in error_details and error_details["last_error"]:
		error_code = error_details["last_error"].get("code")
		error_message = error_details["last_error"].get("message", "")
		
		if error_code == "rate_limit_exceeded":
			return {
				"reason": "Rate limit exceeded",
				"suggestion": "Too many requests. Please wait a moment before trying again"
			}
		elif error_code == "server_error":
			return {
				"reason": "OpenAI server error",
				"suggestion": "OpenAI is experiencing issues. Please try again in a few moments"
			}
		elif "token" in error_message.lower() or "context" in error_message.lower():
			return {
				"reason": "Context length exceeded",
				"suggestion": "The conversation or request is too long. Try starting a new conversation or shortening your request"
			}
	
	# Return default suggestion based on event type
	return suggestions.get(event_type, {
		"reason": f"Assistant run failed with {event_type}",
		"suggestion": "Please try again or contact support if the issue persists"
	})


async def run_tasks_sequentially(*tasks):
    """
    A helper function that runs async tasks in sequence. 
    be sure to pass partial functions if you need to pass arguments!
    """
    for task in tasks:
        await task()

async def stream_generator(data):
    """
    Generator function to simulate streaming data.
    """
    async for message in data:
        json_data = message
        if hasattr(message, 'model_dump_json'):
            json_data = message.model_dump_json()
        if isinstance(json_data, str) and json_data.startswith('data:'):
            yield json_data
        else:
            yield f"data: {json_data}\n\n"
            
            
class file_upload(BaseModel):
    """
    A BaseModel class for handling file uploads to the OpenAI Assistant API.
    This is SIMILAR but not the same as the OpenAI File Object - mostly used to hold the supported file types and their extensions
    and the related ability to be used for vision or retrieval
    
    Attributes:
        file_id: Optional[str] - The ID of the uploaded file.
        filename: str - The name of the file being uploaded.

    Computed Fields:
        extension: str - The file extension extracted from the filename.
        vision: bool - Indicates if the file is an image based on its extension.
        retrieval: bool - Indicates if the file is available for retrieval based on its extension.
    """
    file_id: Optional[str] = None
    filename: str

    
    @computed_field
    def extension(self) -> str:
        return self.filename.split('.')[-1].lower()
    
    @computed_field
    def vision(self) -> bool:
        image_extensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff']
        return self.extension in image_extensions
    @computed_field
    def retrieval(self) -> bool:
        # Determine if the file is for retrieval
        retrieval_extensions = [
            'c', 'cs', 'cpp', 'doc', 'docx', 'html', 'java', 'json', 'md', 'pdf', 'php',
            'pptx', 'py', 'rb', 'tex', 'txt', 'css', 'js', 'sh', 'ts'
        ]
        return self.extension in retrieval_extensions



async def get_assistant_by_name(assistant_name) -> str|None:
	'''
	This function gets the assistant id for the given assistant name.
	It returns the assistant id if found, otherwise it returns None.
	Note will only search for the first 100 assistants.
	
	Args:
		assistant_name: The name of the assistant to search for.
	Returns:
		The assistant_id if found, otherwise it returns None.
	'''
	assistants = await async_openai_client.beta.assistants.list(
		order="asc",
		limit="100",
	)  
	async for assistant in assistants:
		if assistant.name == assistant_name:
			return assistant.id
	return None

async def get_assistants(limit:int=100) -> list[Assistant]:
	assistants = await async_openai_client.beta.assistants.list(
		order="asc",
		limit=limit,
	)  
	return assistants

async def _when_done_str_to_object(when_done:str=None) -> callable:
	"""
	This function converts the when_done string to an object.
	If will split the string into module and function name and try to import the function from the module.
	If the function is not found it will try to get it from the globals().
	If the function is not found it will return None.
	"""
	if when_done:
		module = None
		func = None
		if '.' in when_done:
			module, func = when_done.rsplit('.', 1)
		try:
			if module:
				func = getattr(importlib.import_module(module), func)
			else:
				func = globals().get(when_done)
		except Exception as e:
			logger.error(f"Error in getting function '{when_done}'", e)
			pass
		if not asyncio.iscoroutinefunction(func):
			raise ValueError(f"Provided function '{when_done}' is not found or is not a coroutine")
	return func
	
async def newthread_and_run(assistant_id:str=None, assistant_name:str=None, thread_id:str=None, content:str=None, tools:types.ModuleType=None, metadata:dict={}, files:list=[], when_done:callable=None):
	"""
	This is the main function to run a non streaming thread for an assistant.
	
	parameters:
		assistant_id: The id of the assistant to use.
		assistant_name: The name of the assistant to use.
		
		use assistant_id OR assistant_name - but not both!
		
		thread_id: The id of the thread to use. If not provided a new thread is created.

		content: The content of the message to send to the assistant. This is what you want to Assistant to process. 
		tools: The tools module to use for the tool calls. You pass a module (.py file) that contains the functions you want to use. 
		Names must match with the function names in the Assistant.
		
		metadata: The metadata to store in the thread.
		The Assistant name is always stored in the metadata as 'assistant_name'
		
		files: The list of file_id's to be used by the assistant.
		these need to be uploaded first. They will be provided as 'vision' if they are images. 
		Otherwise they will be provided as 'file_search' or 'code_interpreter' depending on the file type.
		All files will be available for code interpreter and file search.
		
		when_done: The function to be called when the assistant is done. This must be a coroutine!
					This function will receive the thread_id as an argument and can be used to get the full response.
					and do things like send an email or store the results.
					If when_done is not provided the function will (await) the result of the assistant call and return the result.
					(Because otherwise the result will never be know :) )
					if when_done is provided the function will return immediately with a "queued" response that includes the thread_id
					(only) this one is useful for api type calls where you want to offload the processing to a background job
					
	returns:
		The response from the assistant.
	"""
	if not assistant_id:
		assistant_id = await get_assistant_by_name(assistant_name)
		if not assistant_id:
			return {"response": f"Assistant '{assistant_name}' not found", "status_code": 404}
		
	# thread = await prep_thread(thread_id=thread_id, assistant_id=assistant_id, files=files, content=content, metadata=metadata, assistant_name=assistant_name)
		
	if type(when_done) == str:
		when_done = await _when_done_str_to_object(when_done)
	if when_done:
		run = await async_openai_client.beta.threads.runs.create(
						thread_id=thread.id, 
						assistant_id=assistant_id)
		
		task1 = partial(async_openai_client.beta.threads.runs.poll,run_id=run.id,thread_id=thread.id,poll_interval_ms=1000)
		task2 = partial(_process_run,run_id=run.id, thread=thread,tools=tools)
		task3 = partial(when_done,thread.id)
		asyncio.create_task( run_tasks_sequentially(task1,task2,task3))
		return  {"response": f"thread {thread.id} queued for execution", "status_code": 200, "thread_id": thread.id}
	else:
		run = await async_openai_client.beta.threads.runs.create_and_poll(
						thread_id=thread.id, 
						assistant_id=assistant_id, 
						poll_interval_ms=1000)
		return await _process_run(run_id=run.id, thread=thread,tools=tools)


async def stream_thread(assistant_id:str=None, assistant_name:str=None, thread:Thread=None, content:str=None, tools:types.ModuleType=None, metadata:dict={}, files:list=[], when_done:callable=None, extra_args:dict={}, progress_callback:callable=None):
	if not assistant_id:
		assistant_id = await get_assistant_by_name(assistant_name)
		if not assistant_id:
			raise ValueError(f"Assistant {assistant_name} not found")
	# thread = await prep_thread(thread_id=thread_id, assistant_id=assistant_id, files=files, content=content, metadata=metadata, assistant_name=assistant_name)

	stream = await async_openai_client.beta.threads.runs.create(
						thread_id=thread.id, 
						assistant_id=assistant_id, 
						stream=True)

	async for event in stream:
		async for token in _process_event(event=event, thread=thread, tools=tools, extra_args=extra_args, progress_callback=progress_callback):
			yield token
			
async def add_vision_files(thread_id:str, vision_files:list=[]):
	for v in vision_files:
		await async_openai_client.beta.threads.messages.create(
			thread_id=thread_id,
			content= [{
			'type' : "image_file",
			'image_file' : {"file_id": v.file_id ,'detail':'high'}}],
			role="user"
		)  
				
			
			
async def prep_thread(thread_id:str=None, assistant_id:str=None, files:list=[], content:str=None, metadata:dict={}, assistant_name:str=None) -> Thread:
	vision_files = []
	attachment_files = []
	if files:
		for i in range(len(files)):
			if type(files[i]) == str:
				files[i] = await retrieve_file_object(files[i])
			if files[i].vision:
				vision_files.append( files[i])
				continue
			else:
				attachment_files.append({"file_id": files[i].file_id, "tools": [{"type": "file_search" if files[i].retrieval else "code_interpreter"  }]})     
	thread = await get_thread(thread_id=thread_id, assistant_name=assistant_name, metadata=metadata) # create a new thread, store assistant name in meta data thread is created if not exists
	await async_openai_client.beta.threads.messages.create(
		thread.id,
		role="user",
		attachments=attachment_files,
		content=content,
	)
	await add_vision_files(thread_id=thread.id, vision_files=vision_files)
	return thread

async def get_thread(thread_id:str=None, assistant_name:str=None, metadata:dict={}) -> Thread:
	"""
	This function either creates a new thread or retrieves an existing thread. 
	If assistant_name is provided, it will store the assistant name in the metadata of the thread.
	If thread_id is provided, it will retrieve the thread.
	
	Args:
		thread_id: The id of the thread to retrieve.
		
		assistant_name: The name of the assistant to store in the metadata of the thread.
		assistant_id: The id of the assistant to store in the metadata of the thread.
		- use assistant_id OR assistant_name - but not both!
		
		metadata: The metadata to store in the thread.
	Returns:
		The thread object.
	"""
	thread = None
	if thread_id:
		try:
			thread = await async_openai_client.beta.threads.retrieve(thread_id)
		except Exception as e:  # pylint: disable=bare-except, broad-except
			logger.error("Error in getting thread", e)
			thread = None
	if not thread:
		if assistant_name:
			metadata["assistant_name"] = assistant_name        
		thread = await async_openai_client.beta.threads.create(
			metadata= metadata
		)
	return thread


async def _process_run(run_id:str, thread: Thread,tools:types.ModuleType):
	"""
	Process run

	Args:
		event: The event to be processed.
		thread: The thread object.
		**kwargs: Additional keyword arguments.

	Raises:
		Exception: If the run fails.
	"""
	run = await async_openai_client.beta.threads.runs.retrieve(run_id=run_id, thread_id=thread.id)
	while not run.status in ['completed','expired','failed','cancelled','incomplete']:
		# note this only loops after function calling and possibly next function calling or code interpreter
		if run.status == 'requires_action':
					
			tool_outputs = await _process_tool_calls(
				tool_calls=run.required_action.submit_tool_outputs.tool_calls,
				tools=tools
			)
			run = await async_openai_client.beta.threads.runs.submit_tool_outputs_and_poll(
					thread_id=thread.id,
					run_id=run.id,
					tool_outputs=tool_outputs,
				)

# RUN STATUS: COMPLETED
	if run.status == "completed":
		response_message = await getfullresponse(run.thread_id)
		return {"response": response_message, "status_code": 200, "thread_id": thread.id}

# RUN STATUS: EXPIRED | FAILED | CANCELLED | INCOMPLETE
	if run.status in ['expired','failed','cancelled','incomplete']:
		return {"response": run.last_error, "status_code": 500, "thread_id": thread.id}
	
	
async def _process_event(event, thread: Thread,tools:types.ModuleType, extra_args:dict={}, progress_callback:callable=None):
	"""
	Process an event in the thread - for streaming runs

	Args:
		event: The event to be processed.
		thread: The thread object.
		**kwargs: Additional keyword arguments.

	Yields:
		The processed tokens.

	Raises:
		Exception: If the run fails.
	"""
	if isinstance(event, ThreadMessageDelta):
		data = event.data.delta.content
		for d in data:
			yield d

	elif isinstance(event, ThreadRunRequiresAction):
		run = event.data
		print('Processing tool calls')
		tool_outputs = await _process_tool_calls(
				tool_calls=run.required_action.submit_tool_outputs.tool_calls,
				tools=tools, extra_args=extra_args, progress_callback=progress_callback
			)
		tool_output_events =  (await async_openai_client.beta.threads.runs.submit_tool_outputs(
					thread_id=thread.id,
					run_id=run.id,
					tool_outputs=tool_outputs,stream=True
				))
		async for tool_event in tool_output_events:
			async for token in _process_event(
				tool_event, thread=thread,tools=tools, extra_args=extra_args, progress_callback=progress_callback
			):
				yield token

	elif any(
		isinstance(event, cls)
		for cls in [
			ThreadRunFailed,
			ThreadRunCancelling,
			ThreadRunCancelled,
			ThreadRunExpired,
			ThreadRunStepFailed,
			ThreadRunStepCancelled,
		]
	):
		# Determine which specific event type caused the failure
		event_type = type(event).__name__
		error_details = {
			"event_type": event_type,
			"thread_id": thread.id if thread else None,
		}
		
		# Extract additional error information if available
		if hasattr(event, 'data'):
			event_data = event.data
			if hasattr(event_data, 'last_error') and event_data.last_error:
				error_details["last_error"] = {
					"code": event_data.last_error.code if hasattr(event_data.last_error, 'code') else None,
					"message": event_data.last_error.message if hasattr(event_data.last_error, 'message') else None
				}
			if hasattr(event_data, 'status'):
				error_details["status"] = event_data.status
			if hasattr(event_data, 'failed_at'):
				error_details["failed_at"] = event_data.failed_at
				
		# Log the detailed error
		logger.error(f"Assistant run failed: {error_details}")
		
		# Analyze the failure and get suggestions
		failure_analysis = analyze_run_failure(event_type, error_details)
		
		# Raise a more informative exception
		error_message = f"Run failed with {event_type}"
		if "last_error" in error_details and error_details["last_error"].get("message"):
			error_message += f": {error_details['last_error']['message']}"
		
		# Include the analysis in the error message
		if failure_analysis:
			error_message += f"\n{failure_analysis['reason']}. {failure_analysis['suggestion']}"
		
		print("Event:")
		print(event)
		raise Exception(error_message) # pylint: disable=broad-exception-raised

async def _process_tool_call(tool_call:str, tool_outputs: list, extra_args:dict=None, tools:types.ModuleType=None):
	"""
	This function processes a single tool call.
	And also handles the exceptions.
	
	The function needs to be async because it calls the tool functions which may perform
	asynchronous operations like making API calls or database queries. The 'await to_run(arguments)'
	call allows these async tool functions to complete without blocking.
	
	Args:
		tool_call: The tool call to be processed. this is the function name that is going to be called
		tool_outputs: The list of tool outputs.
		extra_args: The extra arguments.
		tools: The tools module to use for the tool calls.
	Returns:
		The tool output.
	"""
	result = None
	try:
		arguments = json.loads(tool_call.function.arguments)
		
		function_name = tool_call.function.name
		if extra_args:
			for key, value in extra_args.items():
				arguments[key] = value
							
		#tool_instance keeps track of functions we have already seen
		# load the tool from tools.tools
		to_run = None
		try:
			to_run = getattr(tools, function_name)
		except Exception as e:
			logger.error(f"Error in getting tool {function_name}", e)
			to_run = None
		if to_run is None:
			result = f"Function {function_name} not supported"
		else:
			result = await to_run(**arguments)
	except Exception as e:  # pylint: disable=broad-except
		print('Error in processing tool call: ', e)
		result = str(e)
		logger.error(e)
	print('Appending tool output: ', result)
	tool_outputs.append({
		"tool_call_id": tool_call.id,
		"output": result,
	})

async def _process_tool_calls(tool_calls:list, extra_args:dict=None, tools:types.ModuleType=None,stream:bool=False, progress_callback:callable=None):
	"""
	This function processes all the tool calls.
	"""
	tool_outputs = []
	coroutines = []
	for tool_call in tool_calls:
		print('Calling tool call: ', tool_call.function.name)
		coroutines.append(_process_tool_call(tool_call=tool_call, tool_outputs=tool_outputs, extra_args=extra_args, tools=tools))
		# Send progress updates on each tool calls since they take long times
		if progress_callback:
			# Check if progress_callback is a coroutine function and await it if so
			if asyncio.iscoroutinefunction(progress_callback):
				await progress_callback(tool_call)
			else:
				progress_callback(tool_call)
	if coroutines:
		await asyncio.gather(*coroutines)
	return tool_outputs


async def uploadfile(file=None,file_content=None,filename=None) -> file_upload:
	''' Upload a file to openAI either for the Assistant or for the Thread.
	
	parameters:
		file - a file object
		file_content - the content of the file
					
		filename - the name of the file. If not provided will use the name of the file object
		All uploaded files will automatically be provided in the message to the assistant with both search and code interpreter enabled.
		
	returns:
		file_upload object
	'''
	if file_content == None:
		file_content = await file.read()
	# Determine file extension
	file_upload_object = file_upload(file=file, file_content=file_content, filename=filename)
	
	
	uploaded_file = await async_openai_client.files.create( file=(filename,file_content),purpose=('vision' if file_upload_object.vision else 'assistants'))
	#uploadFile = async_openai_client.files.create( file=(filename,fileContent),purpose='assistants')

	# Append the file information to self._fileids
	return file_upload(file_id=uploaded_file.id, filename=filename, vision=file_upload_object.vision, retrieval=file_upload_object.retrieval)

async def get_response(self, thread_id, remove_annotations:bool=True):
	messages = await async_openai_client.beta.threads.messages.list(thread_id=thread_id)
	message_content = messages.data[0].content[0].text
	# Remove annotations
	if remove_annotations:
		message_content = _remove_annotations(message_content)

	response_message = message_content.value
	return response_message

def _remove_annotations(message_content):
	annotations = message_content.annotations
	for annotation in annotations:
		message_content.value = message_content.value.replace(annotation.text, '')
	return message_content

async def getlastresponse(self, thread_id:str=None):
	''' Get the last response from the assistant, returns messages.data[0] 
	'''
	messages = await async_openai_client.beta.threads.messages.list( thread_id=thread_id)
	return messages.data[0]

async def getallmessages(self, thread_id:str=None) -> list:
	''' Get all messages from the assistant - returns messages.data (list)
	'''
	messages = await async_openai_client.beta.threads.messages.list( thread_id=thread_id)
	return messages.data

async def getfullresponse(self, thread_id:str=None, remove_annotations:bool=True) -> str:
	''' Get the full text response from the assistant (concatenated text type messages)
	traverses the messages.data list and concatenates all text messages
	'''
	messages = await async_openai_client.beta.threads.messages.list( thread_id=thread_id)
	res = ''
	for m in reversed(messages.data):
		if m.role == 'assistant':
			for t in m.content:
				if t.type == 'text':
					if remove_annotations:
						res += _remove_annotations(t.text).value
					else:
						res += t.text.value
					
	return res

async def retrievefile(self,file_id:str) -> bytes:
	''' Retrieve the FILE CONTENT of a file from OpenAI 
	'''
	return await async_openai_client.files.content(file_id=file_id)

async def retrieve_file_object(self,file_id:str) -> file_upload:
	''' 
	Retrieve a File  Upload Object of an uploaded file
	This is SIMILAR but not the same as the OpenAI File Object
	'''
	file = await async_openai_client.files.retrieve(file_id=file_id)
	return file_upload(file_id=file.id, filename=file.filename, vision=file.purpose == 'vision', retrieval=file.purpose == 'assistants')

async def transcribe_audio(self,file=None,file_content=None,file_name=None):
	'''
	Transcribe an audio file
	'''
	if file_content == None:
		file_content = await file.read()
	if file_name == None:
		file_name = file.filename
	return await async_openai_client.audio.transcriptions.create(
		model="whisper-1", 
		file=(file_name,file_content)
	)