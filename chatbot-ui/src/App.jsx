import { useState, useEffect } from "react";
import { Sun, Moon, Send, Paperclip } from "lucide-react";
import axios from "axios";

export default function ChatApp() {
  const [darkMode, setDarkMode] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [file, setFile] = useState(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
  }, [darkMode]);

  const sendMessage = async (query = null) => {
    const message = query || input.trim();
    if (!message) return;
    const userMessage = { role: "user", content: message };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    
    try {
      const response = await axios.post("http://localhost:5001/query", {
        query: message,
      });
      setMessages((prev) => [...prev, { role: "bot", content: response.data.response }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: "bot", content: "Error fetching response" }]);
    }
  };

  const handleFileUpload = (event) => {
    const uploadedFile = event.target.files[0];
    if (uploadedFile) {
      if (!uploadedFile.name.match(/\.(txt|csv|json|md)$/)) {
        alert("⚠️ Only text-based files are allowed!");
        return;
      }
      setMessages((prev) => [...prev, { role: "user", content: `📂 Uploaded: ${uploadedFile.name}` }]);
    }
  };

  const suggestions = [
    "What is the weather in the Philippines now?",
    "Translate 'hello' to Spanish",
    "Tell me a fun fact about space",
  ];

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-4 bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
      <div className="w-full max-w-3xl p-6 bg-white dark:bg-gray-800 shadow-lg rounded-lg flex flex-col h-[80vh] space-y-4">
        <header className="flex justify-between items-center pb-4 border-b dark:border-gray-700">
          <h1 className="text-2xl font-bold">Chatbot UI</h1>
          <button onClick={() => setDarkMode(!darkMode)} className="p-2 rounded-full bg-gray-200 dark:bg-gray-700">
            {darkMode ? <Sun size={24} /> : <Moon size={24} />}
          </button>
        </header>

        <div className="flex flex-wrap gap-3 p-2 justify-center">
          {suggestions.map((text, idx) => (
            <button
              key={idx}
              onClick={() => sendMessage(text)}
              className="px-5 py-3 bg-blue-500 text-white font-medium rounded-full shadow-md hover:bg-blue-600 transition duration-300"
            >
              {text}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto p-4 space-y-4">
          {messages.map((msg, index) => (
            <div key={index} className={`p-4 rounded-lg w-fit max-w-[80%] ${msg.role === "user" ? "self-end bg-blue-500 text-white" : "self-start bg-gray-300 text-gray-900"}`}>
              <strong>{msg.role === "user" ? "You:" : "Bot:"}</strong> {msg.content}
            </div>
          ))}
        </div>

        <footer className="flex gap-3 items-center p-3 border-t dark:border-gray-700 w-full justify-center">
          <label className="cursor-pointer">
            <Paperclip size={28} className="text-gray-500 dark:text-gray-300" />
            <input type="file" className="hidden" onChange={handleFileUpload} />
          </label>
          <input
            type="text"
            className="flex-1 p-4 text-lg border dark:border-gray-600 rounded-lg bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 w-[90%] max-w-2xl"
            placeholder="Type a message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          />
          <button onClick={sendMessage} className="p-4 bg-blue-500 text-white rounded-full hover:bg-blue-600 transition duration-300">
            <Send size={24} />
          </button>
        </footer>
      </div>
    </div>
  );
}
