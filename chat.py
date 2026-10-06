import ollama
import memory
import tools
import voice
import action_logger
import os
import json
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

LLM_PROVIDER = "groq"  # "ollama" or "groq"

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY")) if LLM_PROVIDER == "groq" else None
GROQ_MODEL = "qwen/qwen3.8-27b"
OLLAMA_MODEL = "qwen3:4b"

MAX_TOOL_ITERATIONS = 7


def call_llm(messages, use_tools=True):
    """Call the configured LLM provider (Ollama or Groq) through a unified interface."""
    if LLM_PROVIDER == "groq":
        kwargs = {"model": GROQ_MODEL, "messages": messages}
        if use_tools:
            kwargs["tools"] = tools.TOOL_SCHEMAS

        response = groq_client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        tool_calls = None
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                try:
                    parsed_args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    parsed_args = {}
                tool_calls.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    },
                    "_parsed_arguments": parsed_args
                })

        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": tool_calls
        }
    else:
        kwargs = {"model": OLLAMA_MODEL, "messages": messages}
        if use_tools:
            kwargs["tools"] = tools.TOOL_SCHEMAS
        response = ollama.chat(**kwargs)
        return response["message"]


def main():
    """Run the main voice-based conversation loop: record, transcribe, reason with tool-calling, and speak the response."""
    memory.init_db()
    action_logger.init_log_db()

    print(f"Personal AI Agent (voice mode, provider: {LLM_PROVIDER}) - press Ctrl+C to quit\n")

    conversation_history = memory.load_history(limit=20)

    if not conversation_history:
        conversation_history.append({
            "role": "system",
            "content": (
                "You are a personal AI assistant with access to tools for real actions "
                "(file operations, calendar, email, applications) and for retrieving real data "
                "(document search, action logs, calendar listing). "
                "CRITICAL RULE: You must NEVER claim an action was completed, or present any "
                "specific data (like logs, file contents, or event lists), unless you actually "
                "called the corresponding tool and are reporting its real result. "
                "If you have not called a tool, you have no real information — say so honestly "
                "instead of guessing, assuming, or inventing plausible-sounding details."
            )
        })
    else:
        print("(Previous conversation loaded)\n")

    while True:
        audio_file = voice.record_audio()
        user_input = voice.transcribe_audio(audio_file)
        print(f"You said: {user_input}")

        if not user_input.strip():
            print("(No speech detected, try again)\n")
            continue

        if user_input.lower().strip(".") == "exit":
            print("Goodbye!")
            voice.speak_text("Goodbye!")
            break

        conversation_history.append({"role": "user", "content": user_input})
        memory.save_message("user", user_input)

        assistant_reply = None
        iterations = 0

        while iterations < MAX_TOOL_ITERATIONS:
            iterations += 1
            message = call_llm(conversation_history, use_tools=True)

            if not message.get("tool_calls"):
                content = message.get("content") or ""

                if content and ('"function"' in content or "tool_call" in content.lower()):
                    conversation_history.append({"role": "assistant", "content": content})
                    conversation_history.append({
                        "role": "user",
                        "content": "That did not run as a real tool call. Please use the actual tool-calling mechanism."
                    })
                    continue

                assistant_reply = content or "I'm not sure how to respond to that."
                break

            conversation_history.append(message)

            for tool_call in message["tool_calls"]:
                function_name = tool_call["function"]["name"]

                if LLM_PROVIDER == "groq":
                    function_args = tool_call.get("_parsed_arguments", {})
                else:
                    function_args = tool_call["function"]["arguments"]

                is_risky = tools.RISKY_TOOLS.get(function_name, False)

                if is_risky:
                    print(f"\n⚠️  The agent wants to run a RISKY action:")
                    print(f"   Tool: {function_name}")
                    print(f"   Arguments: {function_args}")
                    confirm = input("   Allow this? (yes/no): ").strip().lower()

                    if confirm != "yes":
                        function_result = "Action cancelled by user. Do not retry without asking again."
                        print("   -> Cancelled.\n")
                        action_logger.log_action(function_name, function_args, function_result, was_risky=True, was_confirmed=False)
                        conversation_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "content": str(function_result)
                        })
                        continue
                    else:
                        print("   -> Confirmed, proceeding.\n")

                print(f"[Agent is using tool: {function_name}({function_args})]")

                if function_name in tools.AVAILABLE_FUNCTIONS:
                    function_to_call = tools.AVAILABLE_FUNCTIONS[function_name]
                    try:
                        function_result = function_to_call(**function_args)
                    except Exception as e:
                        function_result = f"Error running tool: {e}"
                else:
                    function_result = f"Error: unknown tool '{function_name}'"

                action_logger.log_action(function_name, function_args, function_result, was_risky=is_risky, was_confirmed=is_risky)

                conversation_history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": str(function_result)
                })

        if assistant_reply is None:
            final_message = call_llm(conversation_history, use_tools=False)
            assistant_reply = final_message.get("content") or "I reached the maximum number of steps trying to complete this."

        print(f"Agent: {assistant_reply}\n")
        voice.speak_text(assistant_reply)

        conversation_history.append({"role": "assistant", "content": assistant_reply})
        memory.save_message("assistant", assistant_reply)


if __name__ == "__main__":
    main()