import httpx
import html2text
import asyncio
import re
from typing import Set, List, Dict, Any, Optional
from pydantic import HttpUrl
from ai.ai_api import create_google_request
import json

def html_to_text(html,ignore_links=False,bypass_tables=False,ignore_images=True):
	'''
	This function is used to convert html to text.
	It converts the html to text and returns the text.
	
	Args:
		html (str): The HTML content to convert to text.
		ignore_links (bool): Ignore links in the text. Use 'False' to receive the URLs of nested pages to scrape.
		bypass_tables (bool): Bypass tables in the text. Use 'False' to receive the text of the tables.
		ignore_images (bool): Ignore images in the text. Use 'False' to receive the text of the images.
	Returns:
		str: The text content of the webpage. If max_length is provided, the text will be truncated to the specified length.
	'''
	text = html2text.HTML2Text()
	text.ignore_links = ignore_links
	text.bypass_tables = bypass_tables
	text.ignore_images = ignore_images
	return text.handle(html,)

async def get_website_url_content(url: HttpUrl, ignore_links: bool = False, max_length: int = None, tenant_name:str=None):
	'''
	This function is used to scrape a webpage.
	It converts the html to text and returns the text.
	
	Args:
		plain_json (dict): The JSON data containing the URL to scrape. It is meant to be called as a tool call from an assistant.
		the json should be in the format of {"url": "https://www.example.com", "ignore_links": False, "max_length": 1000}

	Returns:
		str: The text content of the webpage. If max_length is provided, the text will be truncated to the specified length.
	'''
	header = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'}
	try:
		async with httpx.AsyncClient(follow_redirects=True) as client:
			response = await client.get(str(url), headers=header, timeout=5)
	except Exception as e:
		print('Error in webscrape: ', e)
		print('URL: ', str(url))
		return "Error fetching the url "+str(url)
	out = html_to_text(response.text,ignore_links=ignore_links)
	if max_length:
		return out[0:max_length]
	else:
		return out

max_characters_form_web_page = 500000
max_characters_for_final_check = 800000

async def check_content_with_ai(content: str, search_query: str, link_count: int, is_final: bool = False, accumulated_text: Optional[str] = None) -> Dict[str, Any]:
	'''
	Checks the content with Google's AI to see if it contains the answer to the search query.
	
	Args:
		content (str): The text from the current web page or accumulated text if is_final is True.
		search_query (str): The query to search for in the content.
		link_count (int): The number of links processed so far.
		is_final (bool): Whether this is the final check using accumulated text.
		accumulated_text (Optional[str]): The accumulated text from all crawled pages, used only if is_final is True.
		
	Returns:
		Dict[str, Any]: The parsed AI response containing definitive_answer_found, answer, and other_related_links.
	'''
	text_to_check = accumulated_text if is_final else content
	max_chars = max_characters_for_final_check if is_final else max_characters_form_web_page
	
	prompt = f"""
	I have collected text from {'multiple web pages' if is_final else 'a web page'}. Here's the information:
	
	{text_to_check[:max_chars]} 
	Based on this information, please answer the following question in JSON format.:
	{search_query}

	Only return true for  definitive_answer_found if the answer is definitely and precisely found in the text. If it only has related information but not the actual response (i.e. mentions the topic but not the answer to that topic question), return definitive_answer_found as false. If there is missing information, we will continue crawling so return false.
	If a definitive answer is found, give a detailed explanation back of the answer using the information. If the query is related to code or development, make sure to add the code snippets wrapped in ```code```. Do not write links in the detailed_explanation but add them to the other_related_links list in the JSON. Incorporate all the related information as well as any other information even though the user didn't ask for it. Limit other related links to just 5.

	Use this JSON schema:

	Answer = {{'definitive_answer_found': str, 'detailed_explanation': str, 'other_related_links': list[str]}}
	Return: Answer
	
	"""
	
	ai_response = create_google_request(
		prompt=prompt,
		model_name="gemini-2.0-flash-lite",
		temperature=0.2,
		max_tokens=600,
		response_mime_type="application/json"
	)

		
	# Parse the JSON response
	try:
		parsed_response = json.loads(ai_response)
		if isinstance(parsed_response, list) and len(parsed_response) > 0:
			parsed_response = parsed_response[0]
		return parsed_response
	except json.JSONDecodeError:
		print("Error parsing AI response: ", ai_response)
		# Return a default structure if parsing fails
		return {
			"definitive_answer_found": "false",
			"detailed_explanation": "Failed to parse AI response",
			"other_related_links": []
		}

