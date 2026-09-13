import ollama

def main():
    print("Personal AI Agent (type 'exit' to quit)\n")
    
    conversation_history = []

    while True:
        user_input = input("You: ")
        
        if user_input.lower() == "exit":
            print("Goodbye!")
            break

        conversation_history.append({"role": "user", "content": user_input})

        response = ollama.chat(
            model="qwen3:4b",
            messages=conversation_history
        )

        assistant_reply = response["message"]["content"]
        print(f"Agent: {assistant_reply}\n")

        conversation_history.append({"role": "assistant", "content": assistant_reply})

if __name__ == "__main__":
    main()