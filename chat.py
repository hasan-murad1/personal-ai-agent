import ollama
import memory
import tools
import voice

MAX_TOOL_ITERATIONS = 5

def main():
    memory.init_db()

    print("Personal AI Agent (voice mode) - press Ctrl+C to quit\n")

    conversation_history = memory.load_history(limit=20)

    if conversation_history:
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

            response = ollama.chat(
                model="qwen3:4b",
                messages=conversation_history,
                tools=tools.TOOL_SCHEMAS
            )

            message = response["message"]

            if not message.get("tool_calls"):
                content = message["content"]

                if '"function"' in content or "tool_call" in content.lower():
                    conversation_history.append({"role": "assistant", "content": content})
                    conversation_history.append({
                        "role": "user",
                        "content": "That did not run as a real tool call. Please use the actual tool-calling mechanism, one tool at a time, not text."
                    })
                    continue

                assistant_reply = content
                break

            conversation_history.append(message)

            for tool_call in message["tool_calls"]:
                function_name = tool_call["function"]["name"]
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
                        conversation_history.append({
                            "role": "tool",
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

                conversation_history.append({
                    "role": "tool",
                    "content": str(function_result)
                })

        if assistant_reply is None:
            assistant_reply = "I reached the maximum number of steps trying to complete this. Could you simplify the request?"

        print(f"Agent: {assistant_reply}\n")
        voice.speak_text(assistant_reply)

        conversation_history.append({"role": "assistant", "content": assistant_reply})
        memory.save_message("assistant", assistant_reply)

if __name__ == "__main__":
    main()