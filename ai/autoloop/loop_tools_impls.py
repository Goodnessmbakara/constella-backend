import requests
from typing import List, Dict, Any
import re
import sys
import os

# Add the parent directory to path to import helpers
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from routers.misc.helpers import read_pdf_from_url

def search_papers(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Search for academic papers using Semantic Scholar API

    Args:
        query: Search query string
        max_results: Maximum number of papers to return

    Returns:
        Dictionary containing search results with papers list
    """
    try:
        # Semantic Scholar API endpoint
        url = "https://api.semanticscholar.org/graph/v1/paper/search"

        params = {
            'query': query,
            'limit': max_results,
            'fields': 'paperId,title,authors,abstract,url,venue,year,citationCount,referenceCount,publicationTypes'
        }

        headers = {
            'User-Agent': 'Research-Autoloop-Tool/1.0'
        }

        response = requests.get(url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()

            # Format the results
            papers = []
            for paper in data.get('data', []):
                formatted_paper = {
                    'id': paper.get('paperId', ''),
                    'title': paper.get('title', ''),
                    'authors': [author.get('name', '') for author in paper.get('authors', [])],
                    'abstract': paper.get('abstract', ''),
                    'link': paper.get('url', ''),
                    'venue': paper.get('venue', ''),
                    'year': paper.get('year', ''),
                    'citation_count': paper.get('citationCount', 0),
                    'reference_count': paper.get('referenceCount', 0),
                    'publication_types': paper.get('publicationTypes', [])
                }
                papers.append(formatted_paper)

            result = {
                'success': True,
                'query': query,
                'total_results': data.get('total', 0),
                'papers': papers
            }
            print(f"[TOOL] search_papers completed: Found {len(papers)} papers for query '{query}'")
            return result
        else:
            result = {
                'success': False,
                'error': f"API request failed with status {response.status_code}",
                'papers': []
            }
            print(f"[TOOL] search_papers failed: {result['error']}")
            return result

    except Exception as e:
        result = {
            'success': False,
            'error': f"Error searching papers: {str(e)}",
            'papers': []
        }
        print(f"[TOOL] search_papers error: {result['error']}")
        return result

def get_potential_pdf_urls(paper_data: Dict) -> List[str]:
    """
    Get potential PDF URLs from paper data

    Args:
        paper_data: Paper data from Semantic Scholar API

    Returns:
        List of potential PDF URLs to try
    """
    urls = []

    # Check for open access PDF
    if paper_data.get('openAccessPdf', {}).get('url'):
        urls.append(paper_data['openAccessPdf']['url'])

    # Try ArXiv URL if available
    external_ids = paper_data.get('externalIds', {})
    if external_ids.get('ArXiv'):
        urls.append(f"https://arxiv.org/pdf/{external_ids['ArXiv']}.pdf")

    # Try DOI-based URLs
    if external_ids.get('DOI'):
        # Some publishers provide direct PDF access
        doi = external_ids['DOI']
        urls.append(f"https://doi.org/{doi}")

    return urls

def extract_research_contributions_from_full_text(full_text: str) -> List[str]:
    """
    Extract research contributions from full paper text

    Args:
        full_text: Full text content of the paper

    Returns:
        List of identified research contributions
    """
    if not full_text:
        return []

    contribution_indicators = [
        r'we (?:present|introduce|propose|develop|demonstrate|show|find|establish|contribute)',
        r'this (?:paper|work|study|research) (?:presents|introduces|proposes|develops|demonstrates|shows|contributes)',
        r'our (?:approach|method|algorithm|technique|framework|contribution|findings|results)',
        r'novel (?:approach|method|algorithm|technique|framework)',
        r'new (?:method|approach|algorithm|technique|framework)',
        r'first time|for the first time',
        r'significantly (?:improves?|outperforms?|advances?)',
        r'breakthrough|innovation|innovative',
        r'main contribution|key contribution|primary contribution',
        r'we show that|we demonstrate that|we prove that'
    ]

    found_contributions = []
    sentences = re.split(r'(?<=[.!?])\s+', full_text)

    for sentence in sentences:
        for indicator in contribution_indicators:
            if re.search(indicator, sentence, re.IGNORECASE):
                clean_sentence = sentence.strip()
                if 20 < len(clean_sentence) < 500:
                    found_contributions.append(clean_sentence)
                break

    return list(set(found_contributions))[:5]

def extract_research_gaps_from_full_text(full_text: str) -> List[str]:
    """
    Extract research gaps from full paper text

    Args:
        full_text: Full text content of the paper

    Returns:
        List of identified research gaps
    """
    if not full_text:
        return []

    gap_indicators = [
        r'future work|future research|future studies',
        r'limitations?(?:\s+of)?(?:\s+this)?(?:\s+study)?',
        r'further research|additional research|more research',
        r'unanswered questions?|open questions?',
        r'remains? to be (?:explored|investigated|studied|determined)',
        r'need(?:s)? to be (?:explored|investigated|studied|addressed)',
        r'warrant(?:s)? (?:further )?investigation',
        r'(?:research )?gap(?:s)? (?:in|exists?|remains?)',
        r'not (?:yet )?(?:been )?(?:fully )?(?:explored|investigated|studied|addressed)',
        r'insufficient (?:data|evidence|research)',
        r'lack(?:s)? of (?:data|evidence|research|studies)',
        r'unexplored (?:area|domain|field|aspect)'
    ]

    found_gaps = []
    sentences = re.split(r'(?<=[.!?])\s+', full_text)

    for sentence in sentences:
        for indicator in gap_indicators:
            if re.search(indicator, sentence, re.IGNORECASE):
                clean_sentence = sentence.strip()
                if 20 < len(clean_sentence) < 500:
                    found_gaps.append(clean_sentence)
                break

    return list(set(found_gaps))[:5]

def read_full_paper_content(paper_id: str) -> Dict[str, Any]:
    """
    Retrieve detailed content of a specific paper using Semantic Scholar API and PDF reading

    Args:
        paper_id: The paper ID from Semantic Scholar

    Returns:
        Dictionary containing detailed paper information including full text if available
    """
    try:
        # Semantic Scholar API endpoint for specific paper
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"

        params = {
            'fields': 'paperId,title,authors,abstract,url,venue,year,citationCount,referenceCount,publicationTypes,citations,references,tldr,s2FieldsOfStudy,publicationDate,openAccessPdf,externalIds'
        }

        headers = {
            'User-Agent': 'Research-Autoloop-Tool/1.0'
        }

        response = requests.get(url, params=params, headers=headers)

        if response.status_code == 200:
            paper = response.json()

            # Format citations
            citations = []
            for citation in paper.get('citations', [])[:10]:  # Limit to first 10 citations
                if citation.get('citingPaper'):
                    citing = citation['citingPaper']
                    citations.append({
                        'title': citing.get('title', ''),
                        'authors': [author.get('name', '') for author in citing.get('authors', [])],
                        'year': citing.get('year', ''),
                        'paper_id': citing.get('paperId', '')
                    })

            # Format references
            references = []
            for reference in paper.get('references', [])[:10]:  # Limit to first 10 references
                if reference.get('citedPaper'):
                    cited = reference['citedPaper']
                    references.append({
                        'title': cited.get('title', ''),
                        'authors': [author.get('name', '') for author in cited.get('authors', [])],
                        'year': cited.get('year', ''),
                        'paper_id': cited.get('paperId', '')
                    })

            # Try to get full text from PDF
            full_text = ""
            pdf_contributions = []
            pdf_gaps = []
            pdf_success = False

            pdf_urls = get_potential_pdf_urls(paper)
            for pdf_url in pdf_urls:
                try:
                    print(f"Attempting to read PDF from: {pdf_url}")
                    full_text, num_pages = read_pdf_from_url(pdf_url, timeout=30)
                    if full_text and len(full_text) > 100:  # Ensure we got meaningful content
                        pdf_contributions = extract_research_contributions_from_full_text(full_text)
                        pdf_gaps = extract_research_gaps_from_full_text(full_text)
                        pdf_success = True
                        print(f"Successfully extracted {len(pdf_contributions)} contributions and {len(pdf_gaps)} gaps from PDF")
                        break
                except Exception as pdf_error:
                    print(f"Failed to read PDF from {pdf_url}: {str(pdf_error)}")
                    continue

            formatted_paper = {
                'success': True,
                'paper_id': paper.get('paperId', ''),
                'title': paper.get('title', ''),
                'authors': [author.get('name', '') for author in paper.get('authors', [])],
                'abstract': paper.get('abstract', ''),
                'link': paper.get('url', ''),
                'venue': paper.get('venue', ''),
                'year': paper.get('year', ''),
                'publication_date': paper.get('publicationDate', ''),
                'citation_count': paper.get('citationCount', 0),
                'reference_count': paper.get('referenceCount', 0),
                'publication_types': paper.get('publicationTypes', []),
                'fields_of_study': [field.get('category', '') for field in paper.get('s2FieldsOfStudy', [])],
                'tldr': paper.get('tldr', {}).get('text', '') if paper.get('tldr') else '',
                'citations': citations,
                'references': references,
                'full_text': full_text[:5000] if full_text else '',  # Limit to first 5000 chars
                'full_text_available': pdf_success,
                'research_contributions': pdf_contributions,
                'research_gaps': pdf_gaps
            }

            print(f"[TOOL] read_full_paper_content completed: Paper '{paper.get('title', '')}' - PDF success: {pdf_success}, Contributions: {len(pdf_contributions)}, Gaps: {len(pdf_gaps)}")
            return formatted_paper
        else:
            result = {
                'success': False,
                'error': f"API request failed with status {response.status_code}",
                'paper_id': paper_id
            }
            print(f"[TOOL] read_full_paper_content failed: {result['error']}")
            return result

    except Exception as e:
        result = {
            'success': False,
            'error': f"Error reading paper content: {str(e)}",
            'paper_id': paper_id
        }
        print(f"[TOOL] read_full_paper_content error: {result['error']}")
        return result

def search_papers_by_topic(topic: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search for papers on a specific research topic

    Args:
        topic: Research topic to search for
        max_results: Maximum number of papers to return

    Returns:
        Dictionary containing search results formatted for research tracking
    """
    search_result = search_papers(topic, max_results)

    if search_result['success']:
        # Format for research tracking structure
        formatted_papers = []
        for paper in search_result['papers']:
            formatted_papers.append({
                'title': paper['title'],
                'authors': paper['authors'],
                'link': paper['link'],
                'abstract': paper['abstract']
            })

        result = {
            'success': True,
            'topic': topic,
            'papers': formatted_papers
        }
        print(f"[TOOL] search_papers_by_topic completed: Found {len(formatted_papers)} papers for topic '{topic}'")
        return result
    else:
        print(f"[TOOL] search_papers_by_topic failed for topic '{topic}': {search_result.get('error', 'Unknown error')}")
        return search_result

def analyze_research_gaps(papers: List[Dict], topic: str) -> Dict[str, Any]:
    """
    Analyze a collection of papers to identify research gaps

    Args:
        papers: List of paper dictionaries
        topic: The research topic being analyzed

    Returns:
        Dictionary containing identified gaps
    """
    try:
        # Simple gap analysis based on abstracts and topics
        common_themes = set()
        limitations_mentioned = []

        for paper in papers:
            abstract = paper.get('abstract', '').lower()

            # Extract common themes (simplified)
            if 'machine learning' in abstract:
                common_themes.add('machine learning')
            if 'deep learning' in abstract:
                common_themes.add('deep learning')
            if 'neural network' in abstract:
                common_themes.add('neural networks')
            if 'reinforcement learning' in abstract:
                common_themes.add('reinforcement learning')

            # Look for limitation keywords
            limitation_keywords = ['limitation', 'challenge', 'future work', 'further research', 'gap']
            for keyword in limitation_keywords:
                if keyword in abstract:
                    # Extract sentence containing the limitation
                    sentences = re.split(r'[.!?]', abstract)
                    for sentence in sentences:
                        if keyword in sentence:
                            limitations_mentioned.append(sentence.strip())

        # Generate potential research gaps
        gaps = []
        gap_id = 1

        # Gap based on missing methodologies
        if 'deep learning' in common_themes and 'reinforcement learning' not in common_themes:
            gaps.append({
                'title': f'Application of Reinforcement Learning to {topic}',
                'id': f'gap_{gap_id}',
                'connections': ['reinforcement learning', topic]
            })
            gap_id += 1

        # Gap based on limitations
        if limitations_mentioned:
            gaps.append({
                'title': f'Addressing Common Limitations in {topic} Research',
                'id': f'gap_{gap_id}',
                'connections': ['limitations', topic, 'methodology improvement']
            })
            gap_id += 1

        # Generic gaps for demonstration
        for i in range(min(3, 10 - len(gaps))):
            gaps.append({
                'title': f'Novel Approach {i+1} for {topic}',
                'id': f'gap_{gap_id}',
                'connections': [topic, 'novel methodology', 'innovation']
            })
            gap_id += 1

        return {
            'success': True,
            'topic': topic,
            'identified_gaps': gaps,
            'common_themes': list(common_themes),
            'limitations_found': limitations_mentioned[:5]  # Limit to first 5
        }

    except Exception as e:
        return {
            'success': False,
            'error': f"Error analyzing research gaps: {str(e)}",
            'topic': topic
        }

def read_paper_pdf_content(paper_url: str) -> Dict[str, Any]:
    """
    Read PDF content directly from a paper URL

    Args:
        paper_url: Direct URL to a PDF paper

    Returns:
        Dictionary containing extracted text and analysis
    """
    try:
        full_text, num_pages = read_pdf_from_url(paper_url, timeout=30)

        if not full_text:
            return {
                'success': False,
                'error': 'No content extracted from PDF',
                'url': paper_url
            }

        # Extract contributions and gaps
        contributions = extract_research_contributions_from_full_text(full_text)
        gaps = extract_research_gaps_from_full_text(full_text)

        return {
            'success': True,
            'url': paper_url,
            'full_text': full_text[:10000],  # First 10k characters
            'num_pages': num_pages,
            'research_contributions': contributions,
            'research_gaps': gaps,
            'text_length': len(full_text)
        }

    except Exception as e:
        return {
            'success': False,
            'error': f"Error reading PDF: {str(e)}",
            'url': paper_url
        }

def update_tracking_data(property_updates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Update tracking data properties with different update types.

    This tool MUST be called after each turn of the loop to persist internal tracking
    data. Feed it the properties that changed this turn; it will update ALL provided
    properties without hesitation.
    
    Args:
        property_updates: Dictionary mapping property names to update specifications.
                          Each update spec should have. Depending on the properties you need to update
                          - typeOfUpdate: 'CHANGE_VALUE', 'ARRAY_PUSH_VALUE', or 'ARRAY_REMOVE_VALUE'
                          - updateValue: The value to use for the update
    
    Returns:
        Dictionary indicating success/failure and updated properties
    """
    try:
        # This is a placeholder implementation - in a real system, this would
        # interact with the actual state management system
        updated_properties = {}
        
        for property_name, update_spec in property_updates.items():
            type_of_update = update_spec.get('typeOfUpdate')
            update_value = update_spec.get('updateValue')
            
            if type_of_update not in ['CHANGE_VALUE', 'ARRAY_PUSH_VALUE', 'ARRAY_REMOVE_VALUE']:
                return {
                    'success': False,
                    'error': f"Invalid update type '{type_of_update}' for property '{property_name}'"
                }
            
            # Record the update operation (in real implementation, this would modify actual state)
            updated_properties[property_name] = {
                'operation': type_of_update,
                'value': update_value,
                'timestamp': requests.get('http://worldtimeapi.org/api/timezone/Etc/UTC').json().get('datetime', 'unknown') if hasattr(requests, 'get') else 'unknown'
            }
        
        result = {
            'success': True,
            'updated_properties': updated_properties,
            'message': f"Successfully updated {len(updated_properties)} properties"
        }
        print(f"[TOOL] update_tracking_data completed: Updated {len(updated_properties)} properties: {list(property_updates.keys())}")
        return result
        
    except Exception as e:
        result = {
            'success': False,
            'error': f"Error updating internal state: {str(e)}"
        }
        print(f"[TOOL] update_tracking_data error: {result['error']}")
        return result

# Backward compatibility wrapper
# Keeping the same parameters/signature
def update_internal_state(property_updates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return update_tracking_data(property_updates)

def create_root_explainer_card(
    title: str,
    color: str,
    type: str = 'root_explainer',
    incomingConnections: List[str] = None,
    explainer_nodes: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a root card that encapsulates a main research topic
    
    Args:
        title: The title of the research topic
        color: The color to assign to the card
    
    Returns:
        Dictionary containing the created card information
    """
    try:
        # Generate a unique card ID
        import time
        card_id = f"card_{int(time.time())}"
        
        card_data = {
            'id': card_id,
            'title': title,
            'color': color,
            'type': type,
            'incomingConnections': incomingConnections or [],
            'created_at': requests.get('http://worldtimeapi.org/api/timezone/Etc/UTC').json().get('datetime', 'unknown') if hasattr(requests, 'get') else 'unknown',
            'body_items': [],
            'metadata': {
                'paper_count': 0,
                'last_updated': requests.get('http://worldtimeapi.org/api/timezone/Etc/UTC').json().get('datetime', 'unknown') if hasattr(requests, 'get') else 'unknown'
            }
        }
        # If explainer_nodes is provided (passed by the orchestration loop), update it in-place
        if explainer_nodes is not None:
            try:
                # Ensure it's a list
                if not isinstance(explainer_nodes, list):
                    raise ValueError("explainer_nodes must be a list of nodes")
                # Append the new root card node
                explainer_nodes.append({
                    'id': card_id,
                    'type': type,
                    'title': title,
                    'color': color,
                    'incomingConnections': incomingConnections or [],
                    'body_items': []
                })
            except Exception:
                # Do not fail the tool; keep returning card_data
                pass
        
        result = {
            'success': True,
            'card': card_data,
            'message': f"Successfully created root explainer card: {title}"
        }
        print(f"[TOOL] create_root_explainer_card completed: Created card '{title}' with ID {card_id}")
        return result
        
    except Exception as e:
        result = {
            'success': False,
            'error': f"Error creating root explainer card: {str(e)}"
        }
        print(f"[TOOL] create_root_explainer_card error: {result['error']}")
        return result

def add_card_body_item(card_id: str, title: str, desc: str, external_link: str, explainer_nodes: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Add an item to track for a card body (typically a paper related to the research topic)
    
    Args:
        card_id: The ID of the card to add the item to
        title: The title of the item (e.g., paper title)
        desc: Short description of the item
        external_link: Link to the external resource (e.g., paper URL)
    
    Returns:
        Dictionary indicating success and the added item information
    """
    try:
        import time
        item_id = f"item_{int(time.time())}"
        
        body_item = {
            'id': item_id,
            'title': title,
            'description': desc,
            'external_link': external_link,
            'added_at': requests.get('http://worldtimeapi.org/api/timezone/Etc/UTC').json().get('datetime', 'unknown') if hasattr(requests, 'get') else 'unknown',
            'type': 'paper_reference'
        }
        # If explainer_nodes is provided, try to attach this body item to the matching card
        if explainer_nodes is not None:
            try:
                for node in explainer_nodes:
                    if isinstance(node, dict) and node.get('id') == card_id and node.get('type') in ('card', 'root_explainer'):
                        node.setdefault('body_items', [])
                        node['body_items'].append(body_item)
                        break
            except Exception:
                # Ignore issues mutating explainer_nodes
                pass
        
        # In a real implementation, this would add to the actual card's body_items array
        # For now, we'll return the item that would be added
        
        result = {
            'success': True,
            'card_id': card_id,
            'added_item': body_item,
            'message': f"Successfully added item '{title}' to card {card_id}"
        }
        print(f"[TOOL] add_card_body_item completed: Added item '{title}' to card {card_id}")
        return result
        
    except Exception as e:
        result = {
            'success': False,
            'error': f"Error adding card body item: {str(e)}",
            'card_id': card_id
        }
        print(f"[TOOL] add_card_body_item error: {result['error']}")
        return result

# Available tools mapping
AVAILABLE_TOOLS = {
    'search_papers': search_papers,
    'read_full_paper_content': read_full_paper_content,
    'search_papers_by_topic': search_papers_by_topic,
    'update_tracking_data': update_tracking_data,
    'update_internal_state': update_tracking_data,
    'create_root_explainer_card': create_root_explainer_card,
    'add_card_body_item': add_card_body_item,
    # 'analyze_research_gaps': analyze_research_gaps,
    # 'read_paper_pdf_content': read_paper_pdf_content
}

def execute_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
    """
    Execute a tool by name with provided arguments

    Args:
        tool_name: Name of the tool to execute
        **kwargs: Arguments to pass to the tool

    Returns:
        Tool execution result
    """
    if tool_name in AVAILABLE_TOOLS:
        try:
            return AVAILABLE_TOOLS[tool_name](**kwargs)
        except Exception as e:
            return {
                'success': False,
                'error': f"Error executing tool {tool_name}: {str(e)}"
            }
    else:
        return {
            'success': False,
            'error': f"Tool {tool_name} not found. Available tools: {list(AVAILABLE_TOOLS.keys())}"
        }