async def crawl_website_for_information(start_url: HttpUrl, search_query: str, max_links: int = 200, check_interval: int = 50, tenant_name: str = None):
	'''
	Crawls a website starting from the given URL, follows outgoing links, and accumulates text.
	Periodically checks if the current page content contains the answer to the search query using Google's AI.
	Also uses AI to filter which links to follow based on relevance to the search query.
	
	Args:
		start_url (HttpUrl): The starting URL to begin crawling from.
		search_query (str): The query to search for in the accumulated text.
		max_links (int): Maximum number of links to crawl. Default is 200.
		check_interval (int): How often to check with Google's AI (in number of links). Default is 50.
		tenant_name (str): Optional tenant name for tracking purposes.
		
	Returns:
		Dict: A dictionary containing the accumulated text, visited URLs, and the AI's response.
	'''
	from ai.ai_api import create_google_request
	import json
	
	visited_urls: Set[str] = set()
	to_visit: List[str] = [str(start_url)]
	accumulated_text: str = ""
	results: Dict[str, Any] = {
		"visited_urls": [],
		"accumulated_text": "",
		"ai_responses": []
	}
	
	link_count = 0
	
	while to_visit and link_count < max_links:
		current_url = to_visit.pop(0)
		
		# Skip if already visited
		if current_url in visited_urls:
			continue
			
		print(f"Crawling: {current_url} ({link_count + 1}/{max_links})")
		
		# Get content from the URL
		content = await get_website_url_content(current_url, ignore_links=False, tenant_name=tenant_name)
		
		# Mark as visited
		visited_urls.add(current_url)
		results["visited_urls"].append(current_url)
		link_count += 1
		
		# Add content to accumulated text
		accumulated_text += f"\n\n--- Content from {current_url} ---\n\n{content}"
		
		# Check current page content with AI
		ai_response = await check_content_with_ai(content, search_query, link_count)
		
		results["ai_responses"].append({
			"url": current_url,
			"links_processed": link_count,
			"response": ai_response
		})

		# If AI found a definitive answer, we can stop crawling
		if ai_response and ai_response.get("definitive_answer_found", "").lower() == "true":
			print(f"Answer found after processing {link_count} links")
			print("FINAL AI RESPONSE: ", ai_response)
			return {
				"link": current_url,
				"ai_response": ai_response
			}
		
		# Extract links from the content
		all_links = extract_links_from_text(content)
		
		# Filter out already visited links
		new_links = [link for link in all_links if link not in visited_urls and link not in to_visit]
		
		# Convert relative links to absolute
		processed_links = []
		for link in new_links:
			if not link.startswith(('http://', 'https://')):
				# Try to construct absolute URL
				base_url = '/'.join(current_url.split('/')[:3])  # Get domain part
				if link.startswith('/'):
					link = f"{base_url}{link}"
				else:
					path_parts = current_url.split('/')
					if len(path_parts) > 3:
						parent_path = '/'.join(path_parts[:-1])
						link = f"{parent_path}/{link}"
					else:
						link = f"{base_url}/{link}"
			processed_links.append(link)
		
		# Use AI to filter links for relevance
		if processed_links:
			filter_prompt = f"""The user is looking for {search_query}
The links to visit are: {processed_links}
Return the links that would be relevant to what they might be looking for and only return the links that point to more information websites (filter out links to home page, footer, navbar, etc.)

Use this JSON schema:
Return: list[str]"""

			try:
				ai_link_response = create_google_request(
					prompt=filter_prompt,
					model_name="gemini-2.0-flash-lite",
					temperature=0.2,
					max_tokens=1000,
					response_mime_type="application/json"
				)
				
				if ai_link_response:
					try:
						filtered_links = json.loads(ai_link_response)
						if isinstance(filtered_links, list):
							to_visit.extend(filtered_links)
							print(f"AI filtered links from {len(processed_links)} to {len(filtered_links)}")
						else:
							# Fallback if AI didn't return a list
							to_visit.extend(processed_links)
					except json.JSONDecodeError:
						# Fallback if AI didn't return valid JSON
						to_visit.extend(processed_links)
				else:
					# Fallback if AI didn't respond
					to_visit.extend(processed_links)
			except Exception as e:
				print(f"Error filtering links with AI: {e}")
				# Fallback to using all links
				to_visit.extend(processed_links)
	
	# Final check with accumulated text if we've processed all links or reached the limit
	final_ai_response = await check_content_with_ai("", search_query, link_count, is_final=True, accumulated_text=accumulated_text)
	
	results["ai_responses"].append({
		"links_processed": link_count,
		"is_final": True,
		"response": final_ai_response
	})
	
	results["accumulated_text"] = accumulated_text
	return final_ai_response if final_ai_response.get("definitive_answer_found", "").lower() == "true" else results

def extract_links_from_text(text: str) -> List[str]:
	'''
	Extracts links from markdown text produced by html2text.
	
	Args:
		text (str): The markdown text to extract links from.
		
	Returns:
		List[str]: A list of extracted links.
	'''
	# Pattern to match markdown links: [text](url)
	markdown_links = re.findall(r'\[.*?\]\((.*?)\)', text)
	
	# Pattern to match bare URLs
	bare_urls = re.findall(r'(?<!\()(https?://[^\s\)]+)(?!\))', text)
	
	# Combine and remove duplicates
	all_links = list(set(markdown_links + bare_urls))
	
	return all_links

# if __name__ == "__main__":
# 	asyncio.run(crawl_website_for_information(HttpUrl("https://docs.github.com/en/rest/code-scanning/code-scanning?apiVersion=2022-11-28"), "How to get copilot usage data?", 200, 1, "test"))