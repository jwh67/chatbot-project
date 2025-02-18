/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: 'class', // ✅ Forces dark mode toggle to use "class"
  theme: {
    extend: {
      colors: {
        primary: "#4F46E5", // Custom primary color
        backgroundLight: "#F3F4F6",
        backgroundDark: "#1E1E1E",
        messageUser: "#2563EB",
        messageBot: "#E5E7EB",
      },
    },
  },
  plugins: [],
};
