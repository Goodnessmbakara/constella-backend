from ai.openai_setup import openai_client

def generate_speech(text: str, model: str = "tts-1", voice: str = "nova"):
    """
    Generate speech from text using OpenAI's TTS API
    
    Args:
        text (str): The text to convert to speech
        model (str): The TTS model to use (default: "tts-1")
        voice (str): The voice to use (default: "nova")
        
    Returns:
        StreamingResponse: The streaming response from OpenAI
    """
    try:
        return openai_client.audio.speech.with_streaming_response.create(
            model=model,
            voice=voice,
            input=text,
            response_format="opus" 
        )
        
    except Exception as e:
        print(f"Error generating speech: {str(e)}")
        raise
