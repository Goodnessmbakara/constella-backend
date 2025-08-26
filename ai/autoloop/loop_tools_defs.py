search_papers_tool = {
    "type": "function",
    "function": {
        "name": "search_papers",
        "strict": True,
        "description": "Search for academic papers using Semantic Scholar API",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of papers to return",
                    "default": 10
                }
            },
            "required": [
                "query"
            ],
            "additionalProperties": False
        }
    }
}

read_full_paper_content_tool = {
    "type": "function",
    "function": {
        "name": "read_full_paper_content",
        "strict": True,
        "description": "Read the full content of a paper from its URL",
        "parameters": {
            "type": "object",
            "properties": {
                "paper_url": {
                    "type": "string",
                    "description": "URL of the paper to read"
                }
            },
            "required": [
                "paper_url"
            ],
            "additionalProperties": False
        }
    }
}

search_papers_by_topic_tool = {
    "type": "function",
    "function": {
        "name": "search_papers_by_topic",
        "strict": True,
        "description": "Search for papers by a specific research topic",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Research topic to search for"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of papers to return",
                    "default": 5
                }
            },
            "required": [
                "topic"
            ],
            "additionalProperties": False
        }
    }
}

update_tracking_data_tool = {
    "type": "function",
    "function": {
        "name": "update_tracking_data",
        "strict": True,
        "description": "Update tracking data properties with different update types. This tool MUST be called after each turn of the loop to persist internal tracking data.",
        "parameters": {
            "type": "object",
            "properties": {
                "property_updates": {
                    "type": "object",
                    "description": "Dictionary mapping property names to update specifications. Each update spec should have 'typeOfUpdate' ('CHANGE_VALUE', 'ARRAY_PUSH_VALUE', or 'ARRAY_REMOVE_VALUE') and 'updateValue'",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "typeOfUpdate": {
                                "type": "string",
                                "enum": ["CHANGE_VALUE", "ARRAY_PUSH_VALUE", "ARRAY_REMOVE_VALUE"]
                            },
                            "updateValue": {
                                "description": "The value to use for the update"
                            }
                        },
                        "required": ["typeOfUpdate", "updateValue"]
                    }
                }
            },
            "required": [
                "property_updates"
            ],
            "additionalProperties": False
        }
    }
}

create_root_explainer_card_tool = {
    "type": "function",
    "function": {
        "name": "create_root_explainer_card",
        "strict": True,
        "description": "Create a root card that encapsulates a main research topic",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the root explainer card"
                },
                "color": {
                    "type": "string",
                    "description": "Color for the card"
                },
                "type": {
                    "type": "string",
                    "description": "Type of the explainer card (e.g., 'root_explainer')"
                },
                "incomingConnections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "other root cards that point towards this topic / root card\n If there are existing root explaienr cards, this should always be there"
                }
            },
            "required": [
                "title",
                "color"
            ],
            "additionalProperties": False
        }
    }
}

add_card_body_item_tool = {
    "type": "function",
    "function": {
        "name": "add_card_body_item",
        "strict": True,
        "description": "Add an item to track for a card body (typically a paper related to the research topic)",
        "parameters": {
            "type": "object",
            "properties": {
                "card_id": {
                    "type": "string",
                    "description": "The ID of the card to add the item to"
                },
                "title": {
                    "type": "string",
                    "description": "The title of the item (e.g., paper title)"
                },
                "desc": {
                    "type": "string",
                    "description": "Short description of the item"
                },
                "external_link": {
                    "type": "string",
                    "description": "Link to the external resource (e.g., paper URL)"
                }
            },
            "required": [
                "card_id",
                "title",
                "desc",
                "external_link"
            ],
            "additionalProperties": False
        }
    }
}

def get_autoloop_tools():
    """
    Return the list of tools available to the autoloop assistant.
    """
    return [
        search_papers_tool,
        read_full_paper_content_tool,
        search_papers_by_topic_tool,
        update_tracking_data_tool,
        create_root_explainer_card_tool,
        add_card_body_item_tool
    ]
