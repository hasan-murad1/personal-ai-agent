import ollama
import memory

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
            messages=conversation_history
        )

        assistant_reply = response["message"]["content"]
        print(f"Agent: {assistant_reply}\n")

        conversation_history.append({"role": "assistant", "content": assistant_reply})
        memory.save_message("assistant", assistant_reply)

if __name__ == "__main__":
    main()