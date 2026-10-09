import ollama
import memory
import tools
import voice
import action_logger
import fact_memory
import os
import re
import json
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

LLM_PROVIDER = "groq"  # "ollama" or "groq"

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY")) if LLM_PROVIDER == "groq" else None
GROQ_MODEL = "qwen/qwen3.8-27b"
OLLAMA_MODEL = "qwen3:4b"

MAX_TOOL_ITERATIONS = 7

BASE_SYSTEM_PROMPT = (
    "You are a personal AI assistant with access to tools for real actions "
    "(file operations, calendar, email, applications) and for retrieving real data "
    "(document search, action logs, calendar listing, saved facts). "
    "CRITICAL RULE: You must NEVER claim an action was completed, or present any "
    "specific data (like logs, file contents, or event lists), unless you actually "
    "called the corresponding tool and are reporting its real result. "
    "If you have not called a tool, you have no real information - say so honestly "
    "instead of guessing, assuming, or inventing plausible-sounding details. "
    "Only call remember_fact when the user explicitly asks you to remember something."
)

# Primary defense: if the USER's message asks for a state-changing action,
# the first model call must produce a real tool call (Groq only).
ACTION_INTENT_PATTERN = re.compile(
    r"\b(?:forget|delete|remove|erase|send)\b|^\W*(?:please\s+)?remember\b",
    re.IGNORECASE,
)

# Secondary defense: catch replies that claim a completed action without any tool call.
_ADVERBS = r"(?:(?:\w+ly|just|now|already)\s+)*"
_CLAIM_VERBS = (
    r"(?:removed|deleted|erased|forgotten|cleared|sent|created|scheduled|booked|"
    r"updated|saved|stored|remembered|added)"
)
ACTION_CLAIM_PATTERN = re.compile(
    r"(?<!what\s)\b(?:i've|i have|i)\s+" + _ADVERBS + _CLAIM_VERBS + r"\b"
    r"|\b(?:has|have|had|is|was)\s+(?:now\s+|already\s+)?been\s+" + _ADVERBS + _CLAIM_VERBS + r"\b"
    r"|^\s*done\b",
    re.IGNORECASE,
)


def build_system_prompt():
    """Build the system prompt for this session, including any facts the user asked to be remembered."""
    facts_text = fact_memory.format_facts_for_prompt()
    if facts_text:
        return BASE_SYSTEM_PROMPT + "\n\n" + facts_text
    return BASE_SYSTEM_PROMPT


def call_llm(messages, use_tools=True, force_tool=False):
    """Call the configured LLM provider (Ollama or Groq) through a unified interface.

    force_tool=True asks Groq to require a tool call (ignored for Ollama).
    """
    if LLM_PROVIDER == "groq":
        kwargs = {"model": GROQ_MODEL, "messages": messages}
        if use_tools:
            kwargs["tools"] = tools.TOOL_SCHEMAS
            if force_tool:
                kwargs["tool_choice"] = "required"

        try:
            response = groq_client.chat.completions.create(**kwargs)
        except Exception as e:
            if force_tool:
                print(f"[Warning: required tool call was rejected ({e}); retrying without it]")
                kwargs.pop("tool_choice", None)
                response = groq_client.chat.completions.create(**kwargs)
            else:
                raise

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
    fact_memory.init_facts_db()

    print(f"Personal AI Agent (voice mode, provider: {LLM_PROVIDER}) - press Ctrl+C to quit\n")

    past_messages = memory.load_history(limit=20)
    if past_messages:
        print("(Previous conversation loaded)\n")

    conversation_history = [{"role": "system", "content": build_system_prompt()}] + past_messages

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
        used_tool_this_turn = False
        guard_retried = False

        while iterations < MAX_TOOL_ITERATIONS:
            iterations += 1

            force_tool = (
                iterations == 1
                and LLM_PROVIDER == "groq"
                and ACTION_INTENT_PATTERN.search(user_input) is not None
            )
            if force_tool:
                print("[Action request detected - requiring a real tool call]")

            message = call_llm(conversation_history, use_tools=True, force_tool=force_tool)

            if not message.get("tool_calls"):
                content = message.get("content") or ""

                if content and ('"function"' in content or "tool_call" in content.lower()):
                    conversation_history.append({"role": "assistant", "content": content})
                    conversation_history.append({
                        "role": "user",
                        "content": "That did not run as a real tool call. Please use the actual tool-calling mechanism."
                    })
                    continue

                if (not used_tool_this_turn and not guard_retried
                        and content and ACTION_CLAIM_PATTERN.search(content.replace("*", ""))):
                    guard_retried = True
                    print("[Guard: reply claimed an action but no tool was called - asking the model to retry]")
                    conversation_history.append({"role": "assistant", "content": content})
                    conversation_history.append({
                        "role": "user",
                        "content": (
                            "SYSTEM CHECK: your last reply says an action was completed, but you did not "
                            "call any tool in this turn, so nothing was actually done. If the user asked "
                            "for an action, call the correct tool now. If not, restate your answer "
                            "without claiming that any action was performed."
                        )
                    })
                    continue

                assistant_reply = content or "I'm not sure how to respond to that."
                break

            used_tool_this_turn = True
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

                if function_name in ("remember_fact", "forget_fact"):
                    conversation_history[0]["content"] = build_system_prompt()

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