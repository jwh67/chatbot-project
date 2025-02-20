import { useState, useEffect } from "react";
import { Sun, Moon, Send, Paperclip } from "lucide-react";
import axios from "axios";
import "./styles.css"; // Import external CSS file

export default function ChatApp() {
  const [darkMode, setDarkMode] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    document.body.classList.toggle("dark-mode", darkMode);
  }, [darkMode]);

  const sendMessage = async (query = null) => {
    const message = query || input.trim();
    if (!message) return;

    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setInput("");

    try {
      console.log("Sending query:", message);
      const response = await axios.post("http://localhost:5001/query", { query: message });

      if (response.data && response.data.response && typeof response.data.response === "string") {
        console.log("Received response:", response.data.response);
        setMessages((prev) => [...prev, { role: "bot", content: response.data.response }]);
      } else {
        throw new Error("Invalid API response format");
      }
    } catch (error) {
      console.error("Error fetching response:", error);
      setMessages((prev) => [...prev, { role: "bot", content: "⚠️ Error fetching response. Please try again!" }]);
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
    <div className="chat-container">
      <div className="chat-box">
        <header className="chat-header">
          <h1>Chatbot UI</h1>
          <button onClick={() => setDarkMode(!darkMode)} className="toggle-theme">
            {darkMode ? <Sun size={24} /> : <Moon size={24} />}
          </button>
        </header>

        <div className="suggestions">
          {suggestions.map((text, idx) => (
            <button key={idx} onClick={() => sendMessage(text)} className="suggestion-btn">
              {text}
            </button>
          ))}
        </div>

        <div className="chat-messages">
          {messages.map((msg, index) => (
            <div key={index} className={`chat-bubble ${msg.role}`}>
              {typeof msg.content === "string" ? msg.content : "⚠️ Unexpected response format"}
            </div>
          ))}
        </div>

        <footer className="chat-footer">
          <label className="upload-btn">
            <Paperclip size={24} />
            <input type="file" onChange={handleFileUpload} hidden />
          </label>
          <input
            type="text"
            className="chat-input large-input"
            placeholder="Type a message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          />
          <button onClick={sendMessage} className="send-btn">
            <Send size={24} />
          </button>
        </footer>
      </div>
    </div>
  );
}
