"""
Tools for the Stella assistant
"""

# ---------------------------------------------------------------------------
# Common reusable schema definitions
# ---------------------------------------------------------------------------

# Reusable JSON-schema fragment for a list of tag objects
TAG_LIST_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "uniqueid": {"type": "string", "description": "Unique identifier for the tag"},
            "name": {"type": "string", "description": "Human-readable name of the tag"},
            "color": {"type": "string", "description": "Hex or css color representing the tag"},
        },
        "required": ["uniqueid", "name", "color"],
        "additionalProperties": False,
    },
    "description": "Optional list of tag objects. Each tag must include uniqueid, name, and color.",
    "default": [],
}

# Find notes that are similar to the query
similarity_search_user_notes_tool = {
	"type": "function",
    "function": {
      "name": "search_user_notes_similarity",
      "description": "Only if the user asks you to search, OR (if there is no information in the current notes and you don't have general information on this), then search the user's notes using similarity search.\\n This finds notes that are similar based on meaning.",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "The query to search for"
          },
          "similarity_setting": {
            "type": "number",
            "enum": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            "description": "How similar the results should be to the query. 0.1 is the least similar, 0.5 being decently similar, and 1.0 is almost exactly similar."
          }
        },
        "required": ["query"],
		"additionalProperties": False
      }
    }
}

# Find notes via keyword search
keyword_search_user_notes_tool = {
	"type": "function",
    "function": {
      "name": "search_user_notes_keyword",
      "description": "Search the user's notes using keyword search (i.e. find notes that contain the keyword in the title versus by similarity)",
      "parameters": {
        "type": "object",
        "properties": {
          "keyword": {
            "type": "string",
            "description": "The keyword to search for"
          },
        },
        "required": ["keyword"],
		"additionalProperties": False
      }
    }
}

get_website_url_content_tool = {
    "type": "function",
    "function": {
        "name": "get_website_url_content",
        "description": "Read a website by getting the content of a website using the site's url (i.e. scrapes the website for text)",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the webpage to scrape"
                },
                "ignore_links": {
                    "type": "boolean",
                    "description": "Whether to ignore links in the output text",
                    "default": False
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum length of the returned text. If not provided, returns full text",
                    "default": None
                }
            },
            "required": ["url"],
            "additionalProperties": False
        }
    }
}

# Google search tool
google_search_tool = {
    "type": "function",
    "function": {
        "name": "google_search",
        "description": "Searches for potential websites to browse using Google.\\nAs opposed to searching the user's notes, this is used to find websites to browse to supplement yourself with the latest knowledge.\\nBefore browsing websites, this is done to find websites..",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to execute"
                },
                "results": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 5
                },
                "exactTerms": {
                    "type": "string",
                    "description": "Words or phrases that should appear exactly in the search results",
                    "default": None
                },
                "excludeTerms": {
                    "type": "string",
                    "description": "Words or phrases that should not appear in the search results",
                    "default": None
                }
            },
            "required": ["query"],
            "additionalProperties": False
        }
    }
}

# -------------------------------
# NOTE OPERATIONS (create, edit, delete, connect)
# -------------------------------

# Create a new note in the user's graph
create_note_tool = {
    "type": "function",
    "function": {
        "name": "create_note",
        "description": "Create a brand-new note in the user's knowledge base graph.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The title of the note to create. Should be specific and capture a single atomic idea."
                },
                "content": {
                    "type": "string",
                    "description": "The full body/content of the note."
                },
                "tags": {
                    **TAG_LIST_SCHEMA
                }
            },
            "required": ["title", "content"],
            "additionalProperties": False
        }
    }
}

# --- NOTE EDITING TOOLS (specialised) ---

# 1. Edit the note title only
edit_note_title_tool = {
    "type": "function",
    "function": {
        "name": "edit_note_title",
        "description": "Update the title of an existing note. Use this when ONLY the title needs to change.",
        "parameters": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "Unique identifier of the note to edit."
                },
                "new_title": {
                    "type": "string",
                    "description": "The new title to set for the note."
                }
            },
            "required": ["note_id", "new_title"],
            "additionalProperties": False
        }
    }
}

