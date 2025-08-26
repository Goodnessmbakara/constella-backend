# Aury MBTI Analysis

This module provides MBTI personality analysis based on text message data, converted from the original Swift iOS implementation.

## Overview

The Aury analyzer takes a collection of text messages and analyzes the user's texting patterns to determine their MBTI personality type, along with fun insights about their communication style.

## API Endpoints

### POST `/aury/analyze`

Analyzes message data and returns a complete MBTI personality profile.

**Request Body:**

```json
{
    "messages": [
        {
            "text": "Hey, how's it going?",
            "contact": "John Doe",
            "timestamp": "2024-01-15T10:30:00Z",
            "is_from_me": true
        },
        {
            "text": "Good! Just working on some projects",
            "contact": "John Doe",
            "timestamp": "2024-01-15T10:32:00Z",
            "is_from_me": false
        }
    ]
}
```

**Response:**

```json
{
    "success": true,
    "profile": {
        "mbti_type": "ENFP",
        "profile_emoji": "🎭",
        "aura_name": "Electric Chaos",
        "aura_hex_color": "#ff6b6b",
        "cool_one_liner": "Enthusiasm with a side of overthinking",
        "personality_description": "You're the friend who sends 47 texts in a row and somehow makes it endearing.",
        "description": "Classic ENFP vibes - you text like you're narrating your entire life story, complete with dramatic plot twists.",
        "texting_pros": [
            "Always keeps conversations alive",
            "Genuinely interested in others",
            "Great at emotional support",
            "Never boring to text with"
        ],
        "texting_cons": [
            "Sends way too many messages at once",
            "Gets distracted mid-conversation",
            "Overshares personal details",
            "Takes forever to get to the point"
        ],
        "top_contacts": ["John Doe", "Jane Smith", "Mom"],
        "tips": [
            "Try consolidating your thoughts into fewer messages",
            "Ask more questions to balance the conversation",
            "Give people time to respond before sending follow-ups",
            "Practice being more concise with important info"
        ],
        "roast_summary": "You text like you're writing a memoir, complete with emotional commentary and random tangents. Your friends probably have a separate notification sound just for you because they know they're about to get a novel's worth of updates about your day."
    },
    "error": null
}
```

### POST `/aury/validate-messages`

Validates message format without running the expensive analysis.

**Request Body:** Same as `/analyze`

**Response:**

```json
{
    "valid": true,
    "message_count": 150,
    "user_message_count": 75,
    "valid_conversations": 8,
    "total_contacts": 12,
    "validation_sample": [
        {
            "message_index": 0,
            "valid": true,
            "missing_fields": [],
            "has_text": true,
            "contact": "John Doe"
        }
    ],
    "top_contacts": [
        ["John Doe", 45],
        ["Jane Smith", 32],
        ["Mom", 28]
    ]
}
```

### GET `/aury/health`

Health check endpoint.

**Response:**

```json
{
    "status": "healthy",
    "service": "aury-analysis"
}
```

## Message Data Format

Each message should include:

-   `text` (string): The actual message content
-   `contact` (string): Name or identifier of the contact
-   `timestamp` (string): ISO timestamp of when the message was sent
-   `is_from_me` (boolean): Whether the message was sent by the user being analyzed

## Analysis Requirements

For optimal analysis:

-   Minimum 100 messages recommended
-   At least 5 different contacts with substantial conversation history
-   Mix of different conversation types (casual, work, family, etc.)
-   Recent message data (within last 6-12 months) preferred

## Technical Details

-   Uses OpenAI's structured output for consistent response formatting
-   Implements conversation filtering to focus on meaningful exchanges
-   Analyzes conversation dynamics, response patterns, and communication style
-   Provides both humorous and insightful personality assessment

## Error Handling

The API returns errors gracefully in the response object rather than throwing HTTP exceptions, allowing clients to handle failures appropriately.

Common error scenarios:

-   No messages provided
-   Invalid message format
-   OpenAI API errors
-   Insufficient conversation data

## Example Usage

```python
import httpx

# Prepare message data
messages = [
    {
        "text": "Hey! How was your day?",
        "contact": "Best Friend",
        "timestamp": "2024-01-15T18:30:00Z",
        "is_from_me": True
    },
    # ... more messages
]

# Make request
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/aury/analyze",
        json={"messages": messages}
    )

    result = response.json()
    if result["success"]:
        profile = result["profile"]
        print(f"MBTI Type: {profile['mbti_type']}")
        print(f"Personality: {profile['personality_description']}")
    else:
        print(f"Error: {result['error']}")
```
