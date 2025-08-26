# The Beemo general chat
from ai_api import create_chat_completion, create_chat_message

class BeemoGeneral:
  def __init__(self) -> None:
    # The message to put at the first of completions
    self.initial_assistant_message = (
      "You are Beemo, a personal companion that is there to learn more about the user and to help them grow and improve."
      "You are a robot that is designed to be a friend to the user"
      "You are inquisitive. If the user asks you for something, you ask questions about the user"
      "and the situation until you are relatively confident you can give a response"
      "However, try to respond as quickly as possible once you have asked enough questions"
      "Your overall goal is to help the person grow positively as a person, so respond with this intent" 
    )

    # The json format of each response
    self.response_format = {
			"current_conversation_topic": "details about the current topic (helping user with something, answering a question, teaching something, asking them a question, etc.)",
      "summary": "summary of the situation and the user so far",
      "reasoning": "reasoning for the response",
      "criticism": "constructive self-criticism",
      "questions_to_ask": "if missing any important and relevant information, questions to ask here. otherwise leave blank",
      "response": "if in a position to give a response, response here. if still need to ask more questions, leave blank"
    }
  
  # Runs the beemo chat
  def run(self):
    # The current context of the chat
    current_context = [create_chat_message("system", self.initial_assistant_message)]
    for i in range(100):
      # Get the user input
      user_input = input("User: ")

      # Add the user input to the context
      current_context.append(create_chat_message("user", user_input))

      # Get the assistant response
      assistant_response = create_chat_completion(current_context)

      # Add the assistant response to the context
      current_context.append(create_chat_message("assistant", assistant_response))

      # Print the assistant response
      print("Assistant: " + assistant_response)

# Run the beemo chat
BeemoGeneral().run()