# 2. Add tags to a note
add_tags_to_note_tool = {
    "type": "function",
    "function": {
        "name": "edit_note_tags",
        "description": "Add new tags to an existing note. Return only the new list of tags to add, not the existing tags.",
        "parameters": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "Unique identifier of the note to edit."
                },
                "tags_to_add": {
                    **TAG_LIST_SCHEMA
                }
            },
            "required": ["note_id", "tags_to_add"],
            "additionalProperties": False
        }
    }
}

# 3. Remove tags from a note
remove_tags_from_note_tool = {
    "type": "function",
    "function": {
        "name": "remove_tags_from_note",
        "description": "Remove tags from an existing note. Return only the list of tags to remove from the existing note.",
		"parameters": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "Unique identifier of the note to edit."
                },
                "tags_to_remove": {
                    **TAG_LIST_SCHEMA
                }
            },
            "required": ["note_id", "tags_to_remove"],
            "additionalProperties": False
        }
    }
}

# 3. Delete a specific part of the note content
delete_part_of_note_content_tool = {
    "type": "function",
    "function": {
        "name": "delete_part_of_note_content",
        "description": "Remove an exact substring from a note's content.",
        "parameters": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "Unique identifier of the note to edit."
                },
                "content_part_to_delete": {
                    "type": "string",
                    "description": "The exact, continuous text from the content to delete."
                }
            },
            "required": ["note_id", "content_part_to_delete"],
            "additionalProperties": False
        }
    }
}

# 4. Replace a specific part of the note content with new text
replace_part_of_note_content_tool = {
    "type": "function",
    "function": {
        "name": "replace_part_of_note_content",
        "description": "Replace an exact substring in a note's content with new text.",
        "parameters": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "Unique identifier of the note to edit."
                },
                "content_part_to_replace": {
                    "type": "string",
                    "description": "The exact, continuous text in the content to replace."
                },
                "replacement_content": {
                    "type": "string",
                    "description": "The new text that will replace the specified content part."
                }
            },
            "required": ["note_id", "content_part_to_replace", "replacement_content"],
            "additionalProperties": False
        }
    }
}

# 5. Append new content to the note
add_part_to_note_content_tool = {
    "type": "function",
    "function": {
        "name": "add_part_to_note_content",
        "description": "Append new text to the end of a note's content.",
        "parameters": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "Unique identifier of the note to edit."
                },
                "content_to_add": {
                    "type": "string",
                    "description": "The text to append to the note's content."
                }
            },
            "required": ["note_id", "content_to_add"],
            "additionalProperties": False
        }
    }
}

# Delete a note
delete_note_tool = {
    "type": "function",
    "function": {
        "name": "delete_note",
        "description": "Delete a note from the user's knowledge base given its id.",
        "parameters": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "The unique identifier of the note to delete."
                }
            },
            "required": ["note_id"],
            "additionalProperties": False
        }
    }
}

# Create a connection (edge) between two notes
create_connection_tool = {
    "type": "function",
    "function": {
        "name": "create_connection",
        "description": "Create a directed connection (edge) from one note to another.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_note_id": {
                    "type": "string",
                    "description": "ID (or exact title if ID not yet known) of the start/source note."
                },
                "end_note_id": {
                    "type": "string",
                    "description": "ID (or exact title if ID not yet known) of the end/target note."
                }
            },
            "required": ["start_note_id", "end_note_id"],
            "additionalProperties": False
        }
    }
}

# Delete an existing connection between two notes
delete_connection_tool = {
    "type": "function",
    "function": {
        "name": "delete_connection",
        "description": "Delete a directed connection (edge) between two existing notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_note_id": {
                    "type": "string",
                    "description": "ID of the start/source note of the connection."
                },
                "end_note_id": {
                    "type": "string",
                    "description": "ID of the end/target note of the connection."
                }
            },
            "required": ["start_note_id", "end_note_id"],
            "additionalProperties": False
        }
    }
}


# Conversing tools

converse_with_user_tool = {
    "type": "function",
    "function": {
        "name": "converse_with_user",
        "description": "Converse with the user. This is used to answer questions and provide information.",
		"parameters": {
			"type": "object",
			"properties": {
				"long_message": {
					"type": "string",
					"description": "Multiple sentences message to send to the user. Detailed using as much information as much as you know to help the user with their specifc request."
				}
			}
		}
    }
}
