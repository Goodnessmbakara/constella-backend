#!/usr/bin/env python3
"""
Test script for autoloop tools and research functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.autoloop.tools import (
    search_papers,
    read_full_paper_content,
    search_papers_by_topic,
    analyze_research_gaps,
    execute_tool,
    read_paper_pdf_content
)

def test_search_papers():
    """Test paper search functionality"""
    print("Testing search_papers...")

    query = "machine learning optimization"
    result = search_papers(query, max_results=3)

    print(f"Search query: {query}")
    print(f"Success: {result['success']}")

    if result['success']:
        print(f"Total results: {result['total_results']}")
        print(f"Papers returned: {len(result['papers'])}")

        for i, paper in enumerate(result['papers'][:2]):
            print(f"\nPaper {i+1}:")
            print(f"  Title: {paper['title']}")
            print(f"  Authors: {', '.join(paper['authors'][:3])}")
            print(f"  Year: {paper['year']}")
            print(f"  Citations: {paper['citation_count']}")
    else:
        print(f"Error: {result['error']}")

    print("-" * 80)

def test_search_papers_by_topic():
    """Test topic-specific paper search"""
    print("Testing search_papers_by_topic...")

    topic = "reinforcement learning"
    result = search_papers_by_topic(topic, max_results=3)

    print(f"Topic: {topic}")
    print(f"Success: {result['success']}")

    if result['success']:
        print(f"Papers found: {len(result['papers'])}")

        for i, paper in enumerate(result['papers'][:2]):
            print(f"\nPaper {i+1}:")
            print(f"  Title: {paper['title']}")
            print(f"  Authors: {', '.join(paper['authors'][:2])}")
            print(f"  Abstract preview: {paper['abstract'][:100]}...")
    else:
        print(f"Error: {result['error']}")

    print("-" * 80)

def test_analyze_research_gaps():
    """Test research gap analysis"""
    print("Testing analyze_research_gaps...")

    # Mock papers data for testing
    mock_papers = [
        {
            'title': 'Deep Learning Approaches in Computer Vision',
            'authors': ['Smith, J.', 'Doe, A.'],
            'abstract': 'This paper presents deep learning methodologies for computer vision tasks. However, there are limitations in handling edge cases and future work should focus on reinforcement learning applications.'
        },
        {
            'title': 'Machine Learning Optimization Techniques',
            'authors': ['Johnson, B.', 'Williams, C.'],
            'abstract': 'We explore various machine learning optimization approaches. The main challenge is computational complexity and further research is needed in neural network architectures.'
        },
        {
            'title': 'Neural Network Applications in NLP',
            'authors': ['Brown, D.', 'Davis, E.'],
            'abstract': 'This work demonstrates neural network applications in natural language processing. Limitations include data requirements and the gap in understanding model interpretability.'
        }
    ]

    topic = "machine learning"
    result = analyze_research_gaps(mock_papers, topic)

    print(f"Topic analyzed: {topic}")
    print(f"Success: {result['success']}")

    if result['success']:
        print(f"Identified gaps: {len(result['identified_gaps'])}")
        print(f"Common themes: {result['common_themes']}")
        print(f"Limitations found: {len(result['limitations_found'])}")

        print("\nIdentified Research Gaps:")
        for i, gap in enumerate(result['identified_gaps'][:3]):
            print(f"  Gap {i+1}: {gap['title']}")
            print(f"    ID: {gap['id']}")
            print(f"    Connections: {', '.join(gap['connections'])}")
    else:
        print(f"Error: {result['error']}")

    print("-" * 80)

def test_execute_tool():
    """Test tool execution framework"""
    print("Testing execute_tool...")

    # Test valid tool
    result = execute_tool('search_papers', query='deep learning', max_results=2)
    print(f"Tool execution success: {result.get('success', False)}")

    if result.get('success'):
        print(f"Papers found: {len(result.get('papers', []))}")

    # Test invalid tool
    result = execute_tool('nonexistent_tool', query='test')
    print(f"Invalid tool handled: {not result.get('success', True)}")
    print(f"Error message: {result.get('error', 'No error')}")

    print("-" * 80)

def test_read_paper_pdf():
    """Test PDF reading functionality"""
    print("Testing read_paper_pdf_content...")

    # Test with a known arXiv paper PDF URL
    test_pdf_url = "https://arxiv.org/pdf/2301.07041.pdf"  # Example arXiv paper
    result = read_paper_pdf_content(test_pdf_url)

    print(f"PDF URL: {test_pdf_url}")
    print(f"Success: {result['success']}")

    if result['success']:
        print(f"Pages: {result['num_pages']}")
        print(f"Text length: {result['text_length']}")
        print(f"Research contributions found: {len(result['research_contributions'])}")
        print(f"Research gaps found: {len(result['research_gaps'])}")

        print("\nSample contributions:")
        for i, contrib in enumerate(result['research_contributions'][:2]):
            print(f"  {i+1}. {contrib[:100]}...")

        print("\nSample gaps:")
        for i, gap in enumerate(result['research_gaps'][:2]):
            print(f"  {i+1}. {gap[:100]}...")
    else:
        print(f"Error: {result['error']}")

    print("-" * 80)

def test_read_full_paper_enhanced():
    """Test enhanced read_full_paper_content with PDF extraction"""
    print("Testing enhanced read_full_paper_content...")

    # Test with a paper that might have PDF access
    # Using a random paper ID - replace with actual ID for real testing
    paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"  # Example paper ID
    result = read_full_paper_content(paper_id)

    print(f"Paper ID: {paper_id}")
    print(f"Success: {result['success']}")

    if result['success']:
        print(f"Title: {result['title']}")
        print(f"Full text available: {result.get('full_text_available', False)}")
        print(f"Research contributions: {len(result.get('research_contributions', []))}")
        print(f"Research gaps: {len(result.get('research_gaps', []))}")

        if result.get('research_contributions'):
            print("\nContributions from full text:")
            for i, contrib in enumerate(result['research_contributions'][:2]):
                print(f"  {i+1}. {contrib[:100]}...")

        if result.get('research_gaps'):
            print("\nGaps from full text:")
            for i, gap in enumerate(result['research_gaps'][:2]):
                print(f"  {i+1}. {gap[:100]}...")
    else:
        print(f"Error: {result['error']}")

    print("-" * 80)

def test_full_research_workflow():
    """Test a complete research workflow"""
    print("Testing full research workflow...")

    topic = "neural networks"

    # Step 1: Search for papers
    print(f"Step 1: Searching papers for '{topic}'...")
    papers_result = search_papers_by_topic(topic, max_results=3)

    if not papers_result['success']:
        print(f"Failed to search papers: {papers_result['error']}")
        return

    print(f"Found {len(papers_result['papers'])} papers")

    # Step 2: Analyze gaps
    print(f"Step 2: Analyzing research gaps...")
    gap_analysis = analyze_research_gaps(papers_result['papers'], topic)

    if not gap_analysis['success']:
        print(f"Failed to analyze gaps: {gap_analysis['error']}")
        return

    print(f"Identified {len(gap_analysis['identified_gaps'])} research gaps")

    # Step 3: Display results in the required format
    print("\nResearch Workflow Results:")
    print("=" * 50)

    # Key Specific Topics
    topic_data = {
        'title': topic,
        'id': 'topic_1',
        'papers': papers_result['papers']
    }

    print(f"Topic: {topic_data['title']}")
    print(f"Papers analyzed: {len(topic_data['papers'])}")

    # Key Gaps
    print(f"\nResearch Gaps Identified:")
    for gap in gap_analysis['identified_gaps'][:5]:
        print(f"  - {gap['title']} (ID: {gap['id']})")
        print(f"    Connections: {', '.join(gap['connections'])}")

    print("-" * 80)

def main():
    """Run all tests"""
    print("Starting Autoloop Tools Test Suite")
    print("=" * 80)

    try:
        test_search_papers()
        test_search_papers_by_topic()
        test_analyze_research_gaps()
        test_execute_tool()
        test_read_paper_pdf()
        test_read_full_paper_enhanced()
        test_full_research_workflow()

        print("All tests completed!")

    except Exception as e:
        print(f"Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
