import { useState } from "react";

export default function Chatbot() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");

  const sendMessage = async () => {
    if (!input.trim()) return;
    console.log("User Input:", input); // Debug: Log what user entered
    
    const userMessage = { sender: "user", text: input };
    setMessages([...messages, userMessage]);
    setInput("");
    
    try {

      console.log("Sending Query:", JSON.stringify({ query: input })); // Debug API request

      const response = await fetch("http://127.0.0.1:5001/query", {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "X-API-Key": "W6fgqEOATNUvxZy0L0r9z9C8xZuIqc9VyVyvg71XnQU"
        },
        body: JSON.stringify({ query: input }), // Ensure correct key "query"
      });

      console.log("Response Status:", response.status); // Log HTTP status
      
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      
      const data = await response.json();
      console.log("API Response:", data);
      
      if (!data.response) {
        throw new Error("Invalid response from API");
      }
      
      const botMessage = { sender: "bot", text: data.response };
      setMessages((prevMessages) => [...prevMessages, botMessage]);
    } catch (error) {
      console.error("Error fetching response:", error);
      const errorMessage = { sender: "bot", text: "Error: Unable to get response from server." };
      setMessages((prevMessages) => [...prevMessages, errorMessage]);
    }
  };

  return (
    <div className="flex flex-col w-full max-w-md mx-auto p-4 bg-gray-100 rounded-xl shadow-md">
      <div className="h-64 overflow-y-auto border-b p-2 bg-white rounded">
        {messages.map((msg, index) => (
          <div key={index} className={`p-2 my-1 rounded ${msg.sender === "user" ? "bg-blue-200 text-right" : "bg-gray-200 text-left"}`}>
            {msg.text}
          </div>
        ))}
      </div>
      <div className="flex mt-4">
        <input
          type="text"
          className="flex-1 p-2 border rounded-l-md focus:outline-none"
          placeholder="Type a message..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === "Enter" && sendMessage()}
        />
        <button
          onClick={sendMessage}
          className="px-4 bg-blue-500 text-white rounded-r-md hover:bg-blue-600"
        >
          Send
        </button>
      </div>
    </div>
  );
}
