import { useState, useEffect } from "react";
import { Sun, Moon, Send, Paperclip } from "lucide-react";
import axios from "axios";
import "./styles.css"; // Import external CSS file

export default function ChatApp() {
  const [darkMode, setDarkMode] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [editingIndex, setEditingIndex] = useState(null);
  const [editingText, setEditingText] = useState("");


  useEffect(() => {
    document.body.classList.toggle("dark-mode", darkMode);
  }, [darkMode]);

  const sendMessage = async (query = null, event = null) => {
    if (event && event.preventDefault) event.preventDefault();

    const message = typeof query === "string" ? query.trim() : input.trim();
    if (!message) return;

    setMessages((prev) => [...prev, { text: message, sender: "user" }]);
    setInput("");

    console.log("📡 Sending query:", message);

    try {
        const requestData = { query: message };
        console.log("📝 Request Data (Before Sending):", requestData);

        const response = await axios.post(
            "http://192.168.0.182:5001/query",
            requestData,
            { headers: { "Content-Type": "application/json" } }
        );

        console.log("✅ Raw Response:", response);
        console.log("📜 Response Data:", response.data);

        // ✅ Handle API Response Properly
        if (response?.data && typeof response.data === "object") {
            if (response.data.response && typeof response.data.response === "string") {
                let botResponse = response.data.response.trim();
                console.log("🛠 Extracted Response:", botResponse);
                setMessages((prev) => [...prev, { text: botResponse, sender: "bot" }]);
            } else {
                console.error("⚠️ Unexpected response format: Missing 'response' key", response.data);
                setMessages((prev) => [
                    ...prev,
                    { text: "⚠️ Unexpected response format (missing 'response' key).", sender: "bot" }
                ]);
            }
        } else {
            console.error("⚠️ Unexpected response format: `response.data` is invalid", response?.data);
            setMessages((prev) => [
                ...prev,
                { text: "⚠️ Unexpected response format (response.data is invalid).", sender: "bot" }
            ]);
        }
    } catch (error) {
        console.error("❌ Error fetching response:", error);
        setMessages((prev) => [
            ...prev,
            { text: `⚠️ Error fetching response: ${error.message}`, sender: "bot" }
        ]);
    }
  };

  const handleFileUpload = (event) => {
    const uploadedFile = event.target.files[0];
    if (uploadedFile) {
      if (!uploadedFile.name.match(/\.(txt|csv|json|md)$/)) {
        alert("⚠️ Only text-based files are allowed!");
        return;
      }
      setMessages((prev) => [...prev, { sender: "user", text: `📂 Uploaded: ${uploadedFile.name}` }]);
    }
  };

  const suggestions = [
    "What is the weather in the Philippines now?",
    "Translate 'hello' to Spanish",
    "Tell me a fun fact about space",
  ];

  const speakText = (text) => {
    if ("speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "en-US"; // You can change this if needed
      window.speechSynthesis.speak(utterance);
    } else {
      alert("Sorry, your browser does not support text-to-speech.");
    }
  };
  

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
            <button key={idx} onClick={() => sendMessage(text)} className="suggestion-btn upgraded-bubble">
              {text}
            </button>
          ))}
        </div>

        <div className="chat-messages">
  {messages.map((msg, index) => (
    <div key={index} className={`chat-bubble ${msg.sender}`}>
      <div className="chat-message-text">
      {editingIndex === index ? (
  <>
    <input
      type="text"
      value={editingText}
      onChange={(e) => setEditingText(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          setMessages((prev) =>
            prev.map((m, i) =>
              i === index ? { ...m, text: editingText } : m
            )
          );
          setEditingIndex(null);
          sendMessage(editingText); // Resend edited message
        }
      }}
      className="edit-input"
      autoFocus
    />
  </>
) : (
  <>
    <>
  {msg.text}
  {msg.sender === "bot" && (
    <button
      className="speak-btn chat-btn"
      title="Play Audio"
      onClick={() => speakText(msg.text)}
    >
      🔊
    </button>
  )}
</>

    {msg.sender === "user" && (
      <button
        className="edit-btn chat-btn"
        title="Edit"
        onClick={() => {
          setEditingIndex(index);
          setEditingText(msg.text);
        }}
      >
        ✏️
      </button>
    )}
  </>
)}

      </div>

      {msg.sender === "bot" && (
        <div className="chat-controls">
          <button
            onClick={() => navigator.clipboard.writeText(msg.text)}
            title="Copy to clipboard"
            className="chat-btn copy-btn"
          >
            📋
          </button>
          <button
            onClick={() => console.log("👍 Liked response")}
            title="Like"
            className="chat-btn like-btn"
          >
            👍
          </button>
          <button
            onClick={() => console.log("👎 Disliked response")}
            title="Dislike"
            className="chat-btn dislike-btn"
          >
            👎
          </button>
        </div>
      )}
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
            className="chat-input large-input enhanced-input"
            placeholder="Type a message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          />
          <button onClick={sendMessage} className="send-btn enhanced-btn">
            <Send size={24} />
          </button>
        </footer>
      </div>
    </div>
  );
}
