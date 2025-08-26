from typing import List, Dict, Any, Tuple
from pydantic import BaseModel
from collections import defaultdict, Counter
import json
import traceback
from datetime import datetime

from ai.ai_api import openai_structured_output, create_json_schema


class MBTIProfile(BaseModel):
    """MBTI Profile model matching the Swift structure"""
    mbti_type: str
    profile_emoji: str
    aura_name: str
    aura_hex_color: str
    cool_one_liner: str
    personality_description: str
    description: str
    texting_pros: List[str]
    texting_cons: List[str]
    top_contacts: List[str]
    tips: List[str]
    roast_summary: str


class MessageData(BaseModel):
    """Message data structure for analysis"""
    text: str
    contact: str
    timestamp: str
    is_from_me: bool


def calculate_contact_frequency(messages_data: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
    """Calculate contact frequency from message data"""
    frequency = defaultdict(int)
    
    for message in messages_data:
        contact = message.get("contact", "Unknown")
        if contact != "Unknown":
            frequency[contact] += 1
    
    return sorted(frequency.items(), key=lambda x: x[1], reverse=True)


def group_messages_by_contact(messages_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group messages by contact and sort by timestamp"""
    grouped = defaultdict(list)
    
    for message in messages_data:
        contact = message.get("contact", "Unknown")
        if contact != "Unknown":
            grouped[contact].append(message)
    
    # Sort messages within each contact by timestamp
    for contact in grouped:
        grouped[contact].sort(key=lambda msg: msg.get("timestamp", ""))
    
    return dict(grouped)


def format_conversations_for_analysis(conversations: Dict[str, List[Dict[str, Any]]]) -> str:
    """Format conversations for AI analysis similar to the Swift implementation"""
    formatted_conversations = []
    conversation_number = 1
    processed_count = 0
    skipped_count = 0
    
    # Sort contacts by message count
    sorted_contacts = sorted(conversations.items(), key=lambda x: len(x[1]), reverse=True)
    
    print(f"📊 CONVERSATION ANALYSIS: Looking for 50 quality conversations from {len(sorted_contacts)} total contacts")
    
    for contact, messages in sorted_contacts:
        # Skip conversations with less than 10 messages
        if len(messages) < 10:
            skipped_count += 1
            print(f"  ⏭️ Skipping {contact}: Only {len(messages)} messages (< 10)")
            continue
        
        # Check if user has sent at least one message in this conversation
        user_messages = [msg for msg in messages if msg.get("is_from_me", False)]
        if not user_messages:
            skipped_count += 1
            print(f"  ⏭️ Skipping {contact}: User never sent a message")
            continue
        
        conversation_text = f"Convo {conversation_number}: {contact} ({len(messages)} total messages, {len(user_messages)} from user)\n"
        
        # Take recent messages from this conversation (last 100 messages max)
        recent_messages = messages[-100:]
        
        print(f"  ✅ {contact}: Using {len(recent_messages)} recent messages ({len(user_messages)} user messages)")
        
        for message in recent_messages:
            is_from_user = message.get("is_from_me", False)
            text = message.get("text", "")
            sender = "USER" if is_from_user else contact.upper()
            
            # Only include non-empty messages
            if text.strip():
                conversation_text += f"{sender}: {text}\n"
        
        formatted_conversations.append(conversation_text)
        conversation_number += 1
        processed_count += 1
        
        # Stop at 50 valid conversations
        if processed_count >= 50:
            break
    
    print(f"✅ TOTAL CONVERSATIONS FORMATTED: {len(formatted_conversations)}")
    print(f"⏭️ CONVERSATIONS SKIPPED: {skipped_count} (too few messages or no user messages)")
    
    total_message_count = sum(conversation.count('\n') for conversation in formatted_conversations)
    print(f"📝 ESTIMATED TOTAL MESSAGE LINES: {total_message_count}")
    
    return "\n***\n\n".join(formatted_conversations)


def create_mbti_analysis_prompt(messages_data: List[Dict[str, Any]]) -> str:
    """Create the MBTI analysis prompt from message data"""
    contact_frequency = calculate_contact_frequency(messages_data)
    user_sent_messages = [msg for msg in messages_data if msg.get("is_from_me", False)]
    
    # Group messages by contact for conversation analysis
    conversations_by_contact = group_messages_by_contact(messages_data)
    conversation_context = format_conversations_for_analysis(conversations_by_contact)
    
    top_contacts_str = ", ".join([f"{contact}: {count} messages" for contact, count in contact_frequency[:10]])
    
    return f"""📱 TEXTING PERSONALITY ANALYSIS: Time to call you out on your digital habits! I've been stalking your messages (with permission, obviously) and oh boy, do I have some thoughts about how you text.

📊 YOUR DIGITAL FOOTPRINT (THE EVIDENCE):
- Total messages I analyzed: {len(messages_data)} (yes, I read them all)
- Messages YOU actually sent: {len(user_sent_messages)} 
- Your most texted people: {top_contacts_str}

💬 YOUR ACTUAL CONVERSATIONS (the receipts):
{conversation_context}

⚠️ IMPORTANT: Only analyze conversations where YOU actually sent messages. Ignore any conversations where you were just getting spammed but never replied - those don't count for personality analysis.

🔍 WHAT I'M LOOKING FOR IN YOUR TEXTING:

HOW YOU COMMUNICATE IN DIFFERENT CONTEXTS:
- Work texts (are you all professional or do you slip in some personality?)
- Personal conversations (friends, family, dating - where you let your guard down)
- Group chats (are you the comedian, the organizer, or the lurker?)
- Crisis moments (how do you handle drama or support people?)
- Basic coordination (planning, scheduling - are you efficient or all over the place?)

YOUR TEXTING PATTERNS THAT GIVE YOU AWAY:
- When do you text? (3am thoughts or strictly business hours?)
- How long are your messages? (novel writer or one-word responder?)
- Do you text differently with different people?
- How do you handle emotions through text?
- Are you a conversation starter or do you wait for others to reach out?
- Do you leave people on read or respond to everything?

MBTI TYPE POSSIBILITIES - I'll figure out which one fits YOU:
ANALYSTS: INTJ (the strategic loner), INTP (the curious overthinker), ENTJ (the take-charge type), ENTP (the idea machine)
DIPLOMATS: INFJ (the mysterious deep one), INFP (the sensitive dreamer), ENFJ (the people pleaser), ENFP (the enthusiastic chaos)
SENTINELS: ISTJ (the reliable one), ISFJ (the caring worrier), ESTJ (the organized boss), ESFJ (the social connector)
EXPLORERS: ISTP (the chill problem-solver), ISFP (the quiet creative), ESTP (the spontaneous one), ESFP (the life of the party)

I'm not picking from a textbook - I'm reading YOUR specific patterns.
Consider the latest MBTI research and the latest MBTI type descriptions and use them to help you determine the best MBTI type for you.

CONVERSATION DYNAMICS I'M ANALYZING:
- Do you adapt your texting style to match who you're talking to?
- Are you the one starting conversations or always responding?
- How do you handle different types of relationships through text?
- What's your response timing like with different people?
- Do you show different sides of yourself in different conversations?

YOUR ATTACHMENT STYLE THROUGH TEXTING:
- Are you secure and balanced, or do you get anxious when people don't respond?
- Do you seek validation through your messages?
- How do you handle conflict or tension in text conversations?
- Can you actually express emotions through text or do you keep it surface level?

REQUIREMENTS (TIME TO CALL YOU OUT):
- mbtiType: Which of the 16 types matches YOUR specific texting patterns
- profileEmoji: One emoji that captures your texting personality
- auraName: A cool 2-3 word aura name that captures your vibe (like "Midnight Storm", "Golden Breeze", "Electric Chaos")
- auraHexColor: A hex color code (including #) that represents your aura energy
- coolOneLiner: A witty one-liner that captures your texting essence in 5-8 words
- personalityDescription: 1-2 sentences calling out your texting personality directly
- description: 2-3 sentences playfully roasting your MBTI type's texting habits
- textingPros: 3-4 things you're actually good at (I'll give you credit where it's due)
- textingCons: 3-4 ways your texting probably annoys people (sorry not sorry)
- topContacts: Your top 3 most texted people
- tips: 3-4 suggestions for improving your texting game
- roastSummary: A fun paragraph that calls out your texting personality with humor but accuracy

TIME TO GET REAL. I'm going to be accurate but make it fun - like a friend who knows your texting habits way too well."""


def analyze_mbti_from_messages(messages_data: List[Dict[str, Any]]) -> MBTIProfile:
    """
    Analyze MBTI personality from message data using OpenAI structured output
    """
    try:
        print(f"\n🔍 DEBUG: Data being sent to OpenAI:")
        print(f"📊 Total messages: {len(messages_data)}")
        print(f"📱 Sample message data:")
        for i, message in enumerate(messages_data[:5]):
            print(f"  {i + 1}. {message}")
        
        # Create the analysis prompt
        prompt = create_mbti_analysis_prompt(messages_data)
        
        print(f"📝 DEBUG: Full prompt being sent:")
        print(prompt)
        print("\n" + "=" * 50 + "\n")
        
        # Define the JSON schema for structured output
        schema = create_json_schema(
            name="mbti_analysis",
            properties={
                "mbtiType": {
                    "type": "string",
                    "description": "The MBTI personality type (e.g., ENFP, INTJ)"
                },
                "profileEmoji": {
                    "type": "string",
                    "description": "A single emoji that captures their texting personality"
                },
                "auraName": {
                    "type": "string",
                    "description": "A cool 2-3 word aura name that captures their vibe (e.g., 'Midnight Storm', 'Golden Breeze', 'Electric Chaos')"
                },
                "auraHexColor": {
                    "type": "string",
                    "description": "A hex color code (including #) that represents their aura energy"
                },
                "coolOneLiner": {
                    "type": "string",
                    "description": "A witty one-liner that captures their texting essence in 5-8 words"
                },
                "personalityDescription": {
                    "type": "string",
                    "description": "A fun 1-2 sentence description that calls out their texting personality directly"
                },
                "description": {
                    "type": "string",
                    "description": "A playful description that teases their MBTI type's texting habits"
                },
                "textingPros": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of texting strengths with playful compliments"
                },
                "textingCons": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of texting habits that probably annoy people, described with humor"
                },
                "topContacts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of their most texted people"
                },
                "tips": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of friendly suggestions for improving their texting game"
                },
                "roastSummary": {
                    "type": "string",
                    "description": "A fun paragraph that playfully calls out their texting personality with humor and accuracy"
                }
            },
            required_fields=["mbtiType", "profileEmoji", "auraName", "auraHexColor", "coolOneLiner", "personalityDescription", "description", "textingPros", "textingCons", "topContacts", "tips", "roastSummary"]
        )
        
        # Create messages for the API call
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        system_prompt = "You are a playful, teasing MBTI personality analyst who loves to poke fun at people's texting habits in a friendly way. Address the user directly as 'you' and playfully call out their patterns with humor and clever analogies. Think friendly roasting meets accurate psychology - like a witty friend who knows you too well. Be fun, teasing, but still insightful and accurate. You must respond with valid JSON."
        
        # Call OpenAI with structured output
        response_data = openai_structured_output(
            messages=messages,
            response_format=schema,
            system_prompt=system_prompt,
            max_tokens=2000,
            temperature=0.8,
            model="gpt-4o-2024-08-06"
        )
        
        if not response_data:
            raise Exception("No response data received from OpenAI")
        
        print("🤖 DEBUG: OpenAI API Response:")
        print(json.dumps(response_data, indent=2))
        print("\n" + "=" * 50 + "\n")
        
        # Create MBTIProfile from response data
        profile = MBTIProfile(
            mbti_type=response_data["mbtiType"],
            profile_emoji=response_data["profileEmoji"],
            aura_name=response_data["auraName"],
            aura_hex_color=response_data["auraHexColor"],
            cool_one_liner=response_data["coolOneLiner"],
            personality_description=response_data["personalityDescription"],
            description=response_data["description"],
            texting_pros=response_data["textingPros"],
            texting_cons=response_data["textingCons"],
            top_contacts=response_data["topContacts"],
            tips=response_data["tips"],
            roast_summary=response_data["roastSummary"]
        )
        
        print("✅ DEBUG: Successfully parsed MBTI Profile:")
        print(f"Type: {profile.mbti_type}")
        print(f"Emoji: {profile.profile_emoji}")
        print(f"Personality: {profile.personality_description}")
        print(f"Roast Summary: {profile.roast_summary}")
        print("\n" + "=" * 50 + "\n")
        
        return profile
        
    except Exception as e:
        print(f"Error analyzing MBTI from messages: {e}")
        traceback.print_exc()
        raise
