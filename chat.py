import ollama
import memory
import tools

def main():
    memory.init_db()

    print("Personal AI Agent (type 'exit' to quit)\n")

    conversation_history = memory.load_history(limit=20)

    if conversation_history:
        print("(Previous conversation loaded)\n")

    while True:
        user_input = input("You: ")

        if user_input.lower() == "exit":
            print("Goodbye!")
            break

        conversation_history.append({"role": "user", "content": user_input})
        memory.save_message("user", user_input)

        response = ollama.chat(
            model="qwen3:4b",
            messages=conversation_history,
            tools=tools.TOOL_SCHEMAS
        )

        message = response["message"]

        if message.get("tool_calls"):
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

            final_response = ollama.chat(
                model="qwen3:4b",
                messages=conversation_history
            )
            assistant_reply = final_response["message"]["content"]
        else:
            assistant_reply = message["content"]

        print(f"Agent: {assistant_reply}\n")

        conversation_history.append({"role": "assistant", "content": assistant_reply})
        memory.save_message("assistant", assistant_reply)

if __name__ == "__main__":
    main